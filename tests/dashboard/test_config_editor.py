import json
from pathlib import Path
import tomllib

import pytest

from dashboard.config_view import ConfigView
from support.paths import REPO_ROOT


def setup_editor(tmp_path):
    from dashboard.config_editor import ConfigEditor
    wx=tmp_path/'wx.toml';bt=tmp_path/'bt.toml';home=tmp_path/'hermes'
    home.mkdir()
    wx.write_text('# 我的配置\n[bot]\nmention_names = ["Bot"] # 保留\n[model]\nbackend="butler"\n',encoding='utf-8')
    bt.write_text('# 连接地址\n[hermes]\nurl = "http://127.0.0.1:8642" # 地址注释\napi_key="original-secret"\nroot='+json.dumps(str(home))+'\n[custom]\nnote="unchanged"\n',encoding='utf-8')
    view=ConfigView(wx,bt,home,repo_root=tmp_path,log_config_path=tmp_path/'log.toml')
    return ConfigEditor(view),view,wx,bt


def payload(view,source,changes):
    data=view.read()
    version=next(s['version'] for s in data['sources'] if s['id']==source)
    return {'source':source,'version':version,'changes':changes,'acknowledge':True}


def test_edit_hermes_url_preserves_comments_other_values_and_makes_backup(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    before=bt.read_bytes()
    result=editor.save(payload(view,'butler',[{'path':['hermes','url'],'op':'set','value':'http://10.0.0.2:8642'}]))
    assert result['ok'] and result['restart']==['Butler']
    assert Path(result['backup']).read_bytes()==before
    text=bt.read_text(encoding='utf-8')
    assert '# 连接地址' in text and '# 地址注释' in text and 'note="unchanged"' in text
    actual=tomllib.loads(text)
    assert actual['hermes']['url']=='http://10.0.0.2:8642'
    assert actual['hermes']['api_key']=='original-secret'


def test_editor_does_not_return_secrets_and_requires_explicit_secret_changes(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    data=view.read()
    wire=json.dumps(data,ensure_ascii=False)
    assert 'original-secret' not in wire
    row=next(r for s in data['sections'] for r in s['rows'] if r['key']=='butler.hermes.api_key')
    assert row['editor']=='secret' and row['editable'] and row['label']
    for value in ('已配置（隐藏）','未配置',''):
        with pytest.raises(ValueError):editor.save(payload(view,'butler',[{'path':['hermes','api_key'],'op':'set','value':value}]))
    editor.save(payload(view,'butler',[{'path':['hermes','api_key'],'op':'clear'}]))
    assert tomllib.loads(bt.read_text(encoding='utf-8'))['hermes']['api_key']==''


def test_old_editor_cannot_overwrite_new_file_or_unconfigured_paths(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    request=payload(view,'butler',[{'path':['hermes','url'],'op':'set','value':'http://new:8642'}])
    bt.write_text(bt.read_text(encoding='utf-8')+'\n# concurrent edit\n',encoding='utf-8')
    before=bt.read_bytes()
    with pytest.raises(ValueError,match='变化|更新'):editor.save(request)
    assert bt.read_bytes()==before
    with pytest.raises(ValueError):editor.save({**request,'source':str(tmp_path/'other')})
    assert not (tmp_path/'other').exists()


@pytest.mark.parametrize('path,value',[
    (['hermes','url'],'javascript:alert(1)'),(['hermes','timeout'],-1),
    (['hermes','profile_in_path'],'false'),(['server','port'],70000),
    (['contacts'],[{'name':'A','uid':'非ASCII','profile':'p'}]),
])
def test_invalid_settings_are_rejected_without_writes(tmp_path,path,value):
    editor,view,wx,bt=setup_editor(tmp_path)
    before=bt.read_bytes()
    with pytest.raises(ValueError):editor.save(payload(view,'butler',[{'path':path,'op':'set','value':value}]))
    assert bt.read_bytes()==before


def test_default_reset_and_new_runtime_settings_are_written_to_the_real_sources(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    editor.save(payload(view,'wxbot',[{'path':['wechat','typing','chunk_size'],'op':'set','value':3},
        {'path':['queue','failure_discard_seconds'],'op':'set','value':90}]))
    cfg=tomllib.loads(wx.read_text(encoding='utf-8'))
    assert cfg['wechat']['typing']['chunk_size']==3 and cfg['queue']['failure_discard_seconds']==90
    editor.save(payload(view,'wxbot',[{'path':['wechat','typing','chunk_size'],'op':'default'}]))
    assert 'chunk_size' not in tomllib.loads(wx.read_text(encoding='utf-8'))['wechat']['typing']


def test_missing_log_config_can_be_saved_and_read_on_next_start(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    result=editor.save(payload(view,'log_config',[{'path':['server','port'],'op':'set','value':9898}]))
    from dashboard.settings import load_settings
    assert result['restart']==['log']
    assert load_settings(tmp_path/'log.toml')['server']['port']==9898


def test_groups_save_preserves_other_json_fields_and_validates_members(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    folder=tmp_path/'hermes'/'cache';folder.mkdir()
    target=folder/'butler_groups.json'
    target.write_text(json.dumps({'version':1,'note':'keep','groups':{'1':['A']}}),encoding='utf-8')
    editor.save(payload(view,'groups',[{'path':['groups','1'],'op':'set','value':['A','B']}]))
    assert json.loads(target.read_text(encoding='utf-8'))['note']=='keep'
    before=target.read_bytes()
    with pytest.raises(ValueError):editor.save(payload(view,'groups',[{'path':['groups','1'],'op':'set','value':[2]}]))
    assert target.read_bytes()==before


def test_concurrent_saves_use_one_original_version(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from dashboard.config_editor import ConfigEditor
    editor,view,wx,bt=setup_editor(tmp_path)
    a=payload(view,'butler',[{'path':['hermes','timeout'],'op':'set','value':900}])
    b=payload(view,'butler',[{'path':['hermes','timeout'],'op':'set','value':901}])
    def save(body):
        own=ConfigView(wx,bt,tmp_path/'hermes',log_config_path=tmp_path/'log.toml')
        try:return ConfigEditor(own).save(body)['ok']
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,[a,b]))
    assert sorted(results)==[False,True]
    assert tomllib.loads(bt.read_text(encoding='utf-8'))['hermes']['timeout'] in (900,901)
    assert len(list(tmp_path.glob('bt.toml.config-backup-*')))==1


def test_failed_atomic_replace_keeps_original_and_backup(tmp_path,monkeypatch):
    import dashboard.config_editor as module
    editor,view,wx,bt=setup_editor(tmp_path)
    before=bt.read_bytes()
    def fail(*args):raise OSError('simulated write failure')
    monkeypatch.setattr(module.os,'replace',fail)
    with pytest.raises(OSError):editor.save(payload(view,'butler',[{'path':['hermes','timeout'],'op':'set','value':900}]))
    assert bt.read_bytes()==before
    assert next(tmp_path.glob('bt.toml.config-backup-*')).read_bytes()==before
    assert list(tmp_path.glob('.bt.toml-*.tmp'))==[]


def test_nested_hidden_credentials_survive_reordered_contact_edit(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    with bt.open('a',encoding='utf-8') as fh:
        fh.write('\n[[contacts]]\nname="A"\nuid="A"\nsession_key="keep-this-session"\n[[contacts]]\nname="B"\nuid="B"\n')
    rows=[{'name':'B','uid':'B'},{'name':'A','uid':'A','label':'新称呼','session_key':'已配置（隐藏）'}]
    editor.save(payload(view,'butler',[{'path':['contacts'],'op':'set','value':rows}]))
    actual=tomllib.loads(bt.read_text(encoding='utf-8'))['contacts']
    assert actual[1]['session_key']=='keep-this-session' and actual[1]['label']=='新称呼'
    assert 'keep-this-session' not in json.dumps(view.read())


def test_policy_uses_skill_validator_and_keeps_tool_role_boundary(tmp_path):
    from dashboard.config_editor import ConfigEditor
    editor,view,wx,bt=setup_editor(tmp_path)
    with bt.open('a',encoding='utf-8') as fh:fh.write('\n[[contacts]]\nname="A"\nuid="A"\n')
    body=payload(view,'policies',[{'path':['users'],'op':'set','value':{'A':{'role_skill':'role','allowed_skills':['tool'],'heartbeat_enabled':True}}}])
    with pytest.raises(ValueError):editor.save(body)
    def validate(users,changed,cfg):
        assert changed==['A']
        if users['A']['role_skill']!='role' or users['A']['allowed_skills']!=['tool']:raise ValueError('wrong skill type')
    result=ConfigEditor(view,policy_validator=validate).save(body)
    assert result['ok'] and result['restart']==[]
    path=tmp_path/'hermes'/'cache'/'butler_heartbeat.json'
    assert json.loads(path.read_text(encoding='utf-8'))['users']['A']['heartbeat_enabled']


def test_queue_countdown_uses_the_saved_timeout_without_mutating_queue(tmp_path):
    from dashboard.queue_view import QueueView
    from wxbot.queue_store import QueueStore
    editor,view,wx,bt=setup_editor(tmp_path)
    path=tmp_path/'queue.db';store=QueueStore(path)
    task=store.enqueue_delivery('A','reply',now=0);store.claim_delivery(now=0)
    store.finish_delivery(task,'blocked',now=10,error='focus')
    editor.save(payload(view,'wxbot',[{'path':['queue','database'],'op':'set','value':str(path)},
        {'path':['queue','failure_discard_seconds'],'op':'set','value':60}]))
    data=QueueView(**view.queue_options()).read(now=20)
    assert data['outbox'][0]['discard_at']==70 and data['outbox'][0]['remaining_seconds']==50
    assert store.get_delivery(task)['state']=='blocked'
    store.close()


def test_configuration_http_save_is_confirmed_local_and_secret_free(tmp_path,monkeypatch):
    import importlib.util,threading,urllib.request,urllib.error
    from http.server import ThreadingHTTPServer
    editor,view,wx,bt=setup_editor(tmp_path)
    for key,path in (('WXBOT_CONFIG',wx),('BUTLER_CONFIG',bt),('LOG_CONFIG',tmp_path/'log.toml')):
        monkeypatch.setenv(key,str(path))
    spec=importlib.util.spec_from_file_location('_config_editor_http',REPO_ROOT/'src'/'dashboard'/'server.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    server=ThreadingHTTPServer(('127.0.0.1',0),type('TestHandler',(module.Handler,),{'home':str(tmp_path/'hermes')}))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    body=payload(view,'butler',[{'path':['hermes','api_key'],'op':'set','value':'new-secret-value'}])
    def post(headers):
        req=urllib.request.Request(base+'/api/configuration',data=json.dumps(body).encode(),headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as exc:return exc.code,json.load(exc)
    headers={'Content-Type':'application/json','X-Wxbot-Config-Action':'1','Origin':base}
    try:
        assert post({'Content-Type':'application/json'})[0]==403
        assert post({**headers,'Host':'attacker.example:'+str(server.server_port),'Origin':'http://attacker.example:'+str(server.server_port)})[0]==403
        status,result=post(headers)
        assert status==200 and result['restart']==['Butler']
        assert 'new-secret-value' not in json.dumps(result)
        assert post(headers)[0]==409
        with urllib.request.urlopen(base+'/api/configuration',timeout=3) as response:data=json.load(response)
        assert 'new-secret-value' not in json.dumps(data)
        assert tomllib.loads(bt.read_text(encoding='utf-8'))['hermes']['api_key']=='new-secret-value'
    finally:
        server.shutdown();server.server_close();thread.join(2)


def test_unknown_numeric_parameters_keep_their_existing_type_and_range(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    with bt.open('a',encoding='utf-8') as fh:fh.write('\n[extra]\nzero=0\n')
    editor.save(payload(view,'butler',[{'path':['extra','zero'],'op':'set','value':-2}]))
    assert tomllib.loads(bt.read_text(encoding='utf-8'))['extra']['zero']==-2


def test_literal_dotted_keys_edit_the_correct_field(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    with bt.open('a',encoding='utf-8') as fh:fh.write('\n[extra]\n"a.b"="old"\n')
    editor.save(payload(view,'butler',[{'path':['extra','a.b'],'op':'set','value':'new'}]))
    assert tomllib.loads(bt.read_text(encoding='utf-8'))['extra']['a.b']=='new'


def test_redacted_url_cannot_overwrite_its_hidden_token_with_stars(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    bt.write_text('[hermes]\nurl="http://old:8642?token=url-secret-123"\n',encoding='utf-8')
    data=view.read()
    row=next(r for s in data['sections'] for r in s['rows'] if r['key']=='butler.hermes.url')
    request=payload(view,'butler',[{'path':['hermes','url'],'op':'set','value':row['value'].replace('old','new')}])
    before=bt.read_bytes()
    with pytest.raises(ValueError,match='完整|隐藏'):editor.save(request)
    assert bt.read_bytes()==before
    editor.save(payload(view,'butler',[{'path':['hermes','url'],'op':'set','value':'http://new:8642?token=explicit-new-token'}]))
    assert tomllib.loads(bt.read_text(encoding='utf-8'))['hermes']['url'].endswith('token=explicit-new-token')


@pytest.mark.parametrize('secret',['timeout','butler','integer','ok'])
def test_secrets_matching_schema_words_cannot_rewrite_field_identifiers(tmp_path,secret):
    editor,view,wx,bt=setup_editor(tmp_path)
    bt.write_text('[hermes]\napi_key='+json.dumps(secret)+'\n',encoding='utf-8')
    data=view.read()
    source=next(s for s in data['sources'] if s['id']=='butler')
    row=next(r for s in data['sections'] for r in s['rows'] if r['key']=='butler.hermes.timeout')
    assert row['path']==['hermes','timeout'] and row['editor']=='integer' and source['status']=='ok'
    editor.save(payload(view,'butler',[{'path':row['path'],'op':'set','value':900}]))
    actual=tomllib.loads(bt.read_text(encoding='utf-8'))['hermes']
    assert actual['timeout']==900 and '***' not in actual


def test_renaming_contact_preserves_hidden_session_using_stable_identity(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    with bt.open('a',encoding='utf-8') as fh:fh.write('\n[[contacts]]\nname="A"\nuid="u1"\nprofile="p"\nsession_key="private-template"\n')
    rows=[{'name':'B','uid':'u1','profile':'p','session_key':'已配置（隐藏）'}]
    editor.save(payload(view,'butler',[{'path':['contacts'],'op':'set','value':rows}]))
    assert tomllib.loads(bt.read_text(encoding='utf-8'))['contacts'][0]['session_key']=='private-template'


def test_contacts_cannot_collide_after_consumer_trims_names(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    rows=[{'name':'A','uid':'u1'},{'name':' A ','uid':'u2'}]
    with pytest.raises(ValueError):editor.save(payload(view,'butler',[{'path':['contacts'],'op':'set','value':rows}]))


def test_changing_uid_never_inherits_another_contacts_hidden_session(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    with bt.open('a',encoding='utf-8') as fh:
        fh.write('\n[[contacts]]\nname="A"\nuid="u1"\nsession_key="session-A"\n[[contacts]]\nname="B"\nuid="u2"\nsession_key="session-B"\n')
    rows=[{'name':'A','uid':'u2','session_key':'已配置（隐藏）'},
          {'name':'B','uid':'u2','session_key':'已配置（隐藏）'}]
    editor.save(payload(view,'butler',[{'path':['contacts'],'op':'set','value':rows}]))
    actual=tomllib.loads(bt.read_text(encoding='utf-8'))['contacts']
    assert actual[0]['session_key']=='session-A' and actual[1]['session_key']=='session-B'


def test_ambiguous_contact_merge_refuses_to_guess_a_hidden_session(tmp_path):
    editor,view,wx,bt=setup_editor(tmp_path)
    with bt.open('a',encoding='utf-8') as fh:
        fh.write('\n[[contacts]]\nname="A"\nuid="u1"\nsession_key="session-A"\n[[contacts]]\nname="B"\nuid="u2"\nsession_key="session-B"\n')
    before=bt.read_bytes()
    rows=[{'name':'B','uid':'u1','session_key':'已配置（隐藏）'}]
    with pytest.raises(ValueError,match='隐藏|歧义'):editor.save(payload(view,'butler',[{'path':['contacts'],'op':'set','value':rows}]))
    assert bt.read_bytes()==before
