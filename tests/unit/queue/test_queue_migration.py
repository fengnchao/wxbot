import sqlite3

import pytest

from wxbot import queue_schema
from wxbot.queue_store import Incoming, QueueStore


def legacy(path, submitted=True):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE observations(contact TEXT PRIMARY KEY,snapshot TEXT,group_mode INTEGER,updated_at REAL)')
        db.execute('CREATE TABLE pending_sessions(contact TEXT PRIMARY KEY,unread_count INTEGER,mentioned INTEGER,updated_at REAL)')
        db.execute('CREATE TABLE inbox(id INTEGER PRIMARY KEY AUTOINCREMENT,contact TEXT,text TEXT,member_key TEXT,context TEXT,group_mode INTEGER,received_at REAL,batch_id TEXT)')
        db.execute('CREATE TABLE batches(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,contact TEXT,text TEXT,context TEXT,state TEXT,created_at REAL,started_at REAL,finished_at REAL,attempts INTEGER,error TEXT)')
        db.execute('CREATE TABLE outbox(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,contact TEXT,text TEXT,batch_id TEXT UNIQUE REFERENCES batches(id),state TEXT,created_at REAL,not_before REAL,baseline TEXT,submitted_at REAL,finished_at REAL,error TEXT' + (',submitted_text TEXT' if submitted else '') + ')')
        for n, state in enumerate(('pending','sending','confirming','sent','skipped','blocked','uncertain'), 1):
            db.execute('INSERT INTO batches VALUES(?,?,?,?,?,?,?,?,?,?,?)', (n, f'b{n}', 'A', 'in', '', 'waiting_delivery', 1, 2, 3, 4, 'old'))
            values = (n, f'd{n}', 'A','原文',f'b{n}',state,1,2,'[]',3,4,'old') + (('实际',) if submitted else ())
            db.execute('INSERT INTO outbox VALUES(' + ','.join('?' for _ in values) + ')', values)
        db.execute("UPDATE sqlite_sequence SET seq=100 WHERE name='outbox'")


@pytest.mark.parametrize('submitted', [True,False])
def test_migration_preserves_states_fields_ids_and_high_watermark(tmp_path, submitted):
    path = tmp_path / 'old.db'
    legacy(path, submitted)
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        old = [dict(r) for r in db.execute('SELECT * FROM outbox')]
    store = QueueStore(path)
    try:
        for before, after in zip(old, store.records('outbox')):
            assert all(after[k] == v for k,v in before.items())
            assert after['part_seq'] == 1
        new = store.enqueue_delivery('B','new',now=10)
        assert store.get_delivery(new)['seq'] == 101
        assert store.get_batch('b1')['part_count'] == 1
    finally:
        store.close()


def test_readonly_legacy_no_migration_admin_rejected(tmp_path):
    path = tmp_path / 'old.db'
    legacy(path)
    before = path.read_bytes()
    reader = QueueStore(path, access='readonly')
    assert reader.records('outbox')[0]['part_seq'] == 1
    reader.close()
    assert path.read_bytes() == before
    assert not path.with_name('old.db.lock').exists()
    with pytest.raises(ValueError, match='旧|升级'):
        QueueStore(path, access='admin')


def test_failure_rolls_back_whole_migration_and_releases_lock(tmp_path, monkeypatch):
    path = tmp_path / 'old.db'
    legacy(path)
    with sqlite3.connect(path) as db:
        before = list(db.execute("SELECT name,sql FROM sqlite_master ORDER BY name"))
    original = queue_schema.OUTBOX_SQL
    monkeypatch.setattr(queue_schema,'OUTBOX_SQL', 'invalid ddl')
    with pytest.raises(sqlite3.DatabaseError):
        QueueStore(path)
    with sqlite3.connect(path) as db:
        assert list(db.execute("SELECT name,sql FROM sqlite_master ORDER BY name")) == before
        assert db.execute('SELECT count(*) FROM outbox').fetchone()[0] == 7
    monkeypatch.setattr(queue_schema,'OUTBOX_SQL', original)
    QueueStore(path).close()


def test_runtime_lock_before_any_schema_changes(tmp_path):
    path = tmp_path / 'queue.db'
    first = QueueStore(path)
    first.acquire_runtime()
    with pytest.raises(RuntimeError):
        QueueStore(path)
    first.close()


def batch(store, contact, parts):
    store.capture(contact, [], [Incoming('hi')],now=0)
    store.prepare(quiet=0,max_wait=10,prefix='/',now=0)
    b = store.claim_batch(now=0)
    store.finish_batch_parts(b.id, tuple(parts), now=0, reply_text=''.join(parts))
    return b


def test_fair_parts_restart_and_parent_completion(tmp_path):
    path = tmp_path / 'q.db'
    store = QueueStore(path)
    a = batch(store,'A',['a1','a2','a3'])
    b = batch(store,'B',['b1','b2'])
    order=[]
    for i in range(5):
        assert store.has_ready_delivery(now=0)
        d=store.claim_delivery(now=0)
        order.append(d.text)
        store.finish_delivery(d.id,'sent',now=i)
        if i == 0:
            assert store.get_batch(a.id)['state'] == 'waiting_delivery'
        if i == 1:
            store.close()
            store=QueueStore(path,restart_chat_policy='resume')
            store.recover()
    assert order == ['a1','b1','a2','b2','a3']
    assert store.get_batch(a.id)['state'] == store.get_batch(b.id)['state'] == 'done'
    store.close()


def test_late_user_and_manual_resolve_do_not_resume_abandoned_parts():
    s=QueueStore(':memory:')
    a=batch(s,'A',['a1','a2','a3'])
    first=s.claim_delivery(now=0)
    s.finish_delivery(first.id,'sent',now=1)
    batch(s,'B',['b1'])
    b=s.claim_delivery(now=0)
    assert b.text == 'b1'
    s.finish_delivery(b.id,'sent',now=2)
    second=s.claim_delivery(now=0)
    s.finish_delivery(second.id,'uncertain',now=3)
    assert not s.has_ready_delivery(now=4)
    s.resolve(second.id, delivery=True,sent=True,now=4)
    assert s.get_batch(a.id)['state'] == 'done'
    assert s.claim_delivery(now=4) is None
    assert s.records('outbox')[2]['state']=='skipped'


def test_empty_legacy_preserves_deleted_sequence_high_watermark(tmp_path):
    path=tmp_path/'old.db'
    legacy(path)
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM outbox')
    s=QueueStore(path)
    try:
        key=s.enqueue_delivery('A','new',now=0)
        assert s.get_delivery(key)['seq']==101
    finally:
        s.close()


def test_all_parts_atomic_and_duplicate_rejected(monkeypatch):
    s=QueueStore(':memory:')
    s.capture('A',[],[Incoming('hi')],now=0)
    s.prepare(quiet=0,max_wait=10,prefix='/',now=0)
    b=s.claim_batch(now=0)
    original=s._insert_delivery
    def fail_second(db,*args,**kw):
        if args[-1]==2:
            raise RuntimeError('insertion failure')
        return original(db,*args,**kw)
    monkeypatch.setattr(s,'_insert_delivery',fail_second)
    with pytest.raises(RuntimeError):
        s.finish_batch_parts(b.id,('one','two'),now=1)
    assert s.records('outbox')==[]
    assert s.get_batch(b.id)['state']=='processing'
    monkeypatch.setattr(s,'_insert_delivery',original)
    s.finish_batch_parts(b.id,('one','two'),now=2)
    with pytest.raises(ValueError):
        s.finish_batch_parts(b.id,('one','two'),now=3)
    assert len(s.records('outbox'))==2


def test_recover_keeps_done_timestamp_and_terminal_update_is_idempotent():
    s=QueueStore(':memory:')
    b=batch(s,'A',['one'])
    d=s.claim_delivery(now=0)
    s.finish_delivery(d.id,'sent',now=7)
    turns=list(s._db.execute('SELECT * FROM delivery_turns'))
    s.finish_delivery(d.id,'sent',now=8)
    assert list(s._db.execute('SELECT * FROM delivery_turns'))==turns
    s.recover()
    assert s.get_batch(b.id)['finished_at']==7


def test_v2_upgrade_backfills_failure_without_replacing_original_fields(tmp_path):
    path=tmp_path/'v2.db'
    with sqlite3.connect(path) as db:
        for sql in queue_schema._TABLES:
            if 'delivery_events' not in sql:db.execute(sql)
        db.execute(queue_schema.OUTBOX_SQL.replace(', failed_at REAL','').replace(
            "    resolution TEXT NOT NULL DEFAULT '', ",''))
        db.execute("PRAGMA user_version=2")
        db.execute("""INSERT INTO outbox(id,contact,text,state,created_at,not_before,finished_at,error,submitted_text)
            VALUES('old-id','A','原文','blocked',1,2,10,'old failure','实际')""")
    store=QueueStore(path)
    try:
        row=store.get_delivery('old-id')
        assert row['text']=='原文' and row['submitted_text']=='实际' and row['failed_at']==10
        assert row['state']=='blocked' and row['error']=='old failure' and row['finished_at']==10
        assert queue_schema.is_latest(store._db)
        assert [r['id'] for r in store.expire_failed_deliveries(now=190)]==['old-id']
        assert 'old failure' in store.delivery_events()[-1]['reason']
    finally:store.close()
