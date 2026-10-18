import json
import sqlite3

from wxbot.queue_store import Incoming,QueueStore


def test_flow_shows_received_messages_and_exact_old_blocker_without_claiming_butler_received(tmp_path):
    from log.flow_view import FlowView
    path=tmp_path/'q.db'
    s=QueueStore(path)
    s.capture('A',[],[Incoming('old')],now=0)
    s.prepare(quiet=0,max_wait=10,prefix='/',now=0)
    batch=s.claim_batch(now=0)
    s.finish_batch_parts(batch.id,('reply',),now=1)
    delivery=s.claim_delivery(now=1)
    s.finish_delivery(delivery.id,'blocked',now=2,error='input mismatch')
    s.capture('A',[],[Incoming('new'),Incoming('question')],now=3)
    before=[s.records(t) for t in ('inbox','batches','outbox')]
    data=FlowView({'path':path},[]).read(now=10)
    new=next(f for f in data['flows'] if f['preview']=='new')
    assert new['reason']['record_id']==delivery.id
    assert new['events'][0]['stage']=='wxbot_received' and new['events'][0]['status']=='ok'
    assert any(e['stage']=='wxbot_merge' and e['status']=='blocked' for e in new['events'])
    assert not any(e['stage']=='butler_received' and e['status']=='ok' for e in new['events'])
    assert [s.records(t) for t in ('inbox','batches','outbox')]==before
    assert data['total']==3
    assert FlowView({'path':path},[]).read(contact="' OR 1=1 --")['flows']==[]
    assert len(FlowView({'path':path},[]).read(limit=1,offset=1)['flows'])==1
    s.close()


def test_flow_correlates_by_both_contact_and_batch_id_and_keeps_sources_readonly(tmp_path):
    from common.flow_trace import FlowTrace
    from log.flow_view import FlowView
    path=tmp_path/'q.db'
    s=QueueStore(path)
    s.capture('A',[],[Incoming('hi')],now=0)
    s.prepare(quiet=0,max_wait=10,prefix='/',now=0)
    batch=s.claim_batch(now=0)
    events=tmp_path/'trace.jsonl'
    writer=FlowTrace(events)
    writer.emit('B',batch.id,'butler_received','ok')
    writer.emit('A','another-id','hermes_result','ok')
    writer.emit('A',batch.id,'butler_received','ok')
    with events.open('a',encoding='utf-8') as f:
        f.write('{bad trailing record')
    s.close()
    before={p:p.read_bytes() for p in (path,events)}
    data=FlowView({'path':path},[events,tmp_path/'missing.jsonl']).read()
    flow=data['flows'][0]
    assert flow['request_id']==batch.id
    assert sum(e['stage']=='butler_received' and e['status']=='ok' for e in flow['events'])==1
    assert not any(e['stage']=='hermes_result' and e['status']=='ok' for e in flow['events'])
    assert {p:p.read_bytes() for p in before}==before
    assert not (tmp_path/'missing.jsonl').exists()


def test_flow_missing_database_is_not_created(tmp_path):
    from log.flow_view import FlowView
    path=tmp_path/'missing.db'
    data=FlowView({'path':path},[]).read()
    assert data['status']=='missing' and data['read_only']
    assert not path.exists()


def test_flow_configuration_uses_actual_queue_and_butler_log_paths(tmp_path):
    from test_log_monitor import configs
    from log.config_view import ConfigView
    from common.flow_trace import queue_trace_path,butler_trace_path
    wx,bt,home=configs(tmp_path)
    explicit=tmp_path/'custom.log'
    with bt.open('a',encoding='utf-8') as f:
        f.write('\n[log]\nflow_file='+json.dumps(str(explicit))+'\n')
    view=ConfigView(wx,bt,home,repo_root=tmp_path)
    view.read()
    opts=view.flow_options()
    assert opts['trace_paths']==[queue_trace_path(tmp_path/'cache'/'wxbot_queue.sqlite3'),butler_trace_path(explicit)]
    rows={r['key']:r['value'] for section in view.read()['sections'] for r in section['rows']}
    assert rows['wxbot.flow_trace_file']==str(opts['trace_paths'][0])
    assert rows['butler.flow_trace_file']==str(opts['trace_paths'][1])


def test_historical_finished_batch_without_a_trace_does_not_claim_a_reply_was_enqueued(tmp_path):
    from log.flow_view import FlowView
    path=tmp_path/'legacy-done.db'
    s=QueueStore(path)
    s.capture('A',[],[Incoming('old')],now=0)
    s.prepare(quiet=0,max_wait=10,prefix='/',now=0)
    b=s.claim_batch(now=0)
    s.finish_batch_parts(b.id,(),now=1)
    s.close()
    flow=FlowView({'path':path},[]).read()['flows'][0]
    assert not any(e['stage']=='wxbot_result' and e['status']=='ok' for e in flow['events'])
