"""Workflow uses durable facts, exact identities and bounded history; never sends."""
import json
import sqlite3
from contextlib import closing

from dashboard.workflow_view import WorkflowView
from wxbot.queue_store import QueueStore, Incoming


def view(path, trace=None):
    return WorkflowView({'path': path, 'failure_timeout_seconds': 180}, [trace] if trace else [],
                        contacts=[{'name': '群', 'uid': 'group-uid', 'channel_type': 'group'}], backend='codex')


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path/'missing.db'
    assert view(path).read()['status'] == 'missing'
    assert not path.exists()


def test_group_identity_and_merge_replaces_inbox_cards(tmp_path):
    path = tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        store.capture('群', [], [Incoming('hello', member_key='member-1'), Incoming('question', member_key='member-1')], group_mode=True, now=1)
        before = view(path).read(now=2)
        assert len(before['messages']) == 2
        assert before['messages'][0]['uid'] == 'group-uid'
        assert before['messages'][0]['members'] == ['member-1']
        assert before['messages'][0]['stage'] == 1
        assert any(e['stage']=='wxbot_inbox' and e['node']==1 for e in before['messages'][0]['events'])
        store.prepare(quiet=0, max_wait=1, prefix='/', now=3)
        after = view(path).read(now=4)
        assert len(after['messages']) == 1
        assert len(after['messages'][0]['inbox_ids']) == 2
        assert after['messages'][0]['request_id']
        assert after['messages'][0]['uid'] == before['messages'][0]['uid']


def test_only_real_model_events_advance_stage_and_failure_has_deadline(tmp_path):
    path, trace = tmp_path/'q.db', tmp_path/'trace.jsonl'
    with closing(QueueStore(path)) as store:
        store.capture('A', [], [Incoming('hello')], now=1)
        store.prepare(quiet=0, max_wait=1, prefix='/', now=2)
        batch = store.claim_batch(now=3)
        assert view(path).read(now=4)['messages'][0]['stage'] == 1
        trace.write_text(json.dumps({'event_id':'tool-1','contact':'A','request_id':batch.id,'ts':4,
                                    'stage':'hermes_tool','status':'started','tool':'memory.list'})+'\n', encoding='utf-8')
        item = view(path, trace).read(now=5)['messages'][0]
        assert item['stage'] == 3
        assert item['events'][-1]['tool'] == 'memory.list'
        with sqlite3.connect(path) as db:
            db.execute("UPDATE batches SET state='uncertain',finished_at=6,error='connection lost'")
        failed = view(path, trace).read(now=7)['messages'][0]
        assert failed['scope'] == 'issues'
        assert failed['discard_at'] == 186
        assert failed['error'] == 'connection lost'


def test_delivery_does_not_duplicate_batch_and_skipped_is_not_success(tmp_path):
    path = tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        store.capture('A', [], [Incoming('hello')], now=1)
        store.prepare(quiet=0, max_wait=1, prefix='/', now=2)
        batch = store.claim_batch(now=3)
        store.finish_batch_parts(batch.id, ('one', 'two'), now=4)
        first = store.claim_delivery(now=5)
        store.finish_delivery(first.id, 'sent', now=6)
        data = view(path).read(now=7)
        assert len(data['messages']) == 1
        item = data['messages'][0]
        assert item['stage'] == 5 and item['sent_parts'] == 1 and item['part_count'] == 2
        assert any(e['stage']=='wxbot_outbox' and e['ts']==4 for e in item['events'])
        assert next(e['ts'] for e in item['events'] if e['stage']=='wxbot_merge') == 2
        second = store.claim_delivery(now=20)
        store.finish_delivery(second.id, 'skipped', now=21, error='discarded')
        done = view(path).read(now=22)['messages'][0]
        assert done['scope'] == 'issues' and done['status'] == 'discarded'
        assert done['terminal'] is True
        assert view(path).read(now=22)['counts']['sent'] == 1
        assert next(e['ts'] for e in done['events'] if e['stage']=='wxbot_merge') == 2


def test_old_active_survives_new_history_and_reads_never_mutate(tmp_path):
    path = tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        store.capture('old-active', [], [Incoming('waiting')], now=1)
        with sqlite3.connect(path) as db:
            for i in range(100):
                db.execute("INSERT INTO batches(id,contact,text,context,state,created_at,finished_at,reply_complete) VALUES(?,?,?,'','done',?,?,1)",
                           (str(i), 'history', 'silent', i+10, i+11))
        before = store.records('batches')
        data = view(path).read(now=200)
        assert any(m['contact'] == 'old-active' for m in data['messages'])
        assert data['counts']['active'] == 1
        silent = next(m for m in data['messages'] if m['contact']=='history')
        assert silent['status'] == 'no_reply' and silent['stage'] == 4
        assert data['history_more']
        assert store.records('batches') == before


def test_standalone_push_has_no_invented_model_or_received_events(tmp_path):
    path = tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO outbox(id,contact,text,state,created_at,not_before) VALUES('push','A','reminder','pending',10,10)")
        item = view(path).read(now=11)['messages'][0]
        assert item['stage'] == 5 and item['kind'] == 'push'
        assert item['inbox_ids'] == []
        assert all(e['stage'] not in ('wxbot_received','hermes_result') for e in item['events'])


def test_outbox_failure_keeps_its_own_reason_and_is_counted_once(tmp_path):
    path = tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        store.capture('A', [], [Incoming('hello')], now=1)
        store.prepare(quiet=0, max_wait=1, prefix='/', now=2)
        batch=store.claim_batch(now=3)
        store.finish_batch_parts(batch.id, ('reply',), now=4)
        delivery=store.claim_delivery(now=5)
        store.finish_delivery(delivery.id, 'blocked', now=6, error='focus changed')
        data=view(path).read(now=7)
        item=data['messages'][0]
        assert item['error']=='focus changed'
        assert item['discard_at']==186
        assert data['counts']['issues']==1
