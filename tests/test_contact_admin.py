"""Unified contact administration uses temporary, offline databases."""
import sqlite3

import pytest


def admin(tmp_path):
    from butler.identity.contact_admin import ContactAdmin
    from butler.identity.contact_store import ContactStore
    from butler.business import BusinessStore
    from butler.identity.user_registry import UserRegistry
    path = tmp_path / 'business.sqlite3'
    registry = UserRegistry(BusinessStore(path))
    store = ContactStore(path)
    store.activate(store.snapshot())
    return ContactAdmin(path), store, registry


def test_inactive_read_is_pure_and_refuses_edits(tmp_path):
    from butler.identity.contact_admin import ContactAdmin
    path = tmp_path / 'missing.sqlite3'
    service = ContactAdmin(path)
    assert service.read()['active'] is False
    assert not path.exists()
    with pytest.raises(ValueError, match='迁移'):
        service.save({'action': 'create', 'version': 0, 'name': '小王'})
    assert not path.exists()


def test_create_one_person_edit_route_and_reject_stale_version(tmp_path):
    service, store, registry = admin(tmp_path)
    first = service.save({'action': 'create', 'version': 1, 'name': '小王', 'channel_type': 'dm'})
    row = first['rows'][0]
    assert first['total'] == 1 and row['kind'] == 'person'
    assert row['conversations'][0]['listening'] is False
    service.save({'action': 'conversation', 'version': first['version'],
                  'id': row['conversations'][0]['id'], 'listening': True,
                  'subscriptions': [1, 2], 'uid': 'stable-route', 'session_key': 'old:{uid}'})
    with pytest.raises(ValueError, match='version conflict'):
        service.save({'action': 'person', 'version': first['version'], 'id': row['id'], 'name': '失效'})
    latest = service.read(id=row['id'])
    service.save({'action': 'person', 'version': latest['version'], 'id': row['id'], 'name': '王先生'})
    after = service.read(id=row['id'])['row']
    assert after['name'] == '王先生'
    assert after['conversations'][0]['uid'] == 'stable-route'
    assert after['conversations'][0]['subscriptions'] == [1, 2]
    assert after['conversations'][0]['name'] == '小王'  # window title is not a person's display name


def test_person_list_retains_each_group_nickname_and_disabled_binding(tmp_path):
    service, store, registry = admin(tmp_path)
    with registry.store.transaction() as db:
        person = registry._create(db, 'dm', '小王', '小王')
        group = registry._create(db, 'group', '项目群', '王工')
        other = registry._create(db, 'group', '同学群', '小王同学')
        db.execute('UPDATE user_bindings SET user_id=?,enabled=0 WHERE binding_id=?', (person['user_id'],group['binding_id']))
        db.execute('UPDATE user_bindings SET user_id=? WHERE binding_id=?', (person['user_id'],other['binding_id']))
        db.execute('DELETE FROM user_profiles WHERE user_id IN (?,?)', (group['user_id'],other['user_id']))
    result = service.read()
    assert result['total'] == 1
    memberships = result['rows'][0]['memberships']
    assert {(x['contact'], x['nickname']) for x in memberships} == {('项目群','王工'),('同学群','小王同学')}
    assert next(x for x in memberships if x['contact']=='项目群')['enabled'] == 0


def test_policy_save_needs_catalogue_validation_and_is_atomic(tmp_path):
    service, store, registry = admin(tmp_path)
    created = service.save({'action':'create','version':1,'name':'群','channel_type':'group'})
    row = created['rows'][0]
    payload = {'action':'conversation','version':created['version'],'id':row['id'],
               'listening':True,'policy':{'role_skill':'invented','allowed_skills':[],'heartbeat_enabled':False}}
    with pytest.raises(ValueError, match='目录'):
        service.save(payload)
    assert service.read()['version'] == created['version']
    assert store.snapshot()['conversations'][0]['listening'] is False


def test_contact_http_origin_and_conflicts(monkeypatch,tmp_path):
    from test_user_admin import running, request
    import dashboard.server as server
    service, store, registry = admin(tmp_path)
    monkeypatch.setattr(server,'dashboard_mode',lambda:'local')
    monkeypatch.setattr(server.Handler,'_contact_admin',lambda self:service,raising=False)
    with running(server.Handler) as base:
        payload={'action':'create','version':1,'name':'小王'}
        headers={'Origin':base,'Content-Type':'application/json','X-Wxbot-Contact-Action':'1'}
        assert request(base,'/api/contacts',payload)[0]==403
        assert request(base,'/api/contacts',payload,{**headers,'Origin':'https://bad.example'})[0]==403
        assert request(base,'/api/contacts',payload,headers)[0]==200
        assert request(base,'/api/contacts',payload,headers)[0]==409
        status,result=request(base,'/api/contacts')
        assert status==200 and result['total']==1


def test_link_keeps_one_person_all_memberships_memories_and_route_policies(tmp_path):
    service,store,registry=admin(tmp_path)
    left=service.save({'action':'create','version':1,'name':'小王'})
    right=service.save({'action':'create','version':left['version'],'name':'王工'})
    rows={r['name']:r for r in right['rows']}
    with registry.store.transaction() as db:
        registry.store.set_memory('user:'+rows['小王']['id'],'drink','tea',db=db)
        registry.store.set_memory('user:'+rows['王工']['id'],'drink','coffee',db=db)
    result=service.save({'action':'link_binding','version':right['version'],'id':rows['小王']['id'],
        'binding_id':rows['王工']['bindings'][0]['binding_id'],'binding_version':rows['王工']['bindings'][0]['version']})
    assert result['total']==1 and len(result['rows'][0]['conversations'])==2
    assert {v['value'] for v in result['rows'][0]['memory_conflicts']}=={'tea','coffee'}


def test_route_only_person_can_manage_memory_without_granting_identity(tmp_path):
    service,store,registry=admin(tmp_path)
    with registry.store.transaction() as db:
        db.execute("INSERT INTO user_profiles VALUES('route-person','小王',0,0)")
    memory=service.memory('route-person')
    assert memory['items']==[]
    result=service.save({'action':'memory_set','id':'route-person','version':1,'memory_version':0,'key':'drink','value':'tea'})
    assert service.memory('route-person')['items'][0]['value']=='tea'
    assert result['rows'][0]['bindings']==[]


def test_unified_config_does_not_read_or_edit_retired_sources(tmp_path):
    service,store,registry=admin(tmp_path)
    from dashboard.config_view import ConfigView
    from dashboard.config_editor import ConfigEditor
    bt=tmp_path/'config.butler.toml';wx=tmp_path/'config.wxbot.toml'
    for path in (bt,wx):path.write_text('[directory]\ndatabase="business.sqlite3"\n',encoding='utf-8')
    (tmp_path/'data/cache').mkdir(parents=True)
    for name in ('butler_heartbeat.json','butler_groups.json'):(tmp_path/'data/cache'/name).write_text('malformed retired file',encoding='utf-8')
    view=ConfigView(wx,bt,tmp_path/'data',repo_root=tmp_path,log_config_path=tmp_path/'config.log.toml')
    data=view.read()
    assert next(s for s in data['sources'] if s['id']=='contacts')['read_only']
    assert not any(s['id'] in {'policies','groups','log_policies','log_groups'} for s in data['sources'])
    with pytest.raises(ValueError,match='只读'):
        ConfigEditor(view).save({'acknowledge':True,'source':'directory','version':'1','changes':[{'path':['contacts'],'op':'set','value':[]}]})


@pytest.mark.parametrize('provider,mode',[('deepseek','direct'),('butler','external')])
def test_nonlocal_install_can_edit_local_listening_without_local_identity(tmp_path,provider,mode):
    from butler.runtime.install_wizard import install,Connection
    from butler.identity.contact_store import is_unified
    from butler.identity.directory import DirectoryStore
    from dashboard.config_view import ConfigView
    from dashboard.config_editor import ConfigEditor
    from wxbot.config import load_config
    install(tmp_path,Connection(provider=provider,model='test',url='https://remote.example/v1/handle'),nickname='Bot')
    database=tmp_path/'data/business.sqlite3'
    view=ConfigView(tmp_path/'config.wxbot.toml',tmp_path/'config.butler.toml',tmp_path/'data',
                    repo_root=tmp_path,log_config_path=tmp_path/'config.log.toml')
    data=view.read()
    assert data['connection']['mode']==mode
    assert not is_unified(database)
    source=next(s for s in data['sources'] if s['id']=='directory')
    original=(tmp_path/'config.wxbot.toml').read_bytes()
    changes=[{'path':['channel','bot',key],'op':'set','value':value} for key,value in
        [('bound_users',['Alice']),('bound_groups',['项目群']),('mention_names',['新机器人昵称'])]]
    assert ConfigEditor(view).save({'acknowledge':True,'source':'directory','version':source['version'],'changes':changes})['ok']
    runtime=load_config(tmp_path/'config.wxbot.toml')
    assert runtime['bot']['bound_users']==['Alice']
    assert runtime['bot']['bound_groups']==['项目群']
    assert runtime['bot']['mention_names']==['新机器人昵称']
    assert (tmp_path/'config.wxbot.toml').read_bytes()==original
    assert DirectoryStore(database).snapshot()['channel']['bot']['bound_users']==['Alice']
    with sqlite3.connect(database) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('user_profiles','user_bindings')").fetchone()

