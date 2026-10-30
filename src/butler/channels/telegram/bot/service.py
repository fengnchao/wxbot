"""Long polling and independent, idempotent delivery to Butler."""
import threading
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import requests

from butler.channels.telegram.service import instance_lock
from butler.channels.telegram.bot.inbox import validate
from butler.channels.telegram.bot.queue import Queue
from butler.channels.telegram.bot.news import NewsRelay
from butler.channels.telegram.bot.media import TelegramMedia, validate_file_path
from butler.delivery.media import MAX_BYTES, _atomic


def log(message):
    print('[telegram-bot] ' + message, flush=True)


class TelegramError(RuntimeError):
    def __init__(self, code, retry_after=5, *, kind='http', method='API'):
        super().__init__('Telegram API error')  # Never include URL/token or server description.
        self.code = code
        self.retry_after = retry_after
        self.kind = kind
        self.method = method if method in ('getMe', 'getWebhookInfo', 'getUpdates', 'getFile', 'download') else 'API'

    def __str__(self):
        reasons = {
            'proxy': '代理连接失败，请检查 proxy_url 的地址、端口及代理服务',
            'tls': 'TLS 证书校验失败，请检查代理证书和本机时间',
            'connect_timeout': '连接 Telegram 超时；直连不可用时请配置 proxy_url',
            'read_timeout': '等待 Telegram 响应超时，请检查代理网络',
            'connection': '连接 Telegram 失败，请检查网络、DNS 和 proxy_url',
            'network': 'Telegram 网络请求失败，请检查代理配置',
            'invalid_response': '返回内容不是有效 Bot API 回执，请检查代理或网络拦截',
        }
        http_reasons = {
            400: 'Telegram 拒绝请求参数',
            401: 'Token 未通过认证，请检查是否已撤销或填写错误',
            403: 'Telegram 拒绝访问',
            404: 'API 地址或 Token 不正确',
            407: '代理要求认证，请检查代理凭据',
            409: '接收冲突，请检查是否有其他轮询进程或 Webhook',
            429: f'请求被限流，需等待 {self.retry_after} 秒',
        }
        reason = reasons.get(self.kind, http_reasons.get(self.code, 'Telegram 接口请求失败'))
        return f'{self.method} 失败（code={self.code}）：{reason}'


class BotAPI:
    def __init__(self, cfg):
        self._url = 'https://api.telegram.org/bot' + cfg.token + '/'
        self._files_url = 'https://api.telegram.org/file/bot' + cfg.token + '/'
        self.session = requests.Session()
        self.session.trust_env = False
        if cfg.proxy_url:
            self.session.proxies = {'http': cfg.proxy_url, 'https': cfg.proxy_url}

    def call(self, method, **params):
        try:
            with self.session.post(self._url + method, json=params, timeout=(10, 40), allow_redirects=False) as response:
                try:
                    data = response.json()
                except ValueError:
                    raise TelegramError(response.status_code, method=method,
                                        kind='invalid_response' if response.status_code == 200 else 'http') from None
                if response.status_code != 200 or not isinstance(data, dict) or data.get('ok') is not True:
                    parameters = data.get('parameters') if isinstance(data, dict) else None
                    wait = parameters.get('retry_after', 5) if isinstance(parameters, dict) else 5
                    code = data.get('error_code') if isinstance(data, dict) else None
                    code = code if type(code) is int else response.status_code
                    raise TelegramError(code, wait if type(wait) is int and wait > 0 else 5,
                                        method=method, kind='invalid_response' if code == 200 else 'http')
                if 'result' not in data:
                    raise TelegramError(response.status_code, method=method, kind='invalid_response')
                return data['result']
        except TelegramError:
            raise
        except requests.exceptions.ProxyError:
            raise TelegramError(0, kind='proxy', method=method) from None
        except requests.exceptions.SSLError:
            raise TelegramError(0, kind='tls', method=method) from None
        except requests.exceptions.ConnectTimeout:
            raise TelegramError(0, kind='connect_timeout', method=method) from None
        except requests.exceptions.ReadTimeout:
            raise TelegramError(0, kind='read_timeout', method=method) from None
        except requests.exceptions.ConnectionError:
            raise TelegramError(0, kind='connection', method=method) from None
        except requests.exceptions.RequestException:
            raise TelegramError(0, kind='network', method=method) from None

    def download(self, file_path):
        validate_file_path(file_path)
        try:
            with self.session.get(self._files_url + file_path, stream=True,
                                  timeout=(10, 40), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise TelegramError(response.status_code, method='download')
                length = response.headers.get('Content-Length')
                if length is not None and (not length.isdigit() or int(length) > MAX_BYTES):
                    raise ValueError('Telegram 图片超过下载上限')
                data = bytearray()
                for block in response.iter_content(64 * 1024):
                    if len(data) + len(block) > MAX_BYTES:
                        raise ValueError('Telegram 图片超过下载上限')
                    data.extend(block)
                return bytes(data)
        except requests.RequestException:
            raise TelegramError(0, kind='network', method='download') from None


def publish_identity(state_dir, me):
    """Only public, validated getMe data is made available to the desktop broker."""
    if (not isinstance(me, dict) or type(me.get('id')) is not int or me['id'] <= 0
            or me.get('is_bot') is not True or not isinstance(me.get('username'), str)
            or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{3,31}', me['username'])):
        raise ValueError('无效机器人身份')
    state_dir.mkdir(parents=True, exist_ok=True)
    _atomic(state_dir / 'bot-identity.json', json.dumps({'bot_id': me['id'],
        'username': me['username'], 'at': datetime.now(timezone.utc).isoformat()}).encode('utf-8'))


# Keep text entities (including hidden URLs), media metadata and original forward attribution.
MESSAGE_KEYS = ('message_id', 'date', 'from', 'chat', 'text', 'entities', 'caption', 'caption_entities',
                'photo', 'document', 'video', 'animation', 'audio', 'voice', 'sticker', 'media_group_id',
                'forward_origin', 'has_protected_content', 'link_preview_options')


def select_message(update, allowed):
    msg = update.get('message')
    if not isinstance(msg, dict):
        return None
    sender, chat = msg.get('from', {}), msg.get('chat', {})
    uid = sender.get('id')
    if chat.get('type') != 'private' or chat.get('id') != uid or sender.get('is_bot'):
        return None
    if uid not in allowed:
        # Useful when finding one's own numeric id, without logging their message.
        log(f'未接收：sender_id={uid} 不在 allowed_user_ids；不记录正文')
        return None
    return {key: msg[key] for key in MESSAGE_KEYS if key in msg}


def _public_forward_receipt(value):
    """Return only the bounded public source identity carried by one Bot receipt."""
    if not isinstance(value, dict):
        return None
    if (type(value.get('source_chat_id')) is not int or value['source_chat_id'] >= 0
            or type(value.get('source_message_id')) is not int or value['source_message_id'] <= 0
            or type(value.get('bot_message_id')) is not int or value['bot_message_id'] <= 0):
        return None
    username, received = value.get('source_username', ''), value.get('received_at')
    if (not isinstance(username, str) or (username and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{3,31}', username))
            or not isinstance(received, str) or len(received) > 40):
        return None
    try:
        if datetime.fromisoformat(received).tzinfo is None:
            return None
    except ValueError:
        return None
    return {key: value.get(key, '') for key in
            ('source_chat_id', 'source_username', 'source_message_id', 'bot_message_id', 'received_at')}


def publish_forward_receipt(state_dir, bot, message):
    """Called only after authorized ingress commits. Failure never affects that commit."""
    origin = message.get('forward_origin')
    if not isinstance(origin, dict) or origin.get('type') != 'channel':
        return
    source = origin.get('chat')
    if not isinstance(source, dict):
        return
    at = datetime.now(timezone.utc).isoformat()
    receipt = _public_forward_receipt(dict(source_chat_id=source.get('id'),
        source_username=source.get('username', ''), source_message_id=origin.get('message_id'),
        bot_message_id=message.get('message_id'), received_at=at))
    if receipt is None:
        return
    try:
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / 'forward-receipts.json'
        old = {}
        if path.is_file():
            try:
                with path.open('rb') as stream:
                    data = stream.read(2 * 1024 * 1024 + 1)
                if len(data) <= 2 * 1024 * 1024:
                    parsed = json.loads(data)
                    old = parsed if isinstance(parsed, dict) else {}
            except (ValueError, UnicodeError):
                pass
        receipts = []
        if old.get('bot_id') == bot and isinstance(old.get('receipts'), list):
            for entry in old['receipts'][-2000:]:
                safe = _public_forward_receipt(entry)
                if safe is not None:
                    if safe['bot_message_id'] == receipt['bot_message_id']:
                        return  # An old update must never masquerade as a fresh forwarding receipt.
                    receipts.append(safe)
        receipts.append(receipt)
        _atomic(path, json.dumps({'bot_id': bot, 'at': at, 'receipts': receipts[-2000:]},
                                ensure_ascii=False).encode('utf-8'))
    except Exception:
        log('转发收件回执写入失败；已提交的入站消息仍保留')


def persist_update(queue, state_dir, bot, update, allowed):
    """One ingestion boundary used by the sole existing getUpdates poller."""
    message = select_message(update, allowed)
    if message is not None:
        validate({'bot_id': bot, 'update_id': update['update_id'], 'message': message})
    queue.ingest(bot, update, message)
    if message is not None:
        # INSERT OR IGNORE retains the first durable payload for a repeated update ID.
        # A conflicting duplicate may advance no forwarding evidence.
        with queue.db() as db:
            stored = db.execute('SELECT payload FROM pending WHERE bot=? AND uid=?', (bot, update['update_id'])).fetchone()
        if stored is not None and json.loads(stored[0])['message'] == message:
            publish_forward_receipt(state_dir, bot, message)
    return message


def submit(session, cfg, body):
    if not cfg.token:
        raise ValueError('Butler server.token 未配置')
    host = cfg.host
    if host in ('0.0.0.0', '::'):
        host = '127.0.0.1'
    if host not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('本阶段 Butler 接收端仅允许本机地址')
    address = f'[{host}]' if ':' in host else host
    try:
        with session.post(f'http://{address}:{cfg.port}/v1/telegram/inbox', json=body,
                          headers={'Authorization': 'Bearer ' + cfg.token},
                          timeout=(5, 15), allow_redirects=False) as response:
            if response.status_code == 400:
                return 'rejected', 'Butler 拒收格式或内容冲突，请核对 status'
            if response.status_code != 200:
                return 'pending', f'Butler HTTP {response.status_code}；保留待提交'
            data = response.json()
            if (data.get('ok') is True and data.get('status') in ('received', 'duplicate')
                    and data.get('bot_id') == body['bot_id'] and data.get('update_id') == body['update_id']):
                return 'received', 'Butler 已确认入库 receipt=' + str(data.get('receipt_id'))
            return 'pending', 'Butler 回执未匹配，保留待提交'
    except (requests.RequestException, ValueError, AttributeError):
        return 'pending', 'Butler 连接或回执异常，保留待提交'


def run(cfg, butler_cfg):
    if not butler_cfg.token or butler_cfg.host not in ('0.0.0.0', '::', '127.0.0.1', 'localhost', '::1'):
        raise ValueError('请配置本机 Butler 地址与 server.token')
    with instance_lock(cfg.state_dir / 'receiver.lock'):
        api = BotAPI(cfg)
        queue = Queue(cfg.state_dir / 'relay.sqlite3')
        stop = threading.Event()
        errors = []
        worker = None
        news_worker = None
        media_api = None
        try:
            log('正在连接 getMe；网络方式=' + ('显式代理' if cfg.proxy_url else '直连（未配置 proxy_url）'))
            me = api.call('getMe')
            bot = me['id']
            if type(bot) is not int or bot <= 0 or me.get('is_bot') is not True:
                raise ValueError('无效机器人身份')
            publish_identity(cfg.state_dir, me)
            log('getMe 认证成功，正在检查 Webhook')
            if api.call('getWebhookInfo').get('url'):
                log('机器人已有 Webhook；请先核对原接收服务，本程序不会删除它')
                raise ValueError('机器人已有 Webhook；请先核对原接收服务，本程序不会删除它')
            log(f'机器人连接成功 bot_id={bot}；仅接收私聊；白名单人数={len(cfg.allowed_users)}')
            from butler.channels.telegram.relay.settings import load as load_relay
            relay_path = cfg.relay_config or cfg.butler_config.parent / 'config.telegram-relay.toml'
            media_api = BotAPI(cfg)  # Independent HTTP session; only the original api polls updates.
            news = NewsRelay(queue, bot, butler_cfg, cfg.allowed_users, log,
                             media=TelegramMedia(media_api, butler_cfg),
                             relay_settings=lambda: load_relay(relay_path))
            news.recover()

            def deliver_news():
                try:
                    while not stop.is_set():
                        try:
                            expanded = news.expand_once()
                            if stop.is_set():
                                break
                            delivered = news.deliver_once()
                            if not expanded and not delivered:
                                stop.wait(1)
                        except ValueError:
                            log('新闻配置或正文格式异常，请检查 status 和新闻分组；10 秒后重新检查')
                            stop.wait(10)
                except Exception as exc:
                    errors.append(type(exc).__name__)
                    stop.set()

            def delivery():
                try:
                    with requests.Session() as session:
                        session.trust_env = False
                        while not stop.is_set():
                            body = queue.next(bot)
                            if body is None:
                                stop.wait(1)
                                continue
                            if body['message']['from']['id'] not in cfg.allowed_users:
                                queue.finish(bot, body['update_id'], 'rejected', '发送者已移出白名单')
                                continue
                            state, detail = submit(session, butler_cfg, body)
                            queue.finish(bot, body['update_id'], state, detail)
                            log(f"update={body['update_id']} {detail}")
                            if state == 'pending':
                                stop.wait(10)
                except Exception as exc:
                    errors.append(type(exc).__name__)
                    stop.set()

            worker = threading.Thread(target=delivery, name='telegram-butler-delivery')
            worker.start()
            news_worker = threading.Thread(target=deliver_news, name='telegram-news-delivery')
            news_worker.start()
            while not stop.is_set():
                try:
                    updates = api.call('getUpdates', offset=queue.offset(bot), timeout=25,
                                       limit=100, allowed_updates=['message'])
                except TelegramError as exc:
                    log(str(exc))
                    if exc.code in (400, 401, 403, 404, 409):
                        raise
                    stop.wait(exc.retry_after)
                    continue
                if not isinstance(updates, list):
                    raise ValueError('无效更新列表')
                for update in sorted(updates, key=lambda item: item['update_id']):
                    if stop.is_set():
                        break
                    msg = persist_update(queue, cfg.state_dir, bot, update, cfg.allowed_users)
                    if msg is not None:
                        log(f"已收件 update={update['update_id']} sender={msg['from']['id']}；等待 Butler 确认")
            if errors:
                raise RuntimeError('投递线程停止：' + errors[0])
        finally:
            stop.set()
            if worker is not None:
                worker.join()
            if news_worker is not None:
                news_worker.join()
            api.session.close()
            if media_api is not None:
                media_api.session.close()
