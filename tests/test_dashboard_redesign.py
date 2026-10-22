"""Dashboard projections use temporary stores; never touch live services."""
from pathlib import Path
from contextlib import closing

from log.queue_view import QueueView
from log.flow_view import FlowView
from log.config_schema import row_metadata
from log.runtime_view import reminder_jobs
from wxbot.queue_store import QueueStore, Incoming


def test_queue_independent_offsets_and_history_order(tmp_path):
    path = tmp_path / 'queue.db'
    with closing(QueueStore(path)) as store:
        for i in range(4):
            store.capture(str(i), [], [Incoming(str(i))], now=i)
        data = QueueView(path).read(limit=1, offsets={'inbox': 2}, scope='active')
        assert data['inbox'][0]['preview'] == '2'
        assert data['pages']['inbox']['offset'] == 2
        assert data['pages']['outbox']['offset'] == 0
        store.prepare(quiet=0, max_wait=1, prefix='/', now=10)
        for i in range(4):
            batch = store.claim_batch(now=11)
            store.finish_batch_parts(batch.id, ('reply',), now=11+i)
            delivery = store.claim_delivery(now=20+i)
            store.finish_delivery(delivery.id, 'sent', now=21+i)
        history = QueueView(path).read(scope='history', limit=1)
        assert history['outbox'][0]['contact'] == '3'
        assert not history['inbox']
        assert QueueView(path).read(scope='issues')['outbox'] == []


def test_flow_order_is_applied_before_pagination(tmp_path):
    path = tmp_path / 'queue.db'
    with closing(QueueStore(path)) as store:
        for i in range(4):
            store.capture('A', [], [Incoming(str(i))], now=i)
        view = FlowView({'path':path}, [])
        first = view.read(order='asc', limit=1)
        second = view.read(order='asc', limit=1, offset=1)
        assert first['flows'][0]['preview'] == '0'
        assert second['flows'][0]['preview'] == '1'
        assert view.read(order='desc', limit=1)['flows'][0]['preview'] == '3'


def test_configuration_form_metadata_and_context_labels():
    assert row_metadata('butler', ['agent','provider'], 'codex')['choices'] == ['codex','hermes']
    assert row_metadata('wxbot', ['bot','mention_names'], ['Bot'])['widget'] == 'string-list'
    assert row_metadata('butler', ['contacts'], [])['widget'] == 'contacts'
    assert row_metadata('butler', ['codex','home'], '')['label'] == 'Codex 独立登录目录'
    assert 'Hermes' not in row_metadata('butler', ['log','flow_file'], '')['description']


def test_reminders_sorted_by_next_due_stably():
    def reminder(id, due):
        return dict(id=id, due=due, status='scheduled', contact='A', text=id, schedule='once', detail='')
    data = reminder_jobs({'backend':'codex', 'reminders':[reminder('c',30),reminder('b',10),reminder('a',10)]})
    assert [j['job_id'] for j in data['users'][0]['jobs']] == ['a','b','c']


def test_static_dashboard_assets_are_modular():
    root = Path(__file__).resolve().parents[1] / 'log'
    html = (root/'index.html').read_text(encoding='utf-8')
    assert 'assets/dashboard.css' in html
    assert 'assets/configuration.js' in html
    assert 'nav-group' in html
    assert 'id="b-contacts"' in html


def test_issue_sort_uses_failure_time_and_queue_remains_unchanged(tmp_path):
    import sqlite3
    path=tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        for name in ('A','B'):
            store.capture(name,[],[Incoming(name)],now=1)
        store.prepare(quiet=0,max_wait=1,prefix='/',now=3)
        for i in range(2):
            batch=store.claim_batch(now=4)
            store.finish_batch_parts(batch.id,('reply',),now=5)
            delivery=store.claim_delivery(now=6)
            store.finish_delivery(delivery.id,'blocked',now=20-i*10,error='failure')
        before=store.records('outbox')
        data=QueueView(path).read(scope='issues',limit=1,now=30)
        assert data['outbox'][0]['contact']=='B'
        assert not data['inbox']
        assert QueueView(path).read(scope='issues',limit=1,offsets={'outbox':1})['outbox'][0]['contact']=='A'
        assert store.records('outbox')==before


def test_runtime_reminders_choose_earliest_before_limit(tmp_path):
    from butler.business import BusinessStore
    store=BusinessStore(tmp_path/'business.db')
    with store.transaction() as db:
        # More than one page; the earliest scheduled reminder must survive LIMIT.
        for i in range(205):
            db.execute('INSERT INTO reminders(id,owner,contact,text,schedule,due,status,detail) VALUES(?,?,?,?,?,?,?,?)',
                       (f'r{i:03}','a','A','test','in 1m',i,'scheduled',''))
    rows=store.reminders(order='due')
    assert len(rows)==200 and rows[0]['id']=='r000' and rows[-1]['id']=='r199'
