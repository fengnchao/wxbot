import json

from butler.config import Config
from butler.agent.core import Butler
from test_user_registry import avatar


def make(tmp_path):
    cfg=Config(provider='codex',data_dir=str(tmp_path/'data'))
    b=Butler(cfg)
    path=cfg.heartbeat_config_path()
    from pathlib import Path
    Path(path).write_text(json.dumps({'users':{'群':{'role_skill':'butler-companion','allowed_skills':['butler-memory']}}}),encoding='utf-8')
    return b


def test_runtime_resolves_fixed_member_recall_and_mentions(tmp_path):
    b=make(tmp_path)
    a=b.registry.create('group','群','甲',avatar())
    m=b.registry.memories(a['binding_id'])
    b.registry.change_memory(a['binding_id'],'饮食','喜欢面条',m['version'])
    seen=[]
    b.hermes.chat=lambda c,text,**kw: seen.append((c,text,kw))or '好的'
    b.hermes.session_id=lambda *a,**kw:'test-thread'
    result=b.handle('群','今天吃什么',channel_type='group',member_key='raw-hash',avatar=avatar(),msg_id='r1')
    assert seen[0][0].user_id==a['user_id']
    assert '喜欢面条'in seen[0][2]['extra_system']
    assert result.meta['mention_name']=='甲'
    assert result.meta['user_id']==a['user_id']


def test_group_public_context_is_shared_but_private_memories_are_not(tmp_path):
    b=make(tmp_path)
    a=b.registry.create('group','群','甲',avatar())
    other=b.registry.create('group','群','乙',avatar(8))
    b.registry.change_memory(other['binding_id'],'秘密','仅属于乙',0)
    b.group_context.archive('其他群','o',[{'text':'其他群的内容'}])
    b.group_context.archive('群','b',[{'text':'乙公开说八点出发','member_name':'乙'}])
    boundary=b.group_context.archive('群','r2',[{'text':'几点出发','member_name':'甲'}])['seq']
    seen=[]
    b.hermes.chat=lambda c,text,**kw:seen.append(kw['extra_system'])or '八点'
    b.hermes.session_id=lambda *a,**kw:'test-thread'
    b.handle('群','几点出发',channel_type='group',member_key='raw',avatar=avatar(),group_context_seq=boundary,msg_id='r2')
    assert '乙公开说八点出发'in seen[0]
    assert '仅属于乙'not in seen[0]and'其他群的内容'not in seen[0]
    assert '几点出发'not in seen[0]


def test_unknown_group_has_no_mention_or_recalled_memory(tmp_path):
    b=make(tmp_path)
    seen=[]
    b.hermes.chat=lambda c,text,**kw:seen.append((c,kw))or '好的'
    b.hermes.session_id=lambda *a,**kw:'test-thread'
    result=b.handle('群','记住我',channel_type='group',member_key='unknown-x',msg_id='r3')
    assert seen[0][0].identity_status=='unknown'
    assert result.meta['mention_name']==''
    assert b.registry.list_users()['total']==0


def test_silent_group_archive_registers_users_without_a_model_call(tmp_path):
    b = make(tmp_path)
    b.hermes.chat = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('no model'))
    messages = [{'text': '普通消息', 'member_key': 'observed-a', 'member_name': '甲', 'avatar': avatar()}]
    b.archive_group('群', 'silent', messages)
    b.archive_group('群', 'silent', messages)
    rows = b.registry.list_users()['rows']
    assert len(rows) == 1 and rows[0]['nickname'] == '甲'
    assert rows[0]['memory_count'] == 0 and rows[0]['avatar']


def test_observed_user_without_avatar_is_visible_but_has_no_memory_authority(tmp_path):
    b = make(tmp_path)
    b.observe_users('群', 'group', [{'member_key': 'stable-observation', 'member_name': '甲'}])
    row = b.registry.list_users()['rows'][0]
    assert row['status'] == 'observed' and row['memory_count'] == 0
    c = b._resolved_contact(b._contact('群', 'group', 'stable-observation'))
    assert not c.memory_owner and c.identity_status == 'observed'
    b.registry.update_binding(row['binding_id'], row['version'], nickname='甲')
    assert b._resolved_contact(b._contact('群', 'group', 'stable-observation')).user_id == row['user_id']


def test_auto_group_user_with_no_nickname_does_not_mention_placeholder(tmp_path):
    b = make(tmp_path)
    b.observe_users('群', 'group', [{'member_key': 'raw', 'avatar': avatar()}])
    b.hermes.chat = lambda *a, **kw: '收到'
    b.hermes.session_id = lambda *a, **kw: 'thread'
    result = b.handle('群', '你好', channel_type='group', member_key='raw', avatar=avatar(), msg_id='auto')
    assert result.meta['user_id'] and result.meta['mention_name'] == ''


def test_auto_group_user_does_not_import_unconfirmed_hash_only_legacy_notes(tmp_path):
    from butler.backends.codex import owner_key
    b = make(tmp_path)
    b.store.set_memory(owner_key(b._contact('群','group','old-hash')), 'private', 'legacy-secret')
    seen = []
    b.hermes.chat = lambda c, text, **kw: seen.append(kw) or '收到'
    b.hermes.session_id = lambda *a, **kw: 'thread'
    result = b.handle('群','你好',channel_type='group',member_key='old-hash',avatar=avatar(),msg_id='fresh')
    row = b.registry.list_users()['rows'][0]
    assert result.meta['user_id'] == row['user_id'] and row['memory_count'] == 0
    assert 'legacy-secret' not in json.dumps(seen)


def test_group_archive_http_requires_admin_auth_and_handle_transports_avatar(tmp_path):
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.request import Request,build_opener,ProxyHandler
    from urllib.error import HTTPError
    from butler.server import make_handler
    b=make(tmp_path);b.cfg.token='test-secret'
    b.registry.create('group','群','甲',avatar())
    b.hermes.chat=lambda *a,**kw:'收到'
    b.hermes.session_id=lambda *a,**kw:'test-thread'
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(b,b.cfg))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    opener=build_opener(ProxyHandler({}))
    def post(path,payload,token='test-secret'):
        request=Request('http://127.0.0.1:'+str(server.server_port)+path,
            data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with opener.open(request)as response:return json.load(response)
    try:
        import pytest
        observation = {'contact':'alice','channel_type':'dm','messages':[{}]}
        with pytest.raises(HTTPError) as error:
            post('/v1/users/observe',observation,'bad')
        assert error.value.code == 401
        assert post('/v1/users/observe',observation)['users'][0]['user_id']
        assert b.registry.list_users(contact='alice')['total'] == 1
        payload={'contact':'群','source_id':'http-1','messages':[{'text':'你好','member_name':'甲'}]}
        with pytest.raises(HTTPError)as error:post('/v1/group/archive',payload,'bad')
        assert error.value.code==401
        seq=post('/v1/group/archive',payload)['seq']
        actual=post('/v1/handle',{'contact':'群','text':'你好','msg_id':'http-1','channel_type':'group',
            'member_key':'raw','avatar':avatar(),'group_context_seq':seq})
        assert actual['meta']['mention_name']=='甲'
    finally:
        server.shutdown();server.server_close()


def test_group_context_limits_are_configurable_and_bounded(tmp_path):
    import pytest
    from butler.config import load
    path=tmp_path/'config.toml'
    path.write_text('[context]\ngroup_messages=12\ngroup_characters=2400\n',encoding='utf-8')
    cfg=load(path)
    assert cfg.group_context_messages==12 and cfg.group_context_characters==2400
    path.write_text('[context]\ngroup_messages=true\n',encoding='utf-8')
    with pytest.raises(ValueError):load(path)


def test_reset_uses_the_same_resolved_identity_as_chat(tmp_path):
    b=make(tmp_path)
    row=b.registry.create('group','群','甲',avatar())
    seen=[]
    b.hermes.reset=lambda c,**kw:seen.append(c)
    b.hermes.session_id=lambda *a,**kw:'fresh'
    b.reset('群',channel_type='group',member_key='raw',avatar=avatar())
    assert seen[-1].binding_id==row['binding_id']
    b.handle('alice','/reset')
    expected=b.registry.resolve('alice','dm')['binding_id']
    b.reset('alice')
    assert seen[-1].binding_id==expected


def test_linked_memories_do_not_share_reminder_authority(tmp_path):
    from dataclasses import replace
    from butler.backends.codex import owner_key, tool_owner_key
    import pytest
    b=make(tmp_path)
    a=b.registry.create('group','群','甲',avatar())
    d=b.registry.create('dm','alice','Alice',avatar(8))
    b.registry.link(a['binding_id'],d['binding_id'],a['version'])
    group=b._resolved_contact(replace(b._contact('群','group','a'),avatar=avatar()))
    dm=b._resolved_contact(b._contact('alice','dm'))
    policy={'role_skill':'butler-companion','allowed_skills':['butler-memory','create-cron-job']}
    b.tools.policy_loader=lambda name:policy
    def token(c,request_id):
        return b.tools.issue(owner=tool_owner_key(c),memory_owner=owner_key(c),contact=c.name,policy=policy,request_id=request_id)
    private=token(dm,'private')
    reminder=b.tools.call('reminder_create',{'text':'private appointment','schedule':'in 2m'},private,'create')
    public=token(group,'group')
    assert b.tools.call('reminder_list',{},public,'list')['items']==[]
    with pytest.raises(PermissionError):b.tools.call('reminder_cancel',{'id':reminder['id']},public,'cancel')
    b.tools.call('memory_set',{'key':'shared','value':'yes'},private,'memory')
    assert b.tools.call('memory_get',{},public,'read')['items'][0]['value']=='yes'


def test_legacy_reminders_follow_verified_binding_without_sharing(tmp_path):
    from butler.backends.codex import owner_key,tool_owner_key
    b=make(tmp_path)
    old=b._contact('alice','dm')
    with b.store.transaction()as db:
        reminder=b.store.create_reminder(owner_key(old),'alice','existing','in 2m',db=db)
    resolved=b._resolved_contact(old)
    assert b.store.reminders(tool_owner_key(resolved))[0]['id']==reminder['id']


def test_hermes_groups_can_archive_and_receive_public_context(make_home):
    home=make_home(replies=['好'],pending_items=[],contacts=[{'name':'群','profile':'p','uid':'g','channel_type':'group'}])
    b=home.butler
    b.archive_group('群','old',[{'text':'此前公开发言','member_name':'乙'}])
    seq=b.archive_group('群','current',[{'text':'接着说','member_name':'甲'}])['seq']
    result=b.handle('群','接着说',msg_id='current',channel_type='group',member_key='a',group_context_seq=seq)
    assert result.reply=='好'
    assert '此前公开发言'in home.hermes.calls[0]['extra_system']
