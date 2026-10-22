"""Fresh, backend-independent business state; one connection per transaction."""
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid


def next_due(schedule, now=None):
    from croniter import croniter
    now = time.time() if now is None else now
    match = re.fullmatch(r'(?:in\s+|\+)?(\d+)\s*([smhd])', schedule.strip(), re.I)
    if match:
        delay = int(match[1]) * {'s':1, 'm':60, 'h':3600, 'd':86400}[match[2].lower()]
        if delay <= 0:
            raise ValueError('Reminder delay must be positive')
        return now + delay, False
    if len(schedule.split()) == 5 and croniter.is_valid(schedule):
        local = datetime.fromtimestamp(now).astimezone()
        return croniter(schedule, local).get_next(datetime).timestamp(), True
    try:
        due = datetime.fromisoformat(schedule).timestamp()
    except (ValueError, TypeError):
        raise ValueError('Use in 2m, an ISO date/time, or a five-field cron schedule') from None
    if due <= now:
        raise ValueError('Reminder time must be in the future')
    return due, False


class BusinessStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS sessions(scope TEXT PRIMARY KEY, thread_id TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS identities(owner TEXT PRIMARY KEY,contact TEXT,profile TEXT,uid TEXT,channel_type TEXT);
              CREATE TABLE IF NOT EXISTS memory(owner TEXT,key TEXT,value TEXT,updated REAL,
                PRIMARY KEY(owner,key));
              CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY,owner TEXT,contact TEXT,
                text TEXT,schedule TEXT,recurring INTEGER,due REAL,status TEXT,detail TEXT,
                delivery_id TEXT,created REAL);
              CREATE INDEX IF NOT EXISTS due_reminders ON reminders(status,due);
              CREATE TABLE IF NOT EXISTS operations(owner TEXT,request_id TEXT,call_id TEXT,
                fingerprint TEXT,result TEXT,PRIMARY KEY(owner,request_id,call_id));
              CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL,contact TEXT,
                stage TEXT,status TEXT,details TEXT);
            ''')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get_session(self, scope):
        with self.transaction() as db:
            row = db.execute('SELECT thread_id FROM sessions WHERE scope=?',(scope,)).fetchone()
            return row[0] if row else None

    def identify(self,owner,contact):
        with self.transaction() as db:
            db.execute('INSERT OR REPLACE INTO identities VALUES(?,?,?,?,?)',
                       (owner,contact.name,contact.profile,contact.uid,contact.channel_type))

    def last_identity(self,contact):
        with self.transaction() as db:
            row=db.execute('SELECT * FROM identities WHERE contact=? ORDER BY rowid DESC LIMIT 1',(contact,)).fetchone()
            return dict(row) if row else None

    def runtime_memory(self):
        with self.transaction() as db:
            return [dict(r) for r in db.execute('SELECT i.contact,m.key,m.value,m.updated FROM memory m '
                'LEFT JOIN identities i ON i.owner=m.owner ORDER BY m.updated DESC,m.owner,m.key LIMIT 100')]

    def set_session(self, scope, thread_id):
        with self.transaction() as db:
            db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?)',(scope,thread_id))

    def memories(self, owner, query='', *, db=None):
        if db is None:
            with self.transaction() as conn:
                return self.memories(owner, query, db=conn)
        return [dict(r) for r in db.execute('SELECT key,value,updated FROM memory WHERE owner=? '
                'AND (key LIKE ? OR value LIKE ?) ORDER BY updated DESC LIMIT 100',
                (owner,'%'+query+'%','%'+query+'%'))]

    def set_memory(self, owner, key, value, *, db=None):
        if not isinstance(key,str) or not key.strip() or len(key)>200 or not isinstance(value,str) or len(value)>10000:
            raise ValueError('Invalid memory key/value')
        if db is None:
            with self.transaction() as conn:
                return self.set_memory(owner,key,value,db=conn)
        db.execute('INSERT OR REPLACE INTO memory VALUES(?,?,?,?)',(owner,key,value,time.time()))
        return {'ok':True}

    def reminders(self, owner=None, *, db=None, order='recent'):
        if db is None:
            with self.transaction() as conn:
                return self.reminders(owner,db=conn,order=order)
        sql='SELECT * FROM reminders'
        sorting="CASE WHEN status IN ('scheduled','delivering') THEN 0 WHEN status='failed' THEN 1 ELSE 2 END,due ASC,id ASC" if order=='due' else 'due DESC,id DESC'
        return [dict(r) for r in db.execute(sql+(' WHERE owner=?' if owner is not None else '')+f' ORDER BY {sorting} LIMIT 200',
                                           (owner,) if owner is not None else ())]

    def create_reminder(self, owner, contact, text, schedule, *, db):
        if not isinstance(text,str) or not text.strip() or len(text)>10000 or not isinstance(schedule,str):
            raise ValueError('Invalid reminder text/schedule')
        due, recurring = next_due(schedule)
        rid = uuid.uuid4().hex
        db.execute('INSERT INTO reminders VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (rid,owner,contact,text,schedule,int(recurring),due,'scheduled','',None,time.time()))
        return {'ok':True,'id':rid,'due':due,'recurring':recurring}

    def cancel_reminder(self, owner, rid, *, db):
        row = db.execute('SELECT owner,status FROM reminders WHERE id=?',(rid,)).fetchone()
        if not row or row['owner'] != owner:
            raise PermissionError('Reminder does not belong to this identity')
        if row['status'] in ('delivering','sent'):
            raise ValueError('Reminder is already '+row['status']+'; check delivery status before taking further action')
        db.execute("UPDATE reminders SET status='cancelled' WHERE id=?",(rid,))
        return {'ok':True,'id':rid}

    def claim_due(self, now=None, *, limit=20):
        now = time.time() if now is None else now
        with self.transaction() as db:
            rows=[dict(r) for r in db.execute("SELECT * FROM reminders WHERE status='scheduled' AND due<=? ORDER BY due LIMIT ?",(now,min(20,max(1,int(limit)))))]
            for row in rows:
                row['delivery_id'] = uuid.uuid4().hex
                db.execute("UPDATE reminders SET status='delivering',delivery_id=? WHERE id=?",(row['delivery_id'],row['id']))
            return rows

    def recover_deliveries(self):
        with self.transaction() as db:
            db.execute("UPDATE reminders SET status='failed',detail='Process stopped during delivery; check manually before retrying' WHERE status='delivering'")

    def finish_reminder(self, rid, ok, detail, now=None):
        now=time.time() if now is None else now
        with self.transaction() as db:
            row=db.execute('SELECT * FROM reminders WHERE id=?',(rid,)).fetchone()
            if not row or row['status'] != 'delivering':
                return
            due=row['due']
            status='sent' if ok else 'failed'
            if ok and row['recurring']:
                due,_=next_due(row['schedule'],now)
                status='scheduled'
            db.execute('UPDATE reminders SET status=?,detail=?,due=? WHERE id=?',(status,str(detail)[:500],due,rid))

    def event(self, contact, stage, status, **details):
        with self.transaction() as db:
            db.execute('INSERT INTO events(at,contact,stage,status,details) VALUES(?,?,?,?,?)',
                       (time.time(),contact,stage,status,json.dumps(details,ensure_ascii=False)))

    def events(self, limit=100):
        with self.transaction() as db:
            return [dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?',(min(200,max(1,int(limit))),))]
