"""Turn saved bot messages into news deliveries using the existing Butler API."""
from datetime import datetime, timedelta, timezone
from contextlib import closing
import json
import re
from hashlib import sha256
import time
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from butler.push_client import push_news, push_news_bundle
from butler.telegram.service import read_subscribers
from common.media_bundle import validate_items
from .media import MediaError


class MediaRetryError(ValueError):
    """Controlled local operator diagnostic; never includes user content or credentials."""


def retry_media_preparation(path, bot, package_key):
    """Explicitly reopen failed preparation only when no delivery was ever created."""
    if (type(bot) is not int or bot <= 0 or not isinstance(package_key, str)
            or not package_key or len(package_key)>4096):
        raise MediaRetryError('需要有效的 bot-id 和 package-key')
    path = Path(path).resolve()
    if not path.is_file():
        raise MediaRetryError('队列数据库不存在，未创建新库')
    with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=15)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'news_package','news_bundle_delivery','news_plan','pending'} <= tables:
            raise MediaRetryError('此队列没有图文包准备记录，未迁移数据库')

        def safe_failed():
            row = db.execute('SELECT uid,state FROM news_package WHERE bot=? AND package_key=?', (bot,package_key)).fetchone()
            if row is None or row[1]!='media_failed':
                raise MediaRetryError('仅允许重试准备失败的现有图文包')
            if db.execute('SELECT 1 FROM news_bundle_delivery WHERE bot=? AND package_key=? LIMIT 1', (bot,package_key)).fetchone():
                raise MediaRetryError('此图文包已有投递记录，禁止重置或重发')
            return row[0]

        anchor_uid = safe_failed()
        aliases = {package_key}
        if 'news_package_alias' in tables:
            aliases.update(row[0] for row in db.execute('SELECT alias FROM news_package_alias WHERE bot=? AND package_key=?', (bot,package_key)))
        anchor = db.execute('SELECT payload FROM pending WHERE bot=? AND uid=?', (bot,anchor_uid)).fetchone()
        if anchor:
            aliases.add(NewsRelay._package_key(json.loads(anchor[0])['message']))
        updates = []
        for uid,payload in db.execute('SELECT uid,payload FROM pending WHERE bot=?', (bot,)):
            if uid==anchor_uid or NewsRelay._package_key(json.loads(payload)['message']) in aliases:
                updates.append(uid)
        if not updates:
            raise MediaRetryError('没有可重建的原始入站消息，保留失败记录')
        if 'news_delivery' in tables and any(db.execute('SELECT 1 FROM news_delivery WHERE bot=? AND uid=? LIMIT 1', (bot,uid)).fetchone() for uid in updates):
            raise MediaRetryError('关联入站消息已有文字投递记录，禁止重置')
        # Revalidate immediately before mutation under the same write lock. No sender
        # can create a receipt between this check and the reset transaction's commit.
        safe_failed()
        db.executemany('DELETE FROM news_plan WHERE bot=? AND uid=?', [(bot,uid) for uid in updates])
        if 'news_package_alias' in tables:
            db.execute('DELETE FROM news_package_alias WHERE bot=? AND package_key=?', (bot,package_key))
        db.execute("DELETE FROM news_package WHERE bot=? AND package_key=? AND state='media_failed'", (bot,package_key))
    return {'status':'retry_ready','bot_id':bot,'package_key':package_key,'reset_updates':sorted(updates)}


def format_news(message, *, media_enabled=False, include_text=True, include_source=True, include_time=True):
    """Return text parts and a skip reason. Media remains explicit, never silently lost."""
    text = message.get('text') or message.get('caption') or ''
    if not isinstance(text, str):
        return [], '正文格式无效'
    text = text.strip()
    if re.match(r'^/[A-Za-z][A-Za-z0-9_]*(?:@\w+)?(?:\s|$)', text):
        return [], '机器人命令不作为新闻转发'
    if not text and not media_enabled:
        return [], '无文字正文；纯图片或其他媒体尚未接通微信发送'
    if not include_text and not any(message.get(key) for key in ('photo', 'document', 'video', 'animation', 'audio', 'voice', 'sticker')):
        return [], '文字转发已关闭'
    links = []
    for entity in (message.get('entities') or []) + (message.get('caption_entities') or []):
        url = entity.get('url') if isinstance(entity, dict) else None
        try:
            valid = isinstance(url, str) and urlsplit(url).scheme in ('http', 'https')
        except ValueError:
            valid = False
        if valid and url not in text and url not in links:
            links.append(url)
    origin = message.get('forward_origin') or {}
    source = origin.get('chat') or origin.get('sender_chat') or {}
    title = str(source.get('title') or 'Telegram 转发')[:100].replace('\n', ' ')
    username, source_mid = source.get('username'), origin.get('message_id')
    if isinstance(username, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{3,31}', username) and type(source_mid) is int and source_mid > 0:
        url = f'https://t.me/{username}/{source_mid}'
        if url not in links and url not in text:
            links.append(url)
    if links:
        text += '\n\n链接：\n' + '\n'.join(links)
    if not media_enabled and any(message.get(key) for key in ('photo', 'document', 'video', 'animation', 'audio', 'voice', 'sticker')):
        text += '\n\n[本条含媒体附件，当前仅转发文字和链接]'
    if not include_text:
        text = ''
    stamp = origin.get('date', message.get('date'))
    try:
        date = datetime.fromtimestamp(stamp, timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError, OverflowError, OSError):
        date = '时间未知'
    header = '【新闻消息】' + (title if include_source else '') + ('\n' + date if include_time else '')
    chunks, current = [], ''
    for token in re.split(r'(https?://[^\s]+)', text):
        if token.startswith(('https://', 'http://')):
            if current and len(current) + len(token) > 500:
                chunks.append(current)
                current = ''
            current += token
        else:
            while token:
                room = 500 - len(current)
                if room <= 0:
                    chunks.append(current)
                    current = ''
                    room = 500
                current += token[:room]
                token = token[room:]
    if current:
        chunks.append(current)
    if not chunks and media_enabled:
        return [header], ''
    return [header + (f'（{i}/{len(chunks)}）' if len(chunks) > 1 else '') + '\n\n' + chunk
            for i, chunk in enumerate(chunks, 1)], ''


class NewsRelay:
    def __init__(self, queue, bot, cfg, allowed_users, log, *, push=push_news,
                 media=None, bundle_push=push_news_bundle, relay_settings=None, clock=time.time):
        self.queue, self.bot, self.cfg = queue, bot, cfg
        self.allowed_users, self.log, self.push = allowed_users, log, push
        self.media, self.bundle_push = media, bundle_push
        self.relay_settings = relay_settings
        self.clock = clock

    def _settings(self):
        return self.relay_settings() if self.relay_settings is not None else None

    def recover(self):
        with self.queue.db() as db:
            db.execute("UPDATE news_delivery SET state='uncertain',reason='提交中断，结果未知，不自动重发',updated=CURRENT_TIMESTAMP WHERE bot=? AND state='sending'", (self.bot,))
            db.execute("UPDATE news_bundle_delivery SET state='uncertain',reason='提交中断，结果未知，不自动重发',updated=CURRENT_TIMESTAMP WHERE bot=? AND state='sending'", (self.bot,))
            db.execute("UPDATE news_package SET state='media_failed',reason='图片准备中断，请人工核对' WHERE bot=? AND state='preparing'", (self.bot,))

    def expand_once(self):
        settings = self._settings()
        if settings is not None and settings.include_images and self.media is not None:
            return self._expand_bundle(settings)
        with self.queue.db() as db:
            row = db.execute('''SELECT p.uid,p.payload FROM pending p WHERE p.bot=? AND p.state='received'
                AND NOT EXISTS (SELECT 1 FROM news_plan n WHERE n.bot=p.bot AND n.uid=p.uid)
                ORDER BY p.uid LIMIT 1''', (self.bot,)).fetchone()
        if row is None:
            return False
        uid, payload = row
        msg = json.loads(payload)['message']
        if msg['from']['id'] not in self.allowed_users:
            parts, reason = [], '发送者已移出白名单'
        else:
            parts, reason = format_news(msg,
                include_text=getattr(settings, 'include_text', True),
                include_source=getattr(settings, 'include_source', True),
                include_time=getattr(settings, 'include_time', True))
        users = read_subscribers(self.cfg.group_file_path()) if parts else []
        if parts and not users:
            reason = '新闻消息分组没有接收人，本条跳过'
        with self.queue.db() as db:
            created = db.execute('INSERT OR IGNORE INTO news_plan(bot,uid,reason) VALUES(?,?,?)',
                                 (self.bot, uid, reason or '新闻投递任务已生成')).rowcount
            if created:
                for user in users:
                    for number, text in enumerate(parts, 1):
                        db.execute('INSERT INTO news_delivery(bot,uid,contact,part,text) VALUES(?,?,?,?,?)',
                                   (self.bot, uid, user, number, text))
        self.log(f'新闻 update={uid}：' + (reason or f'已生成 {len(users)} 人 × {len(parts)} 段任务；messageType=1'))
        return True

    def deliver_once(self):
        if self._deliver_bundle():
            return True
        # Subscription changes are read again immediately before delivery.
        users = read_subscribers(self.cfg.group_file_path())
        with self.queue.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT d.id,d.uid,d.contact,d.part,d.text,p.payload
                FROM news_delivery d JOIN pending p ON p.bot=d.bot AND p.uid=d.uid
                WHERE d.bot=? AND d.state='pending' AND NOT EXISTS (
                  SELECT 1 FROM news_delivery prev WHERE prev.bot=d.bot AND prev.uid=d.uid
                    AND prev.contact=d.contact AND prev.part<d.part AND prev.state!='sent')
                ORDER BY d.id LIMIT 1''', (self.bot,)).fetchone()
            if row is None:
                return False
            task, uid, contact, part, text, payload = row
            settings = self._settings()
            if (contact not in users or json.loads(payload)['message']['from']['id'] not in self.allowed_users
                    or not getattr(settings, 'include_text', True)):
                db.execute("UPDATE news_delivery SET state='cancelled',reason='用户已取消订阅或发送者权限已撤销' WHERE id=?", (task,))
                return True
            db.execute("UPDATE news_delivery SET state='sending',updated=CURRENT_TIMESTAMP WHERE id=?", (task,))
        self.log(f'新闻 update={uid} → {contact} 第 {part} 段：开始请求 Butler /v1/push messageType=1')
        try:
            result = self.push(self.cfg, contact, text)
            state, reason = result['state'], result['reason']
            if state not in ('sent', 'not_submitted', 'uncertain'):
                raise ValueError('Invalid push state')
        except Exception:
            state, reason = 'uncertain', '提交异常，结果未知，不自动重发'
        with self.queue.db() as db:
            db.execute('UPDATE news_delivery SET state=?,reason=?,updated=CURRENT_TIMESTAMP WHERE id=?',
                       (state, reason, task))
        self.log(f'新闻 update={uid} → {contact}：{state}；{reason}')
        return True

    @staticmethod
    def _source_key(message):
        origin = message.get('forward_origin')
        if not isinstance(origin, dict) or origin.get('type') != 'channel':
            return ''
        source = origin.get('chat')
        mid = origin.get('message_id')
        if (not isinstance(source, dict) or type(source.get('id')) is not int or source['id'] >= 0
                or type(mid) is not int or mid <= 0):
            return ''
        return f'source:{source["id"]}:message:{mid}'

    @classmethod
    def _package_key(cls, message):
        chat = message['chat']['id']
        group = message.get('media_group_id')
        return f'chat:{chat}:album:{group}' if group else cls._source_key(message) or f'chat:{chat}:message:{message["message_id"]}'

    @classmethod
    def _member_order(cls, message):
        source = cls._source_key(message)
        return int(source.rsplit(':',1)[1]) if source else message['message_id']

    def _expand_bundle(self, settings):
        with self.queue.db() as db:
            rows = db.execute('''SELECT p.uid,p.payload,p.received_at,p.state FROM pending p
                WHERE p.bot=? AND p.state IN ('received','pending') AND NOT EXISTS
                (SELECT 1 FROM news_plan n WHERE n.bot=p.bot AND n.uid=p.uid) ORDER BY p.uid''', (self.bot,)).fetchall()
        if not rows:
            return False
        # An album still gathering members must not freeze unrelated channels.
        chosen, grouped = None, {}
        for uid, payload, at, state in rows:
            message = json.loads(payload)['message']
            grouped.setdefault(self._package_key(message), []).append((uid, message, at, state))
        for uid, payload, at, state in rows:
            if state != 'received':
                continue
            message = json.loads(payload)['message']
            key = self._package_key(message)
            with self.queue.db() as db:
                existing = db.execute('SELECT state FROM news_package WHERE bot=? AND package_key=?', (self.bot, key)).fetchone()
                alias = db.execute('SELECT package_key FROM news_package_alias WHERE bot=? AND alias=?', (self.bot, key)).fetchone()
                existing = existing or alias
            all_members = grouped[key]
            members = [(u, msg, stamp) for u, msg, stamp, _ in all_members]
            incomplete = any(s != 'received' for _, _, _, s in all_members)
            if message.get('media_group_id') and not existing:
                first, last = min(m[2] for m in members), max(m[2] for m in members)
                now = self.clock()
                if ((now - last < settings.album_quiet_seconds or incomplete)
                        and now - first < settings.max_album_wait):
                    continue
            elif incomplete and not existing:
                continue
            chosen = uid, key, members, existing, incomplete
            break
        if chosen is None:
            return False
        uid, key, members, existing, incomplete = chosen
        if existing:
            with self.queue.db() as db:
                for member_uid, _, _ in members:
                    db.execute('INSERT OR IGNORE INTO news_plan VALUES(?,?,?)',
                               (self.bot, member_uid, '图集迟到或重复成员，需人工核对；不自动重发'))
            return True
        assembly_key = key
        sources = sorted({self._source_key(msg) for _, msg, _ in members if self._source_key(msg)})
        if members[0][1].get('media_group_id') and sources and all(self._source_key(msg) for _, msg, _ in members):
            identities = sorted({(int(source.split(':')[1]),int(source.rsplit(':',1)[1])) for source in sources})
            key = 'source:album:' + sha256(json.dumps(identities).encode()).hexdigest()
        hold_reason = ''
        with self.queue.db() as db:
            known = {row[0] for source in sources for row in db.execute(
                'SELECT package_key FROM news_package_alias WHERE bot=? AND alias=?', (self.bot, source))}
            found = sum(db.execute('SELECT 1 FROM news_package_alias WHERE bot=? AND alias=?', (self.bot, source)).fetchone() is not None
                        for source in sources)
            if sources and found == len(sources) and len(known) == 1:
                original_key = next(iter(known))
                db.execute('INSERT OR IGNORE INTO news_package_alias VALUES(?,?,?)', (self.bot, assembly_key, original_key))
                for member_uid, _, _ in members:
                    db.execute('INSERT OR IGNORE INTO news_plan VALUES(?,?,?)',
                               (self.bot, member_uid, '图集迟到或重复成员，需人工核对；不自动重发'))
                return True
            if found:
                hold_reason = '原来源消息与已有图文包部分重叠，保留待人工核对，不重复投递'
        users = list(dict.fromkeys(read_subscribers(self.cfg.group_file_path())))
        sender = members[0][1]['from']['id']
        reason = ''
        if any(m['from']['id'] not in self.allowed_users for _, m, _ in members):
            reason = '发送者已移出白名单'
        elif not users:
            reason = '新闻消息分组没有接收人'
        with self.queue.db() as db:
            inserted = db.execute('INSERT OR IGNORE INTO news_package(bot,package_key,uid,sender,state,reason) VALUES(?,?,?,?,?,?)',
                (self.bot, key, uid, sender, 'media_failed' if hold_reason else 'skipped' if reason else 'preparing', hold_reason or reason)).rowcount
            if not inserted:
                return True
            for alias in {assembly_key,*sources}:
                db.execute('INSERT OR IGNORE INTO news_package_alias VALUES(?,?,?)', (self.bot, alias, key))
            for member_uid, _, _ in members:
                db.execute('INSERT OR IGNORE INTO news_plan VALUES(?,?,?)', (self.bot, member_uid, reason or '图文包准备中'))
        if reason or hold_reason:
            return True
        if incomplete:
            with self.queue.db() as db:
                db.execute("UPDATE news_package SET state='media_failed',reason='图集聚合超时，部分成员尚未确认 Butler 入库' WHERE bot=? AND package_key=?", (self.bot, key))
            return True
        items, seen = [], set()
        try:
            for _, message, _ in sorted(members, key=lambda m: (self._member_order(m[1]), m[0])):
                member_identity = self._source_key(message) or str(message['message_id'])
                if member_identity in seen:
                    continue
                seen.add(member_identity)
                parts, skip = format_news(message, media_enabled=True,
                    include_text=getattr(settings, 'include_text', True),
                    include_source=getattr(settings, 'include_source', True),
                    include_time=getattr(settings, 'include_time', True))
                if skip:
                    raise ValueError(skip)
                if getattr(settings, 'include_text', True):
                    items.extend({'kind': 'text', 'text': part} for part in parts)
                items.extend(self.media.prepare(message))
            items = validate_items(items)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, MediaError) else '图片或图文包准备失败，保留待人工处理'
            with self.queue.db() as db:
                db.execute("UPDATE news_package SET state='media_failed',reason=? WHERE bot=? AND package_key=?", (reason, self.bot, key))
            self.log(f'新闻 update={uid}：图片准备失败，未创建部分投递')
            return True
        with self.queue.db() as db:
            db.execute("UPDATE news_package SET items=?,state='ready',reason='图文包就绪' WHERE bot=? AND package_key=?",
                       (json.dumps(items, ensure_ascii=False), self.bot, key))
            for user in users:
                request_id = 'tg-' + sha256(f'{self.bot}:{key}:{user}'.encode('utf-8')).hexdigest()
                db.execute('INSERT OR IGNORE INTO news_bundle_delivery(bot,package_key,contact,request_id) VALUES(?,?,?,?)',
                           (self.bot, key, user, request_id))
        self.log(f'新闻 update={uid}：图文包就绪，接收人={len(users)}，项目={len(items)}')
        return True

    def _deliver_bundle(self):
        with self.queue.db() as db:
            exists = db.execute("SELECT 1 FROM news_bundle_delivery WHERE bot=? AND state='pending' LIMIT 1", (self.bot,)).fetchone()
        if exists is None:
            return False
        users = read_subscribers(self.cfg.group_file_path())
        settings = self._settings()
        with self.queue.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT d.id,d.contact,d.request_id,p.items,p.sender FROM news_bundle_delivery d
                JOIN news_package p ON p.bot=d.bot AND p.package_key=d.package_key
                WHERE d.bot=? AND d.state='pending' AND p.state='ready' AND NOT EXISTS
                (SELECT 1 FROM news_bundle_delivery prev WHERE prev.bot=d.bot AND prev.contact=d.contact
                 AND prev.id<d.id AND prev.state IN ('sending','uncertain','blocked')) ORDER BY d.id LIMIT 1''', (self.bot,)).fetchone()
            if row is None:
                return False
            task, contact, request_id, serialized, sender = row
            if contact not in users or sender not in self.allowed_users or settings is None or not settings.include_images:
                db.execute("UPDATE news_bundle_delivery SET state='cancelled',reason='订阅、发送者权限或图片开关已撤销' WHERE id=?", (task,))
                return True
            if not getattr(settings, 'include_text', True) and any(item.get('kind')=='text' for item in json.loads(serialized)):
                db.execute("UPDATE news_bundle_delivery SET state='blocked',reason='正文开关已关闭；原图文包内容不变，保留待人工处理' WHERE id=?", (task,))
                return True
            db.execute("UPDATE news_bundle_delivery SET state='sending',updated=CURRENT_TIMESTAMP WHERE id=?", (task,))
        try:
            result = self.bundle_push(self.cfg, contact, json.loads(serialized), request_id)
            state, reason = result['state'], result['reason']
            if state not in ('sent', 'not_submitted', 'uncertain'):
                raise ValueError('Invalid bundle result')
        except Exception:
            state, reason = 'uncertain', '图文包提交异常，结果未知，不自动重发'
        with self.queue.db() as db:
            db.execute('UPDATE news_bundle_delivery SET state=?,reason=?,updated=CURRENT_TIMESTAMP WHERE id=?', (state, reason, task))
        self.log(f'新闻图文包 → {contact}：{state}；{reason}')
        return True
