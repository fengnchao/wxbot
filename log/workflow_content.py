"""Read one selected message's full content; never load bodies on every poll."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import tomllib


def read_content(queue_path, telegram_config, record_id):
    if not isinstance(record_id, str) or not record_id or len(record_id) > 160:
        raise ValueError('消息标识无效')
    telegram = re.fullmatch(r'tg:([0-9]{1,19}):([0-9]{1,19})', record_id)
    inbox = re.fullmatch(r'inbox:([0-9]{1,19})', record_id)
    push = re.fullmatch(r'push:([A-Za-z0-9:_-]{1,128})', record_id)
    batch = re.fullmatch(r'[A-Za-z0-9_-]{1,128}', record_id)
    if not (telegram or inbox or push or batch):
        raise ValueError('消息标识无效')
    numbers = tuple(map(int, telegram.groups() if telegram else inbox.groups() if inbox else ()))
    if any(value > 2**63-1 for value in numbers) or (numbers and numbers[0] <= 0):
        raise ValueError('消息标识无效')
    if telegram:
        if telegram_config is None or not Path(telegram_config).is_file():
            return None
        config_path = Path(telegram_config).resolve()
        config = tomllib.loads(config_path.read_text(encoding='utf-8-sig'))['telegram_bot']
        path = (config_path.parent / config.get('state_dir', 'data/telegram-bot') / 'relay.sqlite3').resolve()
    else:
        path = Path(queue_path).resolve()
    if not path.is_file():
        return None
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        if telegram:
            row = db.execute('SELECT payload FROM pending WHERE bot=? AND uid=?', numbers).fetchone()
            if row is None:
                return None
            message = json.loads(row['payload'])['message']
            text = message.get('text') or message.get('caption') or ''
            token = config.get('token')
            if isinstance(token,str) and token:
                text = text.replace(token,'[密钥已隐藏]')
            return {'id':record_id, 'kind':'telegram',
                    'text':text, 'reply_text':''}
        if inbox:
            row = db.execute('SELECT text FROM inbox WHERE id=?', numbers).fetchone()
            kind = 'inbox'
        elif push:
            row = db.execute('SELECT text FROM outbox WHERE id=? AND batch_id IS NULL', push.groups()).fetchone()
            kind = 'push'
        else:
            row = db.execute('SELECT * FROM batches WHERE id=?', (record_id,)).fetchone()
            kind = 'batch'
        if row is None:
            return None
        reply = ''
        if kind == 'batch':
            reply = row['reply_text'] if 'reply_text' in row.keys() else None
            if reply is None:
                reply = ''.join(part[0] for part in db.execute(
                    'SELECT text FROM outbox WHERE batch_id=? ORDER BY seq', (record_id,)))
        return {'id':record_id, 'kind':kind, 'text':row['text'], 'reply_text':reply}
