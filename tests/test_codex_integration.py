import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from butler.config import Config
from butler.core import Butler
from butler.server import make_handler
from butler.reminders import ReminderScheduler
from test_codex_backend import FakeCodex, FakeThread, FakeTurn


def make(tmp_path):
    cfg=Config(provider='codex',data_dir=str(tmp_path/'data'),token='test-secret')
    b=Butler(cfg)
    b.hermes.client_factory=FakeCodex
    return cfg,b


def test_core_uses_codex_without_hermes_or_legacy_actions(tmp_path):
    cfg,b=make(tmp_path)
    assert b.handle('alice','hello').reply=='你好呀'
    assert b.pending.take_and_claim(b.contact_of('alice'))==[]
    assert b.store.path.is_relative_to(tmp_path)
    b.hermes.close()


def test_startup_description_identifies_active_backend(tmp_path):
    from butler.server import backend_description
    cfg=Config(provider='codex',data_dir=str(tmp_path/'data'),hermes_key='must-not-log')
    description=backend_description(cfg)
    assert 'Codex' in description
    assert 'Hermes' not in description and '8642' not in description
    assert cfg.hermes_key not in description


def test_mcp_handshake_and_identity_bound_call(tmp_path):
    cfg,b=make(tmp_path)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(b,cfg))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    token=b.tools.issue(owner='alice',contact='alice',policy={'role_skill':'butler-companion','allowed_skills':[]},request_id='r')
    def rpc(method,params=None):
        body={'jsonrpc':'2.0','id':1,'method':method,'params':params or {}}
        req=urllib.request.Request('http://127.0.0.1:%s/mcp'%server.server_port,data=json.dumps(body).encode(),
                headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
        with urllib.request.urlopen(req) as response:return json.load(response)
    try:
        assert rpc('initialize',{'protocolVersion':'2025-03-26'})['result']['serverInfo']['name']=='butler-wechat'
        assert {t['name'] for t in rpc('tools/list')['result']['tools']}=={'skills_list','skill_read'}
        assert rpc('tools/call',{'name':'memory_get','arguments':{}})['result']['isError'] is True
    finally:
        server.shutdown();server.server_close();b.hermes.close()


def test_scheduler_claims_once_and_records_failures(tmp_path):
    cfg,b=make(tmp_path)
    calls=[]
    class Result:
        meta={'ok':False,'detail':'not sent'}
    b.push=lambda contact,text: calls.append((contact,text)) or Result()
    from pathlib import Path
    policy_path=Path(cfg.heartbeat_config_path());policy_path.parent.mkdir(parents=True,exist_ok=True)
    policy_path.write_text(json.dumps({'users':{'alice':{'role_skill':'butler-companion','allowed_skills':['create-cron-job']}}}),encoding='utf-8')
    token=b.tools.issue(owner='alice',contact='alice',policy={'role_skill':'butler-companion','allowed_skills':['create-cron-job']},request_id='r')
    item=b.tools.call('reminder_create',{'text':'喝水','schedule':'in 1s'},token,'c')
    scheduler=ReminderScheduler(b)
    scheduler.tick(now=item['due']+1)
    scheduler.tick(now=item['due']+10)
    assert calls==[('alice','喝水')]
    assert b.store.reminders('alice')[0]['status']=='failed'


def test_cancelled_queued_reminder_is_not_dispatched(tmp_path):
    _,b=make(tmp_path)
    with b.store.transaction() as db:
        first=b.store.create_reminder('alice','alice','first','in 1s',db=db)
        second=b.store.create_reminder('alice','alice','cancel me','in 2s',db=db)
    calls=[]
    class Result:
        meta={'ok':True}
    def push(contact,text):
        calls.append(text)
        if text=='first':
            with b.store.transaction() as db:
                b.store.cancel_reminder('alice',second['id'],db=db)
        return Result()
    b.push=push
    ReminderScheduler(b).tick(now=second['due']+1)
    assert calls==['first']
    assert {r['id']:r['status'] for r in b.store.reminders('alice')}=={
        first['id']:'sent',second['id']:'cancelled'}


def test_cancel_rejects_reminder_already_being_delivered(tmp_path):
    import pytest
    _,b=make(tmp_path)
    with b.store.transaction() as db:
        item=b.store.create_reminder('alice','alice','sending','in 1s',db=db)
    b.store.claim_due(now=item['due']+1)
    with pytest.raises(ValueError,match='delivering'):
        with b.store.transaction() as db:
            b.store.cancel_reminder('alice',item['id'],db=db)
    assert b.store.reminders('alice')[0]['status']=='delivering'


@pytest.mark.parametrize('failure',['login','quota','incomplete','timeout'])
def test_codex_failure_never_exposes_a_sendable_reply(tmp_path,monkeypatch,failure):
    _,b=make(tmp_path)
    if failure=='login':
        monkeypatch.setattr(FakeCodex,'account',lambda self:SimpleNamespace(account=None))
    elif failure=='quota':
        def denied(*args,**kwargs):raise RuntimeError('quota exceeded')
        monkeypatch.setattr(FakeThread,'turn',denied)
    elif failure=='incomplete':
        def stream(self):
            yield SimpleNamespace(method='turn/completed',payload={'turn':{'status':'completed'}})
        monkeypatch.setattr(FakeTurn,'stream',stream)
    else:
        class ImmediateTimer:
            def __init__(self,interval,callback):self.callback=callback
            def start(self):self.callback()
            def cancel(self):pass
        monkeypatch.setattr('butler.backends.codex.threading.Timer',ImmediateTimer)
    result=b.handle('alice','hello').as_dict()
    assert result['reply'] is None
    assert result['reply_parts']==[]
    assert result['meta']['reply_complete'] is False
    assert not b.backend.workers
