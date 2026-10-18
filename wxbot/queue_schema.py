"""Queue schema creation and atomic legacy migration. No service/UI access."""
VERSION = 3

OUTBOX_SQL = """CREATE TABLE outbox (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
    contact TEXT NOT NULL, text TEXT NOT NULL,
    batch_id TEXT REFERENCES batches(id), state TEXT NOT NULL,
    created_at REAL NOT NULL, not_before REAL NOT NULL,
    baseline TEXT, submitted_at REAL, finished_at REAL,
    error TEXT NOT NULL DEFAULT '', submitted_text TEXT,
    part_seq INTEGER NOT NULL DEFAULT 1, failed_at REAL,
    resolution TEXT NOT NULL DEFAULT '', UNIQUE(batch_id,part_seq))"""

_TABLES = (
    """CREATE TABLE IF NOT EXISTS observations (
        contact TEXT PRIMARY KEY, snapshot TEXT NOT NULL,
        group_mode INTEGER NOT NULL, updated_at REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS pending_sessions (
        contact TEXT PRIMARY KEY, unread_count INTEGER NOT NULL,
        mentioned INTEGER NOT NULL, updated_at REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS batches (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
        contact TEXT NOT NULL, text TEXT NOT NULL, context TEXT NOT NULL,
        state TEXT NOT NULL, created_at REAL NOT NULL, started_at REAL,
        finished_at REAL, attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
        reply_text TEXT, reply_complete INTEGER NOT NULL DEFAULT 0, part_count INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS inbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT, contact TEXT NOT NULL,
        text TEXT NOT NULL, member_key TEXT NOT NULL, context TEXT NOT NULL,
        group_mode INTEGER NOT NULL, received_at REAL NOT NULL,
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
            {'part_seq', 'submitted_text', 'failed_at', 'resolution'} <= columns(db, 'outbox') and
            bool(columns(db, 'delivery_events')) and
            {'reply_text', 'reply_complete', 'part_count'} <= columns(db, 'batches'))


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
        for name,declaration in (('failed_at','REAL'),('resolution',"TEXT NOT NULL DEFAULT ''")):
            if name not in existing:
                db.execute(f'ALTER TABLE outbox ADD COLUMN {name} {declaration}')
        db.execute("""UPDATE outbox SET failed_at=COALESCE(finished_at,submitted_at,created_at)
            WHERE failed_at IS NULL AND state IN ('blocked','uncertain')""")
        batch_cols = columns(db, 'batches')
        for name, declaration in (('reply_text','TEXT'), ('reply_complete','INTEGER NOT NULL DEFAULT 0'),
                                  ('part_count','INTEGER NOT NULL DEFAULT 0')):
            if name not in batch_cols:
                db.execute(f'ALTER TABLE batches ADD COLUMN {name} {declaration}')
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
        db.execute(f'PRAGMA user_version={VERSION}')
        db.commit()
    except BaseException:
        db.rollback()
        raise
