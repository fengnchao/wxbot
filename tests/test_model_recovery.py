import pytest

from wxbot.queue_store import QueueStore,Incoming
from wxbot.queue_worker import ModelWorker
from wxbot.reply import Reply
from wxbot.processor.butler import ButlerProcessor


def claimed(store, name='group'):
    store.capture(name,[],[Incoming('question','member','group context')],now=0,group_mode=True)
    store.prepare(quiet=0,max_wait=10,prefix='/',now=1)
    return store.claim_batch(now=1)


def test_safe_model_failure_retries_same_request_then_succeeds():
    store=QueueStore(':memory:');clock=[1];calls=[]
    class Router:
        def handle_reply(self,*args,request_id=None,**kw):
            calls.append(request_id)
            if len(calls)==1:
                exc=ValueError('initialization failed');exc.retry_safe=True;raise exc
            return Reply.from_text('complete reply')
    store.capture('group',[],[Incoming('question')],now=0)
    worker=ModelWorker(store,Router(),quiet=0,clock=lambda:clock[0])
    assert worker.process_once()
    assert not worker.process_once()
    clock[0]=6
    assert worker.process_once()
    assert calls[0]==calls[1] and len(calls)==2
    assert len(store.records('outbox'))==1
    assert store.records('batches')[0]['error']==''
    assert any(e['action']=='model_retry' for e in store.delivery_events())


def test_unknown_result_expires_without_replaying_and_releases_later_group_message():
    store=QueueStore(':memory:', failure_timeout_seconds=180)
    first=claimed(store)
    store.fail_batch(first.id,'old unknown result',now=2,retry_safe=False)
    store.capture('group',[],[Incoming('new question')],now=3)
    assert store.recover_model_failures(now=181)==[]
    events=store.recover_model_failures(now=182)
    assert events[0]['action']=='model_abandoned'
    assert store.get_batch(first.id)['state']=='done'
    assert store.records('outbox')==[]
    store.prepare(quiet=0,max_wait=10,prefix='/',now=183)
    assert store.claim_batch(now=183).text=='new question'


def test_retry_limit_and_unknown_legacy_tasks_survive_restart(tmp_path):
    path=tmp_path/'queue.db';store=QueueStore(path)
    first=claimed(store)
    for i,now in enumerate((1,6,21)):
        store.fail_batch(first.id,'startup failed',now=now,retry_safe=True)
        if i<2:
            retry=now+(5 if i==0 else 15)
            assert store.recover_model_failures(now=retry)[0]['action']=='model_retry'
            assert store.claim_batch(now=retry).id==first.id
    assert store.recover_model_failures(now=22)[0]['action']=='model_abandoned'
    second=claimed(store,'other')
    # An older version wrote no structured failure event.
    store._db.execute("UPDATE batches SET state='uncertain',error='ValueError: Butler 尚未提供完整回复',finished_at=2 WHERE id=?",(second.id,))
    store._db.commit()
    store.close();store=QueueStore(path)
    assert store.recover_model_failures(now=183)[0]['id']==second.id
    assert store.get_batch(second.id)['state']=='done'
    store.close()


def test_partial_outbox_is_never_abandoned_by_model_recovery():
    store=QueueStore(':memory:');batch=claimed(store)
    store.finish_batch_parts(batch.id,('reply',),now=2)
    delivery=store.claim_delivery(now=3)
    store.finish_delivery(delivery.id,'uncertain',now=3,error='unknown send')
    assert store.recover_model_failures(now=999)==[]
    assert store.get_delivery(delivery.id)['state']=='uncertain'


def test_incomplete_reply_preserves_trusted_retry_flag_and_error():
    with pytest.raises(ValueError) as info:
        ButlerProcessor._decode_reply({'reply':None,'meta':{'reply_complete':False,
             'retry_safe':True,'error':'Codex initialization failed: InternalRpcError'}},'r')
    assert info.value.retry_safe is True
    assert 'InternalRpcError' in str(info.value)
    with pytest.raises(ValueError) as unknown:
        ButlerProcessor._decode_reply({'meta':{'reply_complete':False,'retry_safe':'true'}},'r')
    assert unknown.value.retry_safe is False


def test_dashboard_explains_recovery_and_preserves_failure_history(tmp_path):
    from log.queue_view import QueueView
    from log.flow_view import FlowView
    path=tmp_path/'q.db';store=QueueStore(path,failure_timeout_seconds=180);first=claimed(store)
    store.fail_batch(first.id,'startup failed',now=2,retry_safe=True)
    data=QueueView(path,failure_timeout_seconds=180).read(now=3)
    reason=data['contacts'][0]['reason']
    assert reason['retry_at']==7 and reason['discard_at']==182
    assert data['batches'][0]['retry_safe'] is True
    store.recover_model_failures(now=183)
    history=QueueView(path,failure_timeout_seconds=180).read(scope='history',now=184)
    assert history['batches'][0]['display_state']=='model_failed'
    flow=FlowView({'path':path},[]).read(now=184)['flows'][0]
    assert flow['state']=='model_failed' and 'startup failed' in flow['reason']['error']
    store.close()


def test_interrupted_retry_never_reuses_previous_safe_to_retry_flag():
    store=QueueStore(':memory:');batch=claimed(store)
    store.fail_batch(batch.id,'before turn',now=2,retry_safe=True)
    store.recover_model_failures(now=7);store.claim_batch(now=7)
    store.recover(now=8)
    assert store.recover_model_failures(now=30)==[]
    assert store.get_batch(batch.id)['state']=='uncertain'
    # First failure deadline survives interruption and service restart.
    assert store.recover_model_failures(now=182)[0]['action']=='model_abandoned'


def test_ready_retry_expires_atomically_before_claim_even_after_restart(tmp_path):
    path=tmp_path/'queue.db';store=QueueStore(path);batch=claimed(store)
    store.fail_batch(batch.id,'startup failed',now=2,retry_safe=True)
    store.recover_model_failures(now=7)
    assert store.get_batch(batch.id)['state']=='ready'
    store.close();store=QueueStore(path)
    assert store.claim_batch(now=182) is None
    assert store.get_batch(batch.id)['state']=='done'
    assert store.delivery_events()[-1]['action']=='model_abandoned'
    store.close()


def test_failed_batch_cleanup_runs_while_all_model_workers_are_waiting(monkeypatch):
    import threading
    store=QueueStore(':memory:');failed=claimed(store,'old')
    store.fail_batch(failed.id,'connection reset',now=2)
    for name in ('A','B'):store.capture(name,[],[Incoming('question')],now=0)
    entered={name:threading.Event() for name in ('A','B')};release=threading.Event();cleaned=threading.Event();clock=[3]
    class Router:
        def handle_reply(self,contact,*args,**kwargs):
            entered[contact].set();release.wait(3)
            return Reply.from_text('reply')
    recover=store.recover_model_failures
    def recovery(**kwargs):
        result=recover(**kwargs)
        if any(e['id']==failed.id for e in result):cleaned.set()
        return result
    monkeypatch.setattr(store,'recover_model_failures',recovery)
    worker=ModelWorker(store,Router(),quiet=0,clock=lambda:clock[0],max_concurrency=2)
    worker.start()
    try:
        assert entered['A'].wait(1) and entered['B'].wait(1)
        clock[0]=183
        assert cleaned.wait(.7),'expiry depends on occupied model worker threads'
        assert store.get_batch(failed.id)['state']=='done'
    finally:
        release.set();assert worker.stop(timeout=2);store.close()
