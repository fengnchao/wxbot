"""Durable reception cursor and conservative per-recipient delivery receipts."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading

from butler.channels.telegram.formatting import Message


@dataclass(frozen=True)
class Delivery:
    id: int
    contact: str
    text: str
    source_id: int
    message_id: int
    part: int


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path, *, readonly=False):
        self.readonly = readonly
        self._lock = threading.RLock()
        path = Path(path).resolve()
        if readonly:
            self.db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, check_same_thread=False)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path, timeout=5, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        if not readonly:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS account (singleton INTEGER PRIMARY KEY CHECK(singleton=1), account_id INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sources (source_id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, cursor INTEGER NOT NULL, baseline INTEGER NOT NULL, scanned_at TEXT);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(source_id),
                    message_id INTEGER NOT NULL, text TEXT NOT NULL, published_at TEXT NOT NULL,
                    source_name TEXT NOT NULL, source_username TEXT NOT NULL,
                    state TEXT NOT NULL, received_at TEXT NOT NULL, UNIQUE(source_id,message_id));
                CREATE TABLE IF NOT EXISTS deliveries (
                    id INTEGER PRIMARY KEY, message_row INTEGER NOT NULL REFERENCES messages(id),
                    contact TEXT NOT NULL, part INTEGER NOT NULL, text TEXT NOT NULL,
                    state TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
                    UNIQUE(message_row,contact,part));
                CREATE TABLE IF NOT EXISTS runtime (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS pending_contact ON deliveries(contact,id,state);
            ''')

    @contextmanager
    def transaction(self):
        if self.readonly:
            raise ValueError('只读状态不能修改')
        with self._lock, self.db:
            self.db.execute('BEGIN IMMEDIATE')
            yield self.db

    def close(self):
        with self._lock:
            self.db.close()

    def bind(self, account_id, source_id, username, baseline):
        with self.transaction() as db:
            old = db.execute('SELECT account_id FROM account').fetchone()
            if old and old[0] != account_id:
                raise ValueError('Telegram 账号与已绑定账号不符')
            old_source = db.execute('SELECT source_id FROM sources WHERE username=?', (username,)).fetchone()
            old_name = db.execute('SELECT username FROM sources WHERE source_id=?', (source_id,)).fetchone()
            if (old_source and old_source[0] != source_id) or (old_name and old_name[0] != username):
                raise ValueError('Telegram 来源身份发生变化')
            db.execute('INSERT OR IGNORE INTO account VALUES(1,?)', (account_id,))
            db.execute('INSERT OR IGNORE INTO sources(source_id,username,cursor,baseline) VALUES(?,?,?,?)',
                       (source_id, username, baseline, baseline))

    def cursor(self, source_id):
        with self._lock:
            row = self.db.execute('SELECT cursor FROM sources WHERE source_id=?', (source_id,)).fetchone()
            return row[0] if row else None

    def ingest(self, source_id, messages, cursor):
        with self.transaction() as db:
            source = db.execute('SELECT cursor,baseline FROM sources WHERE source_id=?', (source_id,)).fetchone()
            if not source or cursor < source['cursor']:
                raise ValueError('扫描游标无效')
            for m in messages:
                if m.source_id != source_id or m.message_id > cursor:
                    raise ValueError('消息与扫描来源不符')
                if m.message_id <= source['baseline']:
                    continue
                db.execute('''INSERT OR IGNORE INTO messages
                    (source_id,message_id,text,published_at,source_name,source_username,state,received_at)
                    VALUES(?,?,?,?,?,?,?,?)''', (m.source_id, m.message_id, m.text, m.published_at.isoformat(),
                    m.source_name, m.source_username, 'new' if m.text.strip() else 'ignored', now()))
            db.execute('UPDATE sources SET cursor=?,scanned_at=? WHERE source_id=?', (cursor, now(), source_id))

    def unexpanded(self, *, source_ids=None):
        ids = tuple(source_ids) if source_ids is not None else None
        if ids == ():
            return []
        source_filter = (' AND source_id IN (' + ','.join('?' for _ in ids) + ')') if ids is not None else ''
        with self._lock:
            rows = self.db.execute("SELECT * FROM messages WHERE state='new'" + source_filter +
                                   ' ORDER BY id LIMIT 100', ids or ()).fetchall()
            return [Message(r['source_id'], r['message_id'], r['text'], datetime.fromisoformat(r['published_at']),
                            r['source_name'], r['source_username']) for r in rows]

    def expand(self, message, contacts, parts):
        with self.transaction() as db:
            row = db.execute('SELECT id,state FROM messages WHERE source_id=? AND message_id=?',
                             (message.source_id, message.message_id)).fetchone()
            if not row or row['state'] != 'new':
                return
            if contacts and not parts:
                raise ValueError('有收件人但消息分段为空')
            for contact in dict.fromkeys(contacts):
                for number, text in enumerate(parts, 1):
                    db.execute('''INSERT INTO deliveries(message_row,contact,part,text,state,updated_at)
                        VALUES(?,?,?,?,'pending',?)''', (row['id'], contact, number, text, now()))
            db.execute('UPDATE messages SET state=? WHERE id=?', ('expanded' if contacts else 'no_subscribers', row['id']))

    def claim(self, allowed_contacts, excluded=(), *, source_ids=None):
        allowed = set(allowed_contacts)
        ids = tuple(source_ids) if source_ids is not None else None
        pending_filter = (' AND pm.source_id IN (' + ','.join('?' for _ in ids) + ')') if ids else ''
        with self.transaction() as db:
            pending = db.execute("SELECT id,contact FROM deliveries WHERE state='pending'").fetchall()
            for row in pending:
                if row['contact'] not in allowed:
                    db.execute("UPDATE deliveries SET state='skipped_removed',reason='已退出新闻分组',updated_at=? WHERE id=?", (now(), row['id']))
            if ids == ():
                return None
            rows = db.execute('''SELECT d.*,m.source_id,m.message_id FROM deliveries d
                JOIN messages m ON m.id=d.message_row WHERE d.state='pending'
                AND NOT EXISTS (SELECT 1 FROM deliveries prior JOIN messages pm ON pm.id=prior.message_row
                    WHERE prior.contact=d.contact
                    AND (prior.state IN ('sending','uncertain','not_submitted')
                        OR (prior.id<d.id AND prior.state='pending' ''' + pending_filter + ''')))
                ORDER BY d.id''', ids or ()).fetchall()
            for row in rows:
                if row['contact'] in excluded or (source_ids is not None and row['source_id'] not in source_ids):
                    continue
                db.execute("UPDATE deliveries SET state='sending',updated_at=? WHERE id=?", (now(), row['id']))
                return Delivery(row['id'], row['contact'], row['text'], row['source_id'], row['message_id'], row['part'])
            return None

    def defer(self, delivery_id):
        """Only called before a claimed task has made any HTTP request."""
        with self.transaction() as db:
            db.execute("UPDATE deliveries SET state='pending',updated_at=? WHERE id=? AND state='sending'", (now(), delivery_id))

    def finish(self, delivery_id, state, reason):
        if state not in ('sent', 'not_submitted', 'uncertain', 'skipped_removed'):
            raise ValueError('投递结果状态无效')
        with self.transaction() as db:
            db.execute("UPDATE deliveries SET state=?,reason=?,updated_at=? WHERE id=? AND state='sending'",
                       (state, reason, now(), delivery_id))

    def recover(self):
        with self.transaction() as db:
            db.execute("UPDATE deliveries SET state='uncertain',reason='上次进程在提交期间退出，须人工核对',updated_at=? WHERE state='sending'", (now(),))

    def runtime(self, key, value):
        with self.transaction() as db:
            db.execute('INSERT OR REPLACE INTO runtime VALUES(?,?)', (key, str(value)))

    def status(self):
        with self._lock:
            return {
                'account_id': (r[0] if (r := self.db.execute('SELECT account_id FROM account').fetchone()) else None),
                'sources': [dict(r) for r in self.db.execute('SELECT * FROM sources ORDER BY source_id')],
                'messages': dict(self.db.execute('SELECT state,COUNT(*) FROM messages GROUP BY state').fetchall()),
                'deliveries': dict(self.db.execute('SELECT state,COUNT(*) FROM deliveries GROUP BY state').fetchall()),
                'message_results': [dict(r) for r in self.db.execute('''
                    WITH per_contact AS (
                        SELECT message_row,contact,MIN(state='sent') AS complete
                        FROM deliveries GROUP BY message_row,contact)
                    SELECT m.source_id,m.message_id,m.state,COUNT(p.contact) AS planned_recipients,
                           COALESCE(SUM(p.complete),0) AS completed_recipients
                    FROM messages m LEFT JOIN per_contact p ON p.message_row=m.id
                    GROUP BY m.id ORDER BY m.id DESC LIMIT 100''')],
                'receipts': [dict(r) for r in self.db.execute('''SELECT d.id,d.contact,d.part,d.state,d.reason,d.updated_at,m.source_id,m.message_id
                    FROM deliveries d JOIN messages m ON m.id=d.message_row ORDER BY d.id DESC LIMIT 100''')],
                'runtime': dict(self.db.execute('SELECT key,value FROM runtime').fetchall()),
            }
