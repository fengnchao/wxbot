from types import SimpleNamespace
import json

import pytest

from butler.config import Config
from butler.contacts import Contact
from butler.business import BusinessStore
from butler.catalogue import SkillCatalogue
from butler.tools import ToolService
from butler.backends.codex import CodexBackend
from butler.hermes import HermesError


class FakeTurn:
    def __init__(self,status='completed'):
        self.status=status
    def stream(self):
        for method,payload in [('item/completed',{'item':{'type':'agentMessage','phase':'commentary','text':'DO NOT SEND'}}),
                               ('item/started',{'item':{'type':'mcpToolCall','tool':'skills_list','id':'tool1'}}),
                               ('item/completed',{'item':{'type':'agentMessage','phase':'final_answer','text':'你好呀'}}),
                               ('turn/completed',{'turn':{'status':self.status}})]:
            yield SimpleNamespace(method=method,payload=payload)


class FakeThread:
    id='thread-test'
    def turn(self,*args,**kwargs): return FakeTurn()


class FakeCodex:
    created=[]
    def __init__(self,config):
        self.config=config; self.closed=False; self.resumed=None; self.thread_options=None
        self.created.append(self)
    def account(self): return SimpleNamespace(account={'type':'chatgpt'})
    def thread_start(self,**kwargs): self.thread_options=kwargs; return FakeThread()
    def thread_resume(self,thread_id,**kwargs): self.resumed=thread_id; self.thread_options=kwargs; return FakeThread()
    def close(self): self.closed=True


def make_backend(tmp_path):
    cfg=Config(provider='codex',data_dir=str(tmp_path/'data'),codex_home=str(tmp_path/'codex'))
    store=BusinessStore(tmp_path/'business.sqlite3')
    cat=SkillCatalogue(cfg.plugin_path()/'skills')
    tools=ToolService(store,cat)
    return CodexBackend(cfg,store=store,tools=tools,client_factory=FakeCodex)


def test_backend_final_only_persistent_resume_and_scopes(tmp_path):
    b=make_backend(tmp_path)
    c=Contact('alice','default','alice')
    policy={'role_skill':'paimon','allowed_skills':[]}
    assert b.chat(c,'hi',skill_policy=policy)=='你好呀'
    first=b.session_id(c,skill_policy=policy)
    worker=list(b.workers.values())[0]
    assert worker.client.config.env['CODEX_HOME'] == str(tmp_path/'codex')
    assert worker.client.thread_options['config']['features']['shell_tool'] is False
    assert worker.client.thread_options['config']['features']['memories'] is False
    b.close()
    assert b.chat(c,'again',skill_policy=policy)=='你好呀'
    assert list(b.workers.values())[0].client.resumed == first
    assert b.scope(c,policy,'chat')!=b.scope(c,policy,'heartbeat')
    assert b.scope(c,policy,'chat')!=b.scope(Contact('bob','default','bob'),policy,'chat')
    assert b.scope(c,policy,'chat')!=b.scope(Contact('alice','default','alice',channel_type='group'),policy,'chat')
    assert b.scope(c,policy,'chat')!=b.scope(c,dict(policy,allowed_skills=['butler-memory']),'chat')
    assert b.scope(c,policy,'chat')!=b.scope(c,{'role_skill':'tong-jincheng-perspective','allowed_skills':[]},'chat')
    b.reset(c,skill_policy=policy)
    assert b.session_id(c,skill_policy=policy)!=first
    b.close()


def test_backend_rejects_failed_partial_or_unbound_tools(tmp_path, monkeypatch):
    b=make_backend(tmp_path); c=Contact('alice','default','alice')
    monkeypatch.setattr(FakeThread,'turn',lambda *a,**kw:FakeTurn('failed'))
    with pytest.raises(HermesError): b.chat(c,'hi')
    assert not b.workers
    with pytest.raises(ValueError): b.chat(c,'hi',skill_policy={'role_skill':'not-found','allowed_skills':[]})
    b.close()


def test_config_relative_paths_resolve_against_config_file(tmp_path):
    from butler.config import load
    path=tmp_path/'中文 空间'/'config.butler.toml'; path.parent.mkdir()
    path.write_text('[agent]\nprovider="codex"\ndata_dir="data"\n[codex]\nhome="runtime"\n',encoding='utf-8')
    cfg=load(path)
    assert cfg.provider=='codex'
    assert cfg.data_path()==path.parent/'data'
    assert cfg.codex_home_path()==path.parent/'runtime'
    assert cfg.flow_log_path()==str(path.parent/'data'/'cache'/'wxbot.log')
    path.write_text(path.read_text(encoding='utf-8')+'[log]\nflow_file="logs/flow.log"\n'
                    '[groups]\nfile="settings/groups.json"\n'
                    '[heartbeat]\nconfig_file="settings/policy.json"\n'
                    'state_file="settings/state.json"\naudit_file="logs/audit.jsonl"\n',encoding='utf-8')
    cfg=load(path)
    assert cfg.flow_log_path()==str(path.parent/'logs/flow.log')
    assert cfg.group_file_path()==str(path.parent/'settings/groups.json')
    assert cfg.heartbeat_config_path()==str(path.parent/'settings/policy.json')
    assert cfg.heartbeat_state_path()==str(path.parent/'settings/state.json')
    assert cfg.heartbeat_audit_path()==str(path.parent/'logs/audit.jsonl')


def test_codex_identity_has_no_legacy_storage_dependency():
    c=Contact('group','default','g1',channel_type='group')
    identity=c.identity(backend='codex')
    assert 'HERMES_HOME' not in identity
    assert 'Butler' in identity and 'member_id' in identity


def test_observed_group_identity_has_no_memory_capability(tmp_path, monkeypatch):
    b = make_backend(tmp_path)
    original = b.tools.issue
    definitions = []
    def issue(**kwargs):
        token = original(**kwargs)
        definitions.extend(b.tools.definitions(token))
        return token
    monkeypatch.setattr(b.tools, 'issue', issue)
    try:
        c = Contact('group', 'default', 'observed-user', channel_type='group', identity_status='observed')
        b.chat(c, 'remember me', skill_policy={'role_skill':'butler-companion', 'allowed_skills':['butler-memory']})
        assert not any(item['name'].startswith('memory_') for item in definitions)
        assert '不能读取或保存个人长期记忆' in c.identity(backend='codex')
    finally:
        b.close()


def test_sdk_gets_system_proxy_and_localhost_bypass(tmp_path,monkeypatch):
    monkeypatch.setattr('butler.backends.codex.getproxies',lambda:{'https':'http://127.0.0.1:9876'})
    b=make_backend(tmp_path)
    b.chat(Contact('alice','default','alice'),'hello')
    env=list(b.workers.values())[0].client.config.env
    assert env['HTTPS_PROXY']=='http://127.0.0.1:9876'
    assert '127.0.0.1' in env['NO_PROXY']
    b.close()


def test_broken_thread_resume_starts_fresh_same_identity_before_submission(tmp_path,monkeypatch):
    from openai_codex.errors import InternalRpcError
    b=make_backend(tmp_path);c=Contact('group','default','group',channel_type='group')
    scope=b.scope(c);b.store.set_session(scope,'broken-old-thread')
    def broken(*args,**kwargs):raise InternalRpcError(-32603,'failed to load thread')
    monkeypatch.setattr(FakeCodex,'thread_resume',broken)
    assert b.chat(c,'hello')=='你好呀'
    assert b.store.get_session(scope)=='thread-test'
    assert b.store.events()[0]['stage']=='model_result'
    b.close()


def test_pre_turn_failure_is_safe_to_retry_but_post_submission_is_not(tmp_path,monkeypatch):
    from openai_codex.errors import InternalRpcError
    b=make_backend(tmp_path);c=Contact('group','default','group')
    b.cfg.token='local-config-secret'
    def broken(*args,**kwargs):raise InternalRpcError(-32603,'startup exploded '+b.cfg.token)
    monkeypatch.setattr(FakeCodex,'account',broken)
    with pytest.raises(HermesError) as init:b.chat(c,'hello')
    assert init.value.retry_safe is True
    assert 'startup exploded' in str(init.value)
    assert b.cfg.token not in b.store.events()[0]['details']
    monkeypatch.setattr(FakeCodex,'account',lambda self:SimpleNamespace(account={'type':'chatgpt'}))
    monkeypatch.setattr(FakeThread,'turn',broken)
    with pytest.raises(HermesError) as sent:b.chat(c,'hello')
    assert sent.value.retry_safe is False
    b.close()


def test_startup_error_redacts_worker_credential_before_cleanup(tmp_path,monkeypatch):
    from openai_codex.errors import InternalRpcError
    b=make_backend(tmp_path)
    captured=[]
    def broken(client):
        credential=client.config.env['BUTLER_TOOL_CAPABILITY'];captured.append(credential)
        raise InternalRpcError(-32603,'rejected credential '+credential)
    monkeypatch.setattr(FakeCodex,'account',broken)
    with pytest.raises(HermesError) as info:b.chat(Contact('group','default','g'),'hello')
    assert captured[0] not in str(info.value)
    assert captured[0] not in b.store.events()[0]['details']
    assert '[REDACTED]' in str(info.value)


def test_worker_slot_timeout_is_safe_to_retry_without_releasing_unowned_slot(tmp_path):
    b=make_backend(tmp_path)
    class Full:
        def acquire(self,**kw):return False
        def release(self):raise AssertionError('slot was never acquired')
    b._slots=Full()
    with pytest.raises(HermesError) as info:b.chat(Contact('group','default','g'),'hello')
    assert info.value.retry_safe is True
    assert '请求队列等待超时' in str(info.value)
    assert 'retry_safe' in b.store.events()[0]['details']


def test_routing_timeout_reuses_client_before_submitting_once(tmp_path,monkeypatch):
    from openai_codex.errors import InternalRpcError
    b=make_backend(tmp_path); accounts=[]; turns=[]
    def account(client):
        accounts.append(client)
        if len(accounts)<3:
            raise InternalRpcError(-32603,'workspace routing discovery timed out')
        return SimpleNamespace(account={'type':'chatgpt'})
    def turn(*args,**kwargs):turns.append(True);return FakeTurn()
    monkeypatch.setattr(FakeCodex,'account',account)
    monkeypatch.setattr(FakeThread,'turn',turn)
    assert b.chat(Contact('alice','default','alice'),'hello')=='你好呀'
    assert len(accounts)==3 and len({id(c) for c in accounts})==1
    assert len(turns)==1
    assert any(e['stage']=='model_initializing' for e in b.store.events())
    b.close()


def test_routing_timeout_stops_after_three_checks_without_a_turn(tmp_path,monkeypatch):
    from openai_codex.errors import InternalRpcError
    b=make_backend(tmp_path); accounts=[]
    def account(client):
        accounts.append(client)
        raise InternalRpcError(-32603,'workspace routing discovery timed out')
    def turn(*args,**kwargs):raise AssertionError('must not submit a turn')
    monkeypatch.setattr(FakeCodex,'account',account)
    monkeypatch.setattr(FakeThread,'turn',turn)
    with pytest.raises(HermesError) as info:b.chat(Contact('alice','default','alice'),'hello')
    assert len(accounts)==3
    assert info.value.retry_safe is True
    assert accounts[0].closed
    assert not b.workers


def test_account_initialization_is_inside_total_deadline(tmp_path):
    import threading,time
    b=make_backend(tmp_path);released=threading.Event();clients=[]
    class SlowAccount(FakeCodex):
        def __init__(self,config):super().__init__(config);clients.append(self)
        def account(self):
            released.wait(1)
            return super().account()
        def close(self):super().close();released.set()
    b.client_factory=SlowAccount
    started=time.monotonic()
    try:
        with pytest.raises(HermesError) as info:
            b.chat(Contact('alice','default','alice'),'hello',timeout=.05)
        assert info.value.retry_safe is True
        assert time.monotonic()-started<.5
        assert clients[0].closed
        assert not b.workers and not b._credentials
    finally:released.set();b.close()


def test_slow_account_does_not_hold_other_contacts_worker_lock(tmp_path):
    import threading
    b=make_backend(tmp_path);entered=threading.Event();release=threading.Event();other=threading.Event();errors=[]
    class FirstSlow(FakeCodex):
        count=0
        def __init__(self,config):
            super().__init__(config);FirstSlow.count+=1;self.first=FirstSlow.count==1
        def account(self):
            if self.first:
                entered.set();release.wait(2)
            else:other.set()
            return super().account()
    b.client_factory=FirstSlow
    def chat(name):
        try:b.chat(Contact(name,'default',name),'hello')
        except Exception as exc:errors.append(exc)
    a=threading.Thread(target=chat,args=('alice',));second=threading.Thread(target=chat,args=('bob',))
    try:
        a.start();assert entered.wait(1)
        second.start();assert other.wait(.5),'another contact is blocked on the initialization lock'
    finally:
        release.set();a.join(2)
        if second.ident is not None:second.join(2)
        b.close()
    assert not errors


def test_startup_expiry_during_session_save_is_still_before_submission(tmp_path,monkeypatch):
    import time
    from butler.backends import codex_runtime
    original_deadline=codex_runtime.CallDeadline
    class ShortStartup(original_deadline):
        def __init__(self,seconds):super().__init__(.02 if seconds==60 else seconds)
    monkeypatch.setattr(codex_runtime,'CallDeadline',ShortStartup)
    b=make_backend(tmp_path);save=b.store.set_session;turns=[]
    def delayed_save(*args):time.sleep(.06);save(*args)
    def thread_start(client,**kwargs):
        class Thread:
            id='thread-test'
            def turn(self,*args):
                turns.append(True)
                if client.closed:raise RuntimeError('closed transport')
                return FakeTurn()
        return Thread()
    monkeypatch.setattr(b.store,'set_session',delayed_save)
    monkeypatch.setattr(FakeCodex,'thread_start',thread_start)
    with pytest.raises(HermesError) as info:b.chat(Contact('alice','default','alice'),'hello')
    assert info.value.retry_safe is True
    assert turns==[] and not b.workers
    b.close()


def test_initializing_clients_are_included_in_worker_capacity(tmp_path):
    import threading
    b=make_backend(tmp_path);clients=[];release=threading.Event();entered=[];both=threading.Event();errors=[]
    class Client(FakeCodex):
        def __init__(self,config):super().__init__(config);clients.append(self)
        def account(self):
            if len(clients)>1:
                entered.append(self)
                if len(entered)==2:both.set()
                release.wait(2)
            return super().account()
    b.client_factory=Client;b.chat(Contact('warm','default','warm'),'hello')
    def chat(name):
        try:b.chat(Contact(name,'default',name),'hello')
        except Exception as exc:errors.append(exc)
    threads=[threading.Thread(target=chat,args=(name,)) for name in ('alice','bob')]
    try:
        for thread in threads:thread.start()
        assert both.wait(1)
        assert sum(not c.closed for c in clients)<=b.cfg.codex_max_workers
    finally:
        release.set()
        for thread in threads:thread.join(2)
        b.close()
    assert not errors
