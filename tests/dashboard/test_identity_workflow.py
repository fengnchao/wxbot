"""Existing flow details expose only bounded identity and context summaries."""
import json

from common.flow_trace import FlowTrace
from dashboard.flow_view import FlowView
from dashboard.workflow_view import WorkflowView
from wxbot.queue_store import Incoming, QueueStore
from wxbot.queue_worker import ModelWorker


def views(path, trace):
    options = {'path': path, 'failure_timeout_seconds': 180}
    return FlowView(options, [trace]), WorkflowView(options, [trace])


def batch(store, mode='text', **kwargs):
    store.capture('群', [], [Incoming('公开问题', 'observed-key', '', '观察昵称', mode, **kwargs)],
                  group_mode=True, now=1)
    store.prepare(quiet=0, max_wait=1, prefix='/', now=2)
    return store.claim_batch(now=3)


def test_identity_context_and_mention_scalars_reach_existing_flow_and_workflow(tmp_path):
    path, trace = tmp_path/'q.db', tmp_path/'trace.jsonl'
    store = QueueStore(path)
    item = batch(store)
    writer = FlowTrace(trace)
    writer.emit('群', item.id, 'butler_identity', 'confirmed', user_id='fixed-user', binding_id='fixed-binding')
    writer.emit('群', item.id, 'butler_memory', 'ok', memory_count=2)
    writer.emit('群', item.id, 'butler_context', 'ok', context_from=10, context_to=17, context_count=5)
    writer.emit('群', item.id, 'wxbot_group_decision', 'direct', decision='direct')
    writer.emit('群', item.id, 'wechat_mention', 'ok', mention_stage='object_verified')
    # A corrupted trace must not expose arbitrary private properties.
    with trace.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps({'ts': 100000000000, 'contact': '群', 'request_id': item.id,
            'stage': 'butler_memory', 'status': 'ok', 'memory_body': 'PRIVATE_MEMORY',
            'avatar': 'PRIVATE_AVATAR'})+'\n')
    for view in views(path, trace):
        data = view.read(now=10)
        row = data.get('flows', data.get('messages'))[0]
        assert row['user_id'] == 'fixed-user'
        assert row['binding_id'] == 'fixed-binding'
        assert row['identity_status'] == 'confirmed'
        assert row['memory_count'] == 2
        assert (row['context_from'], row['context_to'], row['context_count']) == (10, 17, 5)
        assert row['decision'] == 'direct'
        assert row['mention_stage'] == 'object_verified'
        rendered = json.dumps(data)
        assert 'PRIVATE_MEMORY' not in rendered and 'PRIVATE_AVATAR' not in rendered
    store.close()


def test_silent_group_archive_is_terminal_without_pending_model_milestones(tmp_path):
    path, trace = tmp_path/'q.db', tmp_path/'trace.jsonl'
    store = QueueStore(path)
    store.capture('群', [], [Incoming('普通公开发言', 'a', '', '甲', 'none')], group_mode=True, now=1)
    class Backend:
        def archive_group(self, *args, **kwargs):
            return 7
        def handle_reply(self, *args, **kwargs):
            raise AssertionError('silent archive must not call model')
    ModelWorker(store, Backend(), quiet=0, clock=lambda: 3, trace=FlowTrace(trace)).process_once()
    flow, workflow = views(path, trace)
    row = workflow.read(now=4)['messages'][0]
    assert row['status'] == 'archived' and row['terminal'] and row['scope'] == 'complete'
    assert row['stage'] == 2
    assert workflow.read(now=4)['counts']['active'] == 0
    events = flow.read(now=4)['flows'][0]['events']
    assert not any(e['stage'] in ('wxbot_model', 'hermes_request', 'hermes_result') for e in events)
    assert any(e['stage'] == 'wxbot_group_context' and e['status'] == 'archived' for e in events)
    store.close()


def test_in_progress_silent_archive_is_not_counted_as_pending_model(tmp_path):
    path, trace = tmp_path/'q.db', tmp_path/'trace.jsonl'
    store = QueueStore(path)
    batch(store, 'none', reply_reason='cooldown')
    data = views(path, trace)[1].read(now=4)
    assert data['counts']['model'] == 0
    assert not any(e['stage']=='wxbot_model' for e in data['messages'][0]['events'])
    store.close()


def test_existing_delivery_verification_exposes_mention_stage_without_target_or_payload(tmp_path):
    path, trace = tmp_path/'q.db', tmp_path/'trace.jsonl'
    store = QueueStore(path)
    item = batch(store)
    store.finish_batch_parts(item.id, ('公开回答',), now=4, mention_name='甲')
    delivery = store.claim_delivery(now=5)
    store.finish_delivery(delivery.id, 'sent', now=6,
                          details={'mention_verified': True, 'bubble_verified': True})
    row = views(path, trace)[1].read(now=7)['messages'][0]
    assert row['mention_stage'] == 'object_verified'
    event = next(e for e in row['events'] if e['stage'] == 'wechat_mention')
    assert event['mention_stage'] == 'object_verified'
    assert 'mention_name' not in event
    store.close()


def test_mention_plain_fallback_survives_delivery_log_without_claiming_an_at(tmp_path):
    path,trace=tmp_path/'q.db',tmp_path/'trace.jsonl'
    store=QueueStore(path)
    item=batch(store)
    store.finish_batch_parts(item.id,('正文',),now=4,mention_name='甲')
    delivery=store.claim_delivery(now=5)
    store.finish_delivery(delivery.id,'sent',now=6,details={
        'mention_verified':False,'mention_fallback':'multiple_candidates','bubble_verified':True})
    row=views(path,trace)[1].read(now=7)['messages'][0]
    assert row['mention_stage']=='fallback_plain'
    assert store.delivery_events()[0]['details']['mention_fallback']=='multiple_candidates'
    store.close()


def test_persisted_budget_reason_survives_silent_worker_and_missing_trace(tmp_path):
    path, trace = tmp_path/'q.db', tmp_path/'trace.jsonl'
    store = QueueStore(path)
    store.capture('群', [], [Incoming('普通群发言', 'a', '', '甲', 'none', reply_reason='budget')],
                  group_mode=True, now=1)
    class Backend:
        def archive_group(self, *args, **kwargs):
            return 7
    ModelWorker(store, Backend(), quiet=0, clock=lambda: 3, trace=FlowTrace(trace)).process_once()
    events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
    assert any(e['stage']=='wxbot_group_decision' and e.get('decision')=='budget' for e in events)
    row = views(path, tmp_path/'missing.jsonl')[1].read(now=4)['messages'][0]
    assert row['decision']=='budget' and row['status']=='archived'
    assert not any(e['stage']=='wxbot_model' for e in row['events'])
    store.close()
