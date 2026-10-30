"""Butler-owned, authenticated-ingress storage. Acknowledgement means committed."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def validate(body):
    if not isinstance(body, dict):
        raise ValueError('请求须为对象')
    for key in ('bot_id', 'update_id'):
        if type(body.get(key)) is not int or body[key] < (0 if key == 'update_id' else 1):
            raise ValueError('缺少有效 bot_id/update_id')
    msg = body.get('message')
    if not isinstance(msg, dict) or type(msg.get('message_id')) is not int or msg['message_id'] <= 0:
        raise ValueError('缺少有效 message_id')
    sender, chat = msg.get('from'), msg.get('chat')
    if not isinstance(sender, dict) or not isinstance(chat, dict):
        raise ValueError('缺少发送者和私聊身份')
    if (type(sender.get('id')) is not int or sender['id'] <= 0 or sender.get('is_bot')
            or chat.get('type') != 'private' or chat.get('id') != sender['id']):
        raise ValueError('仅支持真人用户私聊')
    return body


def accept(path, body):
    body = validate(body)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    if len(payload.encode('utf-8')) > 500_000:
        raise ValueError('消息过大')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=15)) as db, db:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('''CREATE TABLE IF NOT EXISTS inbox (
            id INTEGER PRIMARY KEY, bot_id INTEGER NOT NULL, update_id INTEGER NOT NULL,
            received_at TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(bot_id,update_id))''')
        old = db.execute('SELECT id,payload FROM inbox WHERE bot_id=? AND update_id=?',
                         (body['bot_id'], body['update_id'])).fetchone()
        if old and old[1] != payload:
            raise ValueError('相同 update_id 的消息内容冲突')
        inserted = db.execute('INSERT OR IGNORE INTO inbox(bot_id,update_id,received_at,payload) VALUES(?,?,?,?)',
                   (body['bot_id'], body['update_id'], datetime.now(timezone.utc).isoformat(), payload)).rowcount
        row = db.execute('SELECT id,payload FROM inbox WHERE bot_id=? AND update_id=?',
                         (body['bot_id'], body['update_id'])).fetchone()
        if row[1] != payload:
            raise ValueError('相同 update_id 的消息内容冲突')
    return {'ok': True, 'status': 'received' if inserted else 'duplicate',
            'receipt_id': row[0], 'bot_id': body['bot_id'], 'update_id': body['update_id']}


def recent(path):
    path = Path(path).resolve()
    if not path.exists():
        return []
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT id,bot_id,update_id,received_at,payload FROM inbox ORDER BY id DESC LIMIT 20').fetchall()
    result = []
    for rid, bot, update, received, payload in rows:
        msg = json.loads(payload)['message']
        result.append({'receipt_id': rid, 'bot_id': bot, 'update_id': update, 'received_at': received,
                       'sender_id': msg['from']['id'], 'message_id': msg['message_id'],
                       'text': msg.get('text') or msg.get('caption', ''),
                       'has_photo': bool(msg.get('photo')), 'media_group_id': msg.get('media_group_id')})
    return result
