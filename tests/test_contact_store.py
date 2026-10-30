import copy
from pathlib import Path

import pytest


def conversation(name='A',kind='dm'):
    return dict(id='route-'+name,name=name,channel_type=kind,uid=name,profile='p',label=name,
                session_key='',listening=True,enabled=True,person_id='person-A' if kind=='dm' else '',
                policy={'role_skill':'role','allowed_skills':['tool'],'heartbeat_enabled':True},subscriptions=[1])


def test_unified_source_requires_explicit_activation_and_never_creates_on_read(tmp_path):
    from butler.contact_store import ContactStore,is_unified
    path=tmp_path/'business.sqlite3'
    assert not is_unified(path) and not path.exists()
    store=ContactStore(path)
    assert not is_unified(path)
    state=store.snapshot();state['conversations']=[conversation()]
    store.activate(state,state['version'])
    assert is_unified(path)


def test_routes_listening_policies_and_subscribers_share_one_record(tmp_path):
    from butler.contact_store import ContactStore
    store=ContactStore(tmp_path/'b.db');state=store.snapshot()
    state['conversations']=[conversation(),conversation('G','group')]
    state['settings']={'bot':{'mention_names':['Bot']},'wechat':{'main_window':{'listen_all':True}}}
    store.activate(state,state['version'])
    assert store.channel_projection()['bot']['bound_users']==['A']
    assert store.channel_projection()['bot']['bound_groups']==['G']
    assert store.groups()=={'1':['A','G']}
    store.set_policy('A',{'role_skill':'other','allowed_skills':[],'heartbeat_enabled':False})
    assert store.policies()['A']['role_skill']=='other'
    store.set_groups({'1':['G'],'2':['A']})
    assert store.groups()=={'1':['G'],'2':['A']}
    state=store.snapshot();state['conversations'][0]['name']='Renamed'
    store.save(state,state['version'])
    assert store.groups()['2']==['Renamed']
    assert 'Renamed' in store.policies()
    assert store.channel_projection()['bot']['bound_users']==['Renamed']
    assert 'bound_users' not in store.snapshot()['settings']['bot']


def test_version_conflict_and_invalid_update_leave_state_unchanged(tmp_path):
    from butler.contact_store import ContactStore
    store=ContactStore(tmp_path/'b.db');state=store.snapshot();state['conversations']=[conversation()]
    saved=store.activate(state,state['version'])
    with pytest.raises(ValueError,match='version'):
        store.save(state,state['version'])
    broken=copy.deepcopy(saved);broken['conversations'].append(conversation())
    with pytest.raises(ValueError):store.save(broken,saved['version'])
    assert store.snapshot()==saved


def test_legacy_directory_projection_does_not_store_another_list(tmp_path):
    from butler.contact_store import ContactStore
    from butler.directory import DirectoryStore
    store=ContactStore(tmp_path/'b.db');state=store.snapshot();state['conversations']=[conversation()]
    store.activate(state,state['version'])
    directory=DirectoryStore(store.path)
    assert directory.contact_rows()[0]['name']=='A'
    legacy=directory.snapshot();legacy['channel']['bot']['bound_users']=[]
    directory.save(legacy,legacy['version'])
    assert not store.snapshot()['conversations'][0]['listening']
    assert store.policies()['A']['role_skill']=='role'


def test_runtime_policy_and_groups_ignore_retired_json(tmp_path):
    from butler.contact_store import ContactStore
    from butler.skill_policy import SkillPolicyStore
    from butler.groups import GroupStore
    store=ContactStore(tmp_path/'b.db');state=store.snapshot();state['conversations']=[conversation()]
    store.activate(state,state['version'])
    policies=SkillPolicyStore(str(tmp_path/'retired.json'),database=store.path)
    groups=GroupStore(str(tmp_path/'retired-groups.json'),database=store.path)
    assert policies.for_contact('A')['heartbeat_enabled']
    assert groups.users_of(1)==['A']
    groups.bind(2,'A')
    assert store.groups()['2']==['A']
    assert not (tmp_path/'retired.json').exists() and not (tmp_path/'retired-groups.json').exists()


def test_news_and_telegram_subscribers_read_active_database(tmp_path):
    from butler.contact_store import ContactStore
    from butler.telegram.service import read_subscribers
    from butler.news.delivery import subscribers
    store=ContactStore(tmp_path/'b.db');state=store.snapshot();state['conversations']=[conversation()]
    store.activate(state,state['version'])
    retired=tmp_path/'groups.json';retired.write_text('{"groups":{"1":["WRONG"]}}')
    assert read_subscribers(retired,database=store.path)==['A']
    assert subscribers(retired,database=store.path)==['A']
    store.set_groups({'1':[]})
    assert read_subscribers(retired,database=store.path)==[]
    assert subscribers(retired,database=store.path)==[]


def test_business_memory_tools_preserve_merged_conflict_variants(tmp_path):
    from butler.business import BusinessStore
    from butler.user_registry import UserRegistry
    from butler.contact_identity import merge_users
    from butler.contact_store import ContactStore
    business=BusinessStore(tmp_path/'b.db');registry=UserRegistry(business)
    with business.transaction() as db:
        a=registry._create(db,'group','G1','A')
        b=registry._create(db,'group','G2','B')
    business.set_memory(a['memory_owner'],'drink','tea')
    business.set_memory(b['memory_owner'],'drink','coffee')
    unified=ContactStore(business.path);unified.activate(unified.snapshot(),0)
    with business.transaction() as db:merge_users(db,b['user_id'],a['user_id'])
    assert {r['value'] for r in business.memories(a['memory_owner'])}=={'tea','coffee'}
    assert all(r.get('source_label') for r in business.memories(a['memory_owner']))
    business.set_memory(a['memory_owner'],'drink','water')
    assert {r['value'] for r in business.memories(a['memory_owner'])}=={'tea','coffee','water'}
    business.delete_memory(a['memory_owner'],'drink')
    assert business.memories(a['memory_owner'])==[]


def test_editing_uncontested_merged_memory_does_not_resurrect_old_value(tmp_path):
    from butler.business import BusinessStore
    from butler.user_registry import UserRegistry
    from butler.contact_identity import merge_users
    from butler.contact_store import ContactStore
    business=BusinessStore(tmp_path/'b.db');registry=UserRegistry(business)
    with business.transaction() as db:
        a=registry._create(db,'group','G1','A');b=registry._create(db,'group','G2','B');c=registry._create(db,'group','G3','C')
    business.set_memory(a['memory_owner'],'drink','tea')
    business.set_memory(c['memory_owner'],'drink','coffee')
    unified=ContactStore(business.path);unified.activate(unified.snapshot(),0)
    with business.transaction() as db:merge_users(db,b['user_id'],a['user_id'])
    business.set_memory(a['memory_owner'],'drink','water')
    with business.transaction() as db:merge_users(db,c['user_id'],a['user_id'])
    assert {r['value'] for r in business.memories(a['memory_owner'])}=={'water','coffee'}


def test_runtime_identity_store_uses_active_canonical_database(tmp_path):
    from butler.config import Config
    from butler.core import Butler
    from butler.contact_store import ContactStore
    path=tmp_path/'custom'/'contacts.sqlite3'
    unified=ContactStore(path);unified.activate(unified.snapshot(),0)
    cfg=Config(provider='codex',data_dir=str(tmp_path/'runtime'),contact_database=str(path))
    butler=Butler(cfg)
    try:assert butler.store.path==path
    finally:butler.hermes.close()


def contact_service(tmp_path):
    from butler.business import BusinessStore
    from butler.user_registry import UserRegistry
    from butler.contact_store import ContactStore
    from butler.contact_admin import ContactAdmin
    business=BusinessStore(tmp_path/'b.db');registry=UserRegistry(business)
    store=ContactStore(business.path);store.activate(store.snapshot(),0)
    return ContactAdmin(business.path),registry


def test_person_rename_merges_current_group_nickname_match(tmp_path):
    service,registry=contact_service(tmp_path)
    def save(**kw):return service.save({'version':service.read()['version'],**kw})
    save(action='create',name='Alice');save(action='create',name='Bob');save(action='create',name='Project',channel_type='group')
    rows=service.read()['rows'];a=next(r for r in rows if r['name']=='Alice');b=next(r for r in rows if r['name']=='Bob');g=next(r for r in rows if r['name']=='Project')
    save(action='membership',id=b['id'],group_id=g['id'],nickname='Engineer')
    with pytest.raises(ValueError,match='合并|归并'):
        save(action='person',id=a['id'],name='Engineer')
    save(action='person',id=a['id'],name='Engineer',confirm_merge=True)
    people=[r for r in service.read()['rows'] if r['kind']=='person']
    assert len(people)==1
    assert {c['name'] for c in people[0]['conversations']}=={'Alice','Bob'}
    assert people[0]['memberships'][0]['nickname']=='Engineer'


def test_membership_edit_rejects_stale_unified_person_save(tmp_path):
    service,registry=contact_service(tmp_path)
    created=service.save({'action':'create','version':1,'name':'Alice'})
    person=created['rows'][0];binding=person['bindings'][0]
    registry.update_binding(binding['binding_id'],binding['version'],enabled=False)
    assert service.read()['version']>created['version']
    with pytest.raises(ValueError,match='version'):
        service.save({'action':'person','version':created['version'],'id':person['id'],'enabled':True})
    assert not service.read()['rows'][0]['enabled']


def test_discovered_private_person_can_reuse_existing_private_binding(tmp_path):
    service,registry=contact_service(tmp_path)
    person=registry.observe('New friend','dm',nickname='New friend')
    before=service.read()
    saved=service.save({'action':'create','version':before['version'],'name':'New friend','person_id':person['user_id']})
    assert saved['total']==1
    assert saved['rows'][0]['id']==person['user_id']
    assert len(saved['rows'][0]['conversations'])==1
    assert registry.list_users()['total']==1


def test_inferred_destination_is_pending_until_its_route_is_reviewed(tmp_path):
    service,registry=contact_service(tmp_path)
    from butler.contact_store import ContactStore
    store=ContactStore(service.path);state=store.snapshot()
    c=conversation('OnlySubscriber');c['needs_route']=True;c['person_id']=''
    state['conversations']=[c];store.save(state,state['version'])
    assert service.read(kind='pending')['total']==1
    service.save({'action':'conversation','version':store.snapshot()['version'],'id':c['id'],
                  'name':c['name'],'uid':'known-route','profile':'default'})
    assert service.read(kind='pending')['total']==0


def test_group_listening_requires_global_bot_nickname(tmp_path):
    from butler.contact_store import ContactStore
    store=ContactStore(tmp_path/'b.db');state=store.snapshot();state['conversations']=[conversation('G','group')]
    with pytest.raises(ValueError,match='昵称|mention'):
        store.activate(state,0)
