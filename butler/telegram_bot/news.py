"""Turn saved bot messages into news deliveries using the existing Butler API."""
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.parse import urlsplit

from butler.push_client import push_news
from butler.telegram.service import read_subscribers


def format_news(message):
    """Return text parts and a skip reason. Media remains explicit, never silently lost."""
    text = message.get('text') or message.get('caption') or ''
    if not isinstance(text, str):
        return [], '正文格式无效'
    text = text.strip()
    if re.match(r'^/[A-Za-z][A-Za-z0-9_]*(?:@\w+)?(?:\s|$)', text):
        return [], '机器人命令不作为新闻转发'
    if not text:
        return [], '无文字正文；纯图片或其他媒体尚未接通微信发送'
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
    if any(message.get(key) for key in ('photo', 'document', 'video', 'animation', 'audio', 'voice', 'sticker')):
        text += '\n\n[本条含媒体附件，当前仅转发文字和链接]'
    stamp = message.get('date')
    try:
        date = datetime.fromtimestamp(stamp, timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError, OverflowError, OSError):
        date = '时间未知'
    header = f'【新闻消息】{title}\n{date}'
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
    return [header + (f'（{i}/{len(chunks)}）' if len(chunks) > 1 else '') + '\n\n' + chunk
            for i, chunk in enumerate(chunks, 1)], ''


class NewsRelay:
    def __init__(self, queue, bot, cfg, allowed_users, log, *, push=push_news):
        self.queue, self.bot, self.cfg = queue, bot, cfg
        self.allowed_users, self.log, self.push = allowed_users, log, push

    def recover(self):
        with self.queue.db() as db:
            db.execute("UPDATE news_delivery SET state='uncertain',reason='提交中断，结果未知，不自动重发',updated=CURRENT_TIMESTAMP WHERE bot=? AND state='sending'", (self.bot,))

    def expand_once(self):
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
            parts, reason = format_news(msg)
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
            if contact not in users or json.loads(payload)['message']['from']['id'] not in self.allowed_users:
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
