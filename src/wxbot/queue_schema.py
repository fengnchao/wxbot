"""Queue schema creation and atomic legacy migration. No service/UI access."""
import sqlite3
import time
from contextlib import closing
from pathlib import Path

VERSION = 10


def backup_before_migration(db, path):
    """Snapshot an existing queue before PRAGMAs/DDL, including its WAL."""
    if path == ':memory:' or is_latest(db):
        return
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
        return
    if db.execute('PRAGMA user_version').fetchone()[0] > VERSION:
        raise ValueError('队列版本较新，不能用旧版程序打开')
    target = Path(str(path) + '.backup-' + str(time.time_ns()))
    with closing(sqlite3.connect(target)) as backup:
        db.backup(backup)

OUTBOX_SQL = """CREATE TABLE outbox (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
    contact TEXT NOT NULL, text TEXT NOT NULL,
    batch_id TEXT REFERENCES batches(id), state TEXT NOT NULL,
    created_at REAL NOT NULL, not_before REAL NOT NULL,
    baseline TEXT, submitted_at REAL, finished_at REAL,
    error TEXT NOT NULL DEFAULT '', submitted_text TEXT,
    part_seq INTEGER NOT NULL DEFAULT 1, failed_at REAL,
    resolution TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'text',
    retries INTEGER NOT NULL DEFAULT 0,
    UNIQUE(batch_id,part_seq))"""

_TABLES = (
    """CREATE TABLE IF NOT EXISTS delivery_packages (
        id TEXT PRIMARY KEY, contact TEXT NOT NULL, request_id TEXT NOT NULL,
        payload_hash TEXT NOT NULL, created_at REAL NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending', UNIQUE(contact,request_id))""",
    """CREATE TABLE IF NOT EXISTS group_member_names (
        contact TEXT NOT NULL, member_key TEXT NOT NULL, name TEXT NOT NULL,
        updated_at REAL NOT NULL, PRIMARY KEY(contact, member_key))""",
    """CREATE TABLE IF NOT EXISTS observations (
        contact TEXT PRIMARY KEY, snapshot TEXT NOT NULL,
        group_mode INTEGER NOT NULL, updated_at REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS pending_sessions (
        contact TEXT PRIMARY KEY, unread_count INTEGER NOT NULL,
        mentioned INTEGER NOT NULL, updated_at REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS batches (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
        contact TEXT NOT NULL, text TEXT NOT NULL, context TEXT NOT NULL,
        member_key TEXT NOT NULL DEFAULT '', member_name TEXT NOT NULL DEFAULT '',
        reply_mode TEXT NOT NULL DEFAULT 'text',
        state TEXT NOT NULL, created_at REAL NOT NULL, started_at REAL,
        finished_at REAL, attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
        reply_text TEXT, reply_complete INTEGER NOT NULL DEFAULT 0, part_count INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS inbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT, contact TEXT NOT NULL,
        text TEXT NOT NULL, member_key TEXT NOT NULL, member_name TEXT NOT NULL DEFAULT '',
        reply_mode TEXT NOT NULL DEFAULT 'text',
        context TEXT NOT NULL, group_mode INTEGER NOT NULL, received_at REAL NOT NULL,
        batch_id TEXT REFERENCES batches(id))""",
    """CREATE TABLE IF NOT EXISTS delivery_turns (contact TEXT PRIMARY KEY, last_turn INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS delivery_events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL,
        record_kind TEXT NOT NULL, contact TEXT NOT NULL, action TEXT NOT NULL,
        at REAL NOT NULL, state TEXT NOT NULL, reason TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL)""",
)


def columns(db, table):
    return {r[1] for r in db.execute(f'PRAGMA table_info({table})')}


def is_latest(db):
    return (db.execute('PRAGMA user_version').fetchone()[0] == VERSION and
            {'part_seq', 'submitted_text', 'failed_at', 'resolution', 'kind', 'retries', 'detached', 'draft_text', 'manual_required', 'mention_name', 'package_id', 'media_id', 'media_path'} <= columns(db, 'outbox') and
            bool(columns(db, 'delivery_packages')) and
            bool(columns(db, 'delivery_events')) and bool(columns(db, 'group_member_names')) and
            {'reply_text', 'reply_complete', 'part_count', 'member_key', 'member_name', 'reply_mode', 'first_delivery_failure', 'delivery_resolution', 'avatar', 'reply_reason'} <= columns(db, 'batches') and
            {'member_name', 'reply_mode', 'avatar', 'reply_reason'} <= columns(db, 'inbox'))


def initialize(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version > VERSION:
        raise ValueError('队列版本较新，不能用旧版程序打开')
    db.execute('BEGIN IMMEDIATE')
    try:
        for sql in _TABLES:
            db.execute(sql)
        existing = columns(db, 'outbox')
        if existing and 'part_seq' not in existing:
            high = db.execute("SELECT seq FROM sqlite_sequence WHERE name='outbox'").fetchone()
            db.execute('ALTER TABLE outbox RENAME TO outbox_legacy')
            db.execute(OUTBOX_SQL)
            fields = ('seq,id,contact,text,batch_id,state,created_at,not_before,baseline,'
                      'submitted_at,finished_at,error')
            submitted = 'submitted_text' if 'submitted_text' in existing else 'NULL'
            db.execute(f'INSERT INTO outbox({fields},submitted_text,part_seq) SELECT {fields},{submitted},1 FROM outbox_legacy')
            db.execute('DROP TABLE outbox_legacy')
            if high:
                db.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='outbox'", (high[0],))
        elif not existing:
            db.execute(OUTBOX_SQL)
        elif 'submitted_text' not in existing:
            db.execute('ALTER TABLE outbox ADD COLUMN submitted_text TEXT')
        existing = columns(db, 'outbox')
        for name,declaration in (('failed_at','REAL'),('resolution',"TEXT NOT NULL DEFAULT ''"),
                                 ('kind',"TEXT NOT NULL DEFAULT 'text'"),
                                 ('retries',"INTEGER NOT NULL DEFAULT 0"),
                                 ('detached','INTEGER NOT NULL DEFAULT 0'),
                                 ('manual_required','INTEGER NOT NULL DEFAULT 0'),
                                 ('mention_name',"TEXT NOT NULL DEFAULT ''"),
                                 ('package_id','TEXT REFERENCES delivery_packages(id)'),
                                 ('media_id',"TEXT NOT NULL DEFAULT ''"),
                                 ('media_path',"TEXT NOT NULL DEFAULT ''"),
                                 ('draft_text','TEXT')):
            if name not in existing:
                db.execute(f'ALTER TABLE outbox ADD COLUMN {name} {declaration}')
        if 'failed_at' not in existing:
            db.execute("""UPDATE outbox SET failed_at=COALESCE(finished_at,submitted_at,created_at)
                WHERE failed_at IS NULL AND state IN ('blocked','uncertain')""")
        batch_cols = columns(db, 'batches')
        for name, declaration in (('reply_text','TEXT'), ('reply_complete','INTEGER NOT NULL DEFAULT 0'),
                                  ('part_count','INTEGER NOT NULL DEFAULT 0'),
                                  ('member_key',"TEXT NOT NULL DEFAULT ''"),
                                  ('member_name',"TEXT NOT NULL DEFAULT ''"),
                                  ('reply_mode',"TEXT NOT NULL DEFAULT 'text'"),
                                  ('avatar',"TEXT NOT NULL DEFAULT ''"),
                                  ('reply_reason',"TEXT NOT NULL DEFAULT ''"),
                                  ('first_delivery_failure','REAL'),
                                  ('delivery_resolution',"TEXT NOT NULL DEFAULT ''")):
            if name not in batch_cols:
                db.execute(f'ALTER TABLE batches ADD COLUMN {name} {declaration}')
        inbox_cols = columns(db, 'inbox')
        for name, declaration in (('member_name',"TEXT NOT NULL DEFAULT ''"),
                                  ('avatar',"TEXT NOT NULL DEFAULT ''"),
                                  ('reply_reason',"TEXT NOT NULL DEFAULT ''"),
                                  ('reply_mode',"TEXT NOT NULL DEFAULT 'text'")):
            if name not in inbox_cols:
                db.execute(f'ALTER TABLE inbox ADD COLUMN {name} {declaration}')
        if 'reply_complete' not in batch_cols:
            db.execute("""UPDATE batches SET
                reply_text=(SELECT text FROM outbox WHERE batch_id=batches.id),
                part_count=(SELECT count(*) FROM outbox WHERE batch_id=batches.id),
                reply_complete=CASE WHEN state='done' OR EXISTS
                    (SELECT 1 FROM outbox WHERE batch_id=batches.id) THEN 1 ELSE 0 END""")
        for sql in ('CREATE INDEX IF NOT EXISTS inbox_unbatched ON inbox(contact,batch_id,id)',
                    'CREATE INDEX IF NOT EXISTS batches_state ON batches(state,seq)',
                    'CREATE INDEX IF NOT EXISTS outbox_state ON outbox(state,seq)',
                    'CREATE INDEX IF NOT EXISTS delivery_events_contact ON delivery_events(contact,seq)'):
            db.execute(sql)
        db.execute('''UPDATE batches SET first_delivery_failure=(SELECT MIN(failed_at) FROM outbox WHERE batch_id=batches.id)
            WHERE first_delivery_failure IS NULL''')
        if version < 9:
            # Legacy hashes/names do not prove a registry binding. Keep original
            # text intact and require review. Never touch started/uncertain rows.
            db.execute("""UPDATE outbox SET state='blocked',manual_required=1,
                error='旧版群回复包含文本 @ 前缀，缺少已确认绑定，请人工核对',
                failed_at=COALESCE(failed_at,created_at)
                WHERE state='pending' AND batch_id IS NOT NULL AND part_seq=1
                AND submitted_at IS NULL AND submitted_text IS NULL AND baseline IS NULL
                AND draft_text IS NULL AND text LIKE '@%'
                AND EXISTS(SELECT 1 FROM inbox WHERE inbox.batch_id=outbox.batch_id AND group_mode=1)""")
        db.execute(f'PRAGMA user_version={VERSION}')
        db.commit()
    except BaseException:
        db.rollback()
        raise
