from threading import Event, Lock
import pytest

from wxbot.queue_store import QueueStore, Incoming
from wxbot.queue_worker import ModelWorker
from wxbot.reply import Reply


def test_bounded_parallel_waits_and_stop_does_not_claim_more():
    store=QueueStore(':memory:')
    for name in ('A','B','C'):
        store.capture(name,[],[Incoming('question')],now=0)
    entered={name:Event() for name in ('A','B','C')}
    release=Event()
    ids=[]
    class Router:
        def handle_reply(self, contact, text, *, context='',request_id=None, member_key="", member_name=""):
            ids.append(request_id)
            entered[contact].set()
            assert release.wait(3)
            return Reply('一。二。',('一。','二。'))
    worker=ModelWorker(store,Router(),quiet=0,max_wait=10,clock=lambda:1,max_concurrency=2)
    worker.start()
    try:
        assert entered['A'].wait(2) and entered['B'].wait(2)
        assert not entered['C'].is_set()
        assert store.records('batches')[2]['state']=='ready'
        assert len(ids)==len(set(ids))==2
        assert not worker.stop(timeout=.01)
    finally:
        release.set()
        assert worker.stop(timeout=2)
    assert not entered['C'].is_set()
    assert len(store.records('outbox'))==4
    assert store.records('batches')[2]['state']=='ready'


@pytest.mark.parametrize('value',[True,False,0,-1,1.5,'2'])
def test_concurrency_positive_integer(value):
    with pytest.raises(ValueError):
        ModelWorker(QueueStore(':memory:'),None,max_concurrency=value)


@pytest.mark.parametrize('value',[True,0,-1,2.5,'2'])
def test_config_and_direct_inbox_validate(value,tmp_path):
    from wxbot.config import load_config
    from wxbot.inbox import MainInbox
    from test_main_window import cfg,Desktop
    c=cfg()
    c['queue']['max_model_requests']=value
    with pytest.raises(ValueError):
        MainInbox(c,None,desktop=Desktop([]))
    path=tmp_path/'config.toml'
    import json
    encoded=str(value).lower() if isinstance(value,bool) else json.dumps(value)
    path.write_text('[wechat]\nmode="main"\n[queue]\nmax_model_requests='+encoded,encoding='utf-8')
    with pytest.raises(ValueError):
        load_config(path)


def test_config_default_and_one_valid(tmp_path):
    from wxbot.config import load_config
    path=tmp_path/'config.toml'
    path.write_text('[wechat]\nmode="main"',encoding='utf-8')
    assert load_config(path)['queue']['max_model_requests']==2
    path.write_text('[wechat]\nmode="main"\n[queue]\nmax_model_requests=1',encoding='utf-8')
    assert load_config(path)['queue']['max_model_requests']==1


def test_stop_budget_includes_a_blocked_queue_prepare():
    entered,release,stopped=Event(),Event(),Event()
    class Store:
        def recover_model_failures(self,**kw):return []
        def prepare(self,**kw):
            entered.set()
            assert release.wait(3)
            return 0
        def claim_batch(self,**kw):
            raise AssertionError('stop must prevent the next claim')
    worker=ModelWorker(Store(),None,max_concurrency=1)
    worker.start()
    assert entered.wait(2)
    result=[]
    from threading import Thread
    def stop():
        result.append(worker.stop(timeout=.01))
        stopped.set()
    thread=Thread(target=stop,daemon=True)
    thread.start()
    try:
        assert stopped.wait(.3), 'stop blocked on a queue transaction beyond its total budget'
        assert result==[False]
    finally:
        release.set()
        thread.join(2)
        worker.stop(timeout=2)


def test_stop_during_claim_releases_unsubmitted_batch(monkeypatch):
    store=QueueStore(':memory:')
    store.capture('A',[],[Incoming('hi')],now=0)
    entered,release=Event(),Event()
    original=store.claim_batch
    def claim(**kw):
        entered.set()
        assert release.wait(3)
        return original(**kw)
    monkeypatch.setattr(store,'claim_batch',claim)
    class Router:
        def handle_reply(self,*a,**kw):
            raise AssertionError('model must not start after stop')
    worker=ModelWorker(store,Router(),quiet=0,clock=lambda:1,max_concurrency=1)
    worker.start()
    assert entered.wait(2)
    try:
        assert worker.stop(timeout=.01) is False
    finally:
        release.set()
        assert worker.stop(timeout=2)
    row=store.records('batches')[0]
    assert row['state']=='ready' and row['attempts']==0 and row['started_at'] is None
