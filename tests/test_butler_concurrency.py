from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

from butler.identity.contacts import Contact, load_contacts
from butler.agent.hermes import HermesClient


def test_different_users_concurrent_alias_and_reset_serial(make_home):
    home = make_home(pending_items=[], contacts=[
        {'name': 'A', 'uid': 'a', 'profile': 'wxbot-101'},
        {'name': 'alias', 'uid': 'a', 'profile': 'wxbot-101'},
        {'name': 'B', 'uid': 'b', 'profile': 'wxbot-101'}])
    entered, release, b_entered, alias_entered, reset_entered = [Event() for _ in range(5)]
    def chat(contact, text, **kw):
        if contact.name == 'A':
            entered.set()
            assert release.wait(3)
        elif contact.name == 'B':
            b_entered.set()
        else:
            alias_entered.set()
        return '好。'
    home.hermes.chat = chat
    home.hermes.reset = lambda *a, **kw: reset_entered.set()
    with ThreadPoolExecutor(4) as pool:
        a = pool.submit(home.butler.handle, 'A', 'hi')
        assert entered.wait(2)
        b = pool.submit(home.butler.handle, 'B', 'hi')
        alias = pool.submit(home.butler.handle, 'alias', 'hi')
        reset = pool.submit(home.butler.reset, 'alias')
        try:
            assert b_entered.wait(2)
            assert not alias_entered.is_set() and not reset_entered.is_set()
        finally:
            release.set()
        for job in (a, b, alias, reset):
            job.result(3)


def test_alias_session_reset_is_shared(make_home):
    h = make_home(pending_items=[])
    client = HermesClient(h.cfg)
    a = Contact('A', 'p', 'same')
    alias = replace(a, name='alias')
    client.reset(a)
    assert client.session_id(alias) == client.session_id(a)
    assert client.session_id(replace(a, channel_type='group')) != client.session_id(a)


def test_pending_claim_filters_ownership_and_is_atomic(make_home):
    items = [{'key':'a', 'text':'A', 'uid':'a'}, {'key':'b', 'text':'B', 'user_id':'b'},
             {'key':'bad', 'text':'bad', 'uid':'a', 'contact':'B'},
             {'key':'legacy', 'text':'legacy'}, {'text':'no-key', 'uid':'a'}]
    h = make_home(pending_items=items)
    a, b = Contact('A','wxbot-101','a'), Contact('B','wxbot-101','b')
    with ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(h.butler.pending.take_and_claim, c) for c in (a,b)]
        assert [[i['key'] for i in j.result(3)] for j in jobs] == [['a'],['b']]
    assert h.butler.pending.take_and_claim(a) == []


def test_sole_profile_owner_counts_uid_aliases():
    cm = load_contacts([{'name':'a','profile':'p','uid':'1'}, {'name':'alias','profile':'p','uid':'1'}])
    assert cm.is_sole_profile_owner(cm.get('a'))
    assert not cm.is_sole_profile_owner(Contact('unknown','p','1'))
    cm.by_name['b'] = Contact('b','p','2')
    assert not cm.is_sole_profile_owner(cm.get('a'))


def test_pending_partial_flush_failure_keeps_success_and_rejects_bad_owners(make_home,monkeypatch):
    h=make_home(pending_items=[{'key':'ok','text':'ok','uid':'101'},
                              {'key':'invalid','text':'bad','uid':None},
                              {'key':'fail','text':'fail','uid':'101'}])
    original=h.butler.pending._run
    def run(script,*args):
        return None if args==('flush','fail') else original(script,*args)
    monkeypatch.setattr(h.butler.pending,'_run',run)
    assert [r['key'] for r in h.butler.pending.take_and_claim(h.cfg.contacts.get('101'))]==['ok']
    assert [r['key'] for r in h.butler.pending.take('wxbot-101')]==['invalid','fail']


def test_pending_unique_owner_and_alias_never_double_claim(make_home):
    h=make_home(contacts=[{'name':'101','profile':'wxbot-101','uid':'101'},
                          {'name':'alias','profile':'wxbot-101','uid':'101'}])
    q=h.butler.pending
    with ThreadPoolExecutor(2) as pool:
        jobs=[pool.submit(q.take_and_claim,h.cfg.contacts.get(n),allow_unowned=True) for n in ('101','alias')]
        assert sum(len(j.result(3)) for j in jobs)==1
    unknown=Contact('unknown','default','x')
    assert not h.cfg.contacts.is_sole_profile_owner(unknown)


def test_delegate_preserves_policy_and_releases_profile_lock(make_home,monkeypatch):
    from butler.agent import skills
    from butler.agent.skills import Ctx
    h=make_home(pending_items=[])
    entered,release,acquired=Event(),Event(),Event()
    policy={'role_skill':'paimon','allowed_skills':['tool']}
    def chat(c,t,**kw):
        assert kw['skill_policy'] is policy
        entered.set()
        assert release.wait(3)
        return 'hi'
    h.hermes.chat=chat
    ctx=Ctx(h.cfg,h.cfg.contacts.get('101'),h.hermes,skill_policy=policy,runtime_locks=h.butler.runtime_locks)
    def resource():
        with h.butler.runtime_locks.profile('wxbot-101'):
            acquired.set()
    with ThreadPoolExecutor(2) as pool:
        job=pool.submit(skills.execute,{'skill':'learn.card'},ctx)
        assert entered.wait(2)
        lock_job=pool.submit(resource)
        try:
            assert acquired.wait(2)
        finally:
            release.set()
        assert job.result(3).ok
        lock_job.result(3)


def test_local_actions_serialize_profile_without_model_guard(make_home,monkeypatch):
    from butler.agent import skills
    h=make_home(pending_items=[])
    entered,release,second,other=Event(),Event(),Event(),Event()
    def local(ctx,args):
        if args.get('first'):
            entered.set()
            assert release.wait(3)
        elif ctx.contact.profile=='other':
            other.set()
        else:
            second.set()
        return skills.ActionResult('local',True)
    monkeypatch.setitem(skills.CATALOG,'test.local',skills.SkillSpec('test.local','local',local))
    ctx=skills.Ctx(h.cfg,h.cfg.contacts.get('101'),h.hermes,runtime_locks=h.butler.runtime_locks)
    other_ctx=replace(ctx,contact=Contact('B','other','b'))
    with ThreadPoolExecutor(3) as pool:
        first=pool.submit(skills.execute,{'skill':'test.local','args':{'first':True}},ctx)
        assert entered.wait(2)
        next_job=pool.submit(skills.execute,{'skill':'test.local'},ctx)
        other_job=pool.submit(skills.execute,{'skill':'test.local'},other_ctx)
        try:
            assert other.wait(2) and not second.is_set()
        finally:
            release.set()
        assert all(j.result(3).ok for j in (first,next_job,other_job))


def test_heartbeat_kind_has_separate_lock_and_group_reset_transport(make_home,start_server):
    from test_transport import _call
    h=make_home(pending_items=[])
    c=h.cfg.contacts.get('101')
    entered=Event()
    def heartbeat():
        with h.butler.runtime_locks.session(c,session_kind='heartbeat'):
            entered.set()
    with ThreadPoolExecutor(1) as pool:
        with h.butler.runtime_locks.session(c):
            job=pool.submit(heartbeat)
            assert entered.wait(2)
        job.result(3)
    base=start_server(h.butler,h.cfg)
    dm=h.hermes.session_id(c)
    code,body=_call(base,'/v1/reset',{'contact':'101','channel_type':'group'})
    assert code==200 and body['meta']['reply_complete']
    assert h.hermes.session_id(c)==dm
    assert h.hermes.session_id(replace(c,channel_type='group'))!=replace(c,channel_type='group').session_id()
    assert _call(base,'/v1/reset',{'contact':'101','channel_type':'bad'})[0]==400


def test_bad_pending_text_does_not_flush_or_hide_good_items(make_home):
    items=[{'key':'dict','text':{'message':'bad'}}, 123,
           {'key':'list','text':['bad']}, {'key':'integer','text':42},
           {'key':'good','text':'good'}]
    h=make_home(pending_items=items)
    assert [i['key'] for i in h.butler.pending.take_and_claim(h.cfg.contacts.get('101'),allow_unowned=True)]==['good']
    import json
    remaining=json.loads((h.scripts/'items.json').read_text(encoding='utf-8'))
    assert remaining==items[:-1]


def test_unknown_pending_ownership_is_not_legacy_unowned(make_home):
    keys=['recipient','receiver','to','target_uid','user','contact_name','UID',
          'recipientId','contactName','toUserId','recipientid','recipients']
    items=[{'key':key,'text':'other user text',key:'other'} for key in keys]
    items.append({'key':'legacy','text':'legacy'})
    h=make_home(pending_items=items)
    assert [i['key'] for i in h.butler.pending.take_and_claim(h.cfg.contacts.get('101'),allow_unowned=True)]==['legacy']
    import json
    assert json.loads((h.scripts/'items.json').read_text(encoding='utf-8'))==items[:-1]


def test_nested_pending_recipient_is_not_unowned(make_home):
    h=make_home(pending_items=[{'key':'nested','text':'secret','metadata':{'recipientId':'B'}}])
    assert h.butler.pending.take_and_claim(h.cfg.contacts.get('101'),allow_unowned=True)==[]
