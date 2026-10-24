"""Persist updates and the polling cursor in one transaction."""
from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3


class Queue:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cursor(bot INTEGER PRIMARY KEY,offset INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS pending(bot INTEGER,uid INTEGER,payload TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',error TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(bot,uid));
                CREATE TABLE IF NOT EXISTS news_plan(bot INTEGER,uid INTEGER,reason TEXT,
                    PRIMARY KEY(bot,uid));
                CREATE TABLE IF NOT EXISTS news_delivery(id INTEGER PRIMARY KEY,bot INTEGER,uid INTEGER,
                    contact TEXT,part INTEGER,text TEXT,state TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT NOT NULL DEFAULT '',updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(bot,uid,contact,part));''')

    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.execute('PRAGMA synchronous=FULL')
            yield db

    def offset(self, bot):
        with self.db() as db:
            row = db.execute('SELECT offset FROM cursor WHERE bot=?', (bot,)).fetchone()
            return row[0] if row else 0

    def ingest(self, bot, update, message):
        uid = update['update_id']
        if type(uid) is not int or uid < 0:
            raise ValueError('Invalid update id')
        with self.db() as db:
            if message is not None:
                payload = json.dumps({'bot_id': bot, 'update_id': uid, 'message': message}, ensure_ascii=False)
                db.execute('INSERT OR IGNORE INTO pending(bot,uid,payload) VALUES(?,?,?)', (bot, uid, payload))
            db.execute('INSERT INTO cursor VALUES(?,?) ON CONFLICT(bot) DO UPDATE SET offset=max(offset,excluded.offset)',
                       (bot, uid + 1))

    def next(self, bot):
        with self.db() as db:
            row = db.execute("SELECT payload FROM pending WHERE bot=? AND state='pending' ORDER BY uid LIMIT 1", (bot,)).fetchone()
        return json.loads(row[0]) if row else None

    def finish(self, bot, uid, state, error=''):
        with self.db() as db:
            db.execute('UPDATE pending SET state=?,error=? WHERE bot=? AND uid=?', (state, error, bot, uid))
