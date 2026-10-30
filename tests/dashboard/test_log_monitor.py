import importlib.util
import json
import sqlite3
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from dashboard.config_view import ConfigView
from dashboard.queue_view import QueueView
from wxbot.queue_store import Incoming, QueueStore
from support.paths import REPO_ROOT


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """首页改为 302 到 /app/：测试直接读跳转头，不跟随到前端产物。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def test_queue_explains_previous_block_and_reads_without_changing_running_tasks(tmp_path):
    path=tmp_path/'queue.db'
    store=QueueStore(path, failure_timeout_seconds=180)
    store.capture('A',[],[Incoming('old')],now=0)
    store.prepare(quiet=0,max_wait=10,prefix='/',now=0)
    batch=store.claim_batch(now=0)
    store.finish_batch_parts(batch.id,('old reply','part two'),now=0)
    d=store.claim_delivery(now=0)
    store.finish_delivery(d.id,'blocked',now=2,error='输入校验失败')
    store.capture('A',[],[Incoming('new')],now=3)
    store.capture('B',[],[Incoming('B question')],now=3)
    before=[store.records(t) for t in ('inbox','batches','outbox')]
    data=QueueView(path, failure_timeout_seconds=180).read(now=20)
    a=next(u for u in data['contacts'] if u['contact']=='A')
    assert a['reason']['code']=='blocked'
    assert a['reason']['record_id']==d.id and a['reason']['error']=='输入校验失败'
    assert a['reason']['commands']['skip'].endswith('--delivery')
    assert a['unbatched']==1
    b=next(u for u in data['contacts'] if u['contact']=='B')
    assert b['reason']['code']=='ready_to_merge'
    assert data['outbox'][0]['part_count']==2
    assert data['actions_enabled']
    assert a['reason']['discard_at']==182 and a['reason']['remaining_seconds']==162
    assert data['outbox'][0]['failed_at']==2
    assert data['events'][-1]['action']=='failed'
    assert [store.records(t) for t in ('inbox','batches','outbox')]==before
    store.close()


def test_queue_filters_paginates_and_missing_file_stays_missing(tmp_path):
    path=tmp_path/'q.db'
    store=QueueStore(path)
    for name in ('A','B','A'):
        store.capture(name,[],[Incoming(name)],now=0)
    view=QueueView(path)
    page=view.read(contact='A',limit=1,offset=1,now=0)
    assert len(page['inbox'])==1 and page['inbox'][0]['contact']=='A'
    assert page['pages']['inbox']['total']==2
    assert view.read(contact="' OR 1=1 --")['inbox']==[]
    assert view.read(state='blocked')['inbox']==[]
    store.close()
    missing=tmp_path/'missing.db'
    assert QueueView(missing).read()['status']=='missing'
    assert not missing.exists() and not Path(str(missing)+'.lock').exists()


def test_queue_legacy_is_readonly_and_failed_query_does_not_create_files(tmp_path):
    from test_queue_migration import legacy
    path=tmp_path/'old.db'
    legacy(path)
    before=path.read_bytes()
    data=QueueView(path).read()
    assert data['status']=='ok' and data['outbox'][0]['part_seq']==1
    assert path.read_bytes()==before and not Path(str(path)+'.lock').exists()
    broken=tmp_path/'bad.db'
    broken.write_text('not sqlite',encoding='utf-8')
    assert QueueView(broken).read()['status']=='error'


def test_legacy_zero_failure_time_is_not_replaced_by_submission_time():
    deadline=QueueView._deadline({'finished_at':0,'submitted_at':5,'created_at':1},20,failure_timeout_seconds=180)
    assert deadline['discard_at']==180


def test_later_blocked_part_points_to_delivery_instead_of_model_batch(tmp_path):
    path=tmp_path/'q.db'
    s=QueueStore(path)
    s.capture('A',[],[Incoming('hi')],now=0)
    s.prepare(quiet=0,max_wait=10,prefix='/',now=0)
    b=s.claim_batch(now=0)
    s.finish_batch_parts(b.id,('one','two'),now=0)
    second=s.records('outbox')[1]
    s.finish_delivery(second['id'],'blocked',now=1,error='bad second')
    reason=QueueView(path).read()['contacts'][0]['reason']
    assert reason['record_id']==second['id'] and reason['record_kind']=='outbox'
    assert reason['commands']['retry'].endswith('--delivery --acknowledge')
    s.close()


def configs(tmp_path):
    wx=tmp_path/'wx.toml'
    bt=tmp_path/'butler.toml'
    home=tmp_path/'hermes'
    (home/'cache').mkdir(parents=True)
    wx.write_text('[bot]\nmention_names=["Bot"]\n[model]\nbackend="butler"\napi_key="wx-secret-123"\n[butler]\ntoken="butler-secret-456"\n[custom]\napiUrl="https://bob:pass@example.test/v1?access_token=query-secret-789"\nAuthorization="Bearer header-secret"\n',encoding='utf-8')
    bt.write_text('[hermes]\nroot='+json.dumps(str(home))+'\napi_key="hermes-secret-000"\n[[contacts]]\nname="101"\nuid="101"\nprofile="p"\n',encoding='utf-8')
    (home/'cache'/'butler_heartbeat.json').write_text(json.dumps({'users':{'101':{'role_skill':'paimon','allowed_skills':['tool'],'heartbeat_enabled':True}}}),encoding='utf-8')
    (home/'cache'/'butler_groups.json').write_text(json.dumps({'groups':{'1':['101']}}),encoding='utf-8')
    return wx,bt,home


def test_config_includes_raw_defaults_fixed_typing_and_dynamic_policies_and_redacts(tmp_path):
    wx,bt,home=configs(tmp_path)
    data=ConfigView(wx,bt,home).read()
    wire=json.dumps(data,ensure_ascii=False)
    for secret in ('wx-secret-123','butler-secret-456','hermes-secret-000','query-secret-789','header-secret','bob:pass'):
        assert secret not in wire
    assert 'paimon' in wire and 'mention_names' in wire and 'allowed_skills' in wire
    rows={r['key']:r for section in data['sections'] for r in section['rows']}
    assert rows['wxbot.queue.quiet_seconds']['value']==3
    assert rows['wxbot.queue.quiet_seconds']['origin']=='default'
    assert rows['wxbot.wechat.typing.chunk_size']['value']==5
    assert rows['wxbot.wechat.typing.chunk_interval']['value']==.25
    assert rows['wxbot.typing.input_method']['value']=='分批剪贴板粘贴'
    assert rows['wxbot.typing.unicode_keyboard']['value'] is False
    assert rows['wxbot.model.api_key']['value']=='已配置（隐藏）'
    assert data['runtime_verified'] is False


def test_config_missing_and_parse_errors_are_per_source_and_do_not_echo_credentials(tmp_path):
    wx,bt,home=configs(tmp_path)
    wx.write_text('[bad syntax token=secret-should-not-echo',encoding='utf-8')
    data=ConfigView(wx,bt,home).read()
    assert any(s['error'] for s in data['sources'])
    assert 'secret-should-not-echo' not in json.dumps(data)
    assert 'paimon' in json.dumps(data)
    bt.unlink()
    assert any(s['status']=='missing' for s in ConfigView(wx,bt,home).read()['sources'])


@pytest.mark.parametrize('field',['hermes.root','heartbeat.config_file','groups.file'])
def test_wrong_path_type_in_butler_does_not_hide_queue_or_other_configuration(tmp_path,field):
    wx,bt,home=configs(tmp_path)
    table,key=field.split('.')
    bt.write_text('['+table+']\n'+key+'=123\n',encoding='utf-8')
    view=ConfigView(wx,bt,home)
    data=view.read()
    assert any(s['status']=='error' for s in data['sources'])
    assert any(s['id']=='wxbot.queue' for s in data['sections'])
    assert view.queue_options()['quiet']==3


def test_configuration_redacts_header_lists_and_sensitive_ancestor_values(tmp_path):
    wx,bt,home=configs(tmp_path)
    with wx.open('a',encoding='utf-8') as fh:
        fh.write('\n[extra]\nheaders=["Authorization: Bearer header-list-secret"]\n[extra.credentials]\nuid=123456\n')
    data=ConfigView(wx,bt,home).read()
    rows={r['key']:r for s in data['sections'] for r in s['rows']}
    wire=json.dumps(data)
    assert 'header-list-secret' not in wire
    assert '123456' not in wire
    assert rows['wxbot.extra.headers']['sensitive']
    assert rows['wxbot.extra.credentials.uid']['value']=='已配置（隐藏）'


def test_configuration_hides_malformed_urls_instead_of_returning_credentials(tmp_path):
    wx,bt,home=configs(tmp_path)
    wx.write_text('[model]\nbackend="openai"\nurl="https://user:url-password@[::1/v1?access_token=query-only-secret"\n',encoding='utf-8')
    data=ConfigView(wx,bt,home).read()
    wire=json.dumps(data)
    assert 'url-password' not in wire
    assert 'query-only-secret' not in wire
    rows={r['key']:r for s in data['sections'] for r in s['rows']}
    assert rows['wxbot.model.url']['value']=='URL 格式无效（已隐藏）'


def test_log_dynamic_overrides_are_shown_alongside_butler_sources(tmp_path):
    wx,bt,home=configs(tmp_path)
    override=tmp_path/'override-groups.json'
    override.write_text(json.dumps({'groups':{'1':['override-user']}}),encoding='utf-8')
    other_home=tmp_path/'log-home'
    (other_home/'cache').mkdir(parents=True)
    (other_home/'cache'/'butler_heartbeat.json').write_text(json.dumps({'users':{'log-user':{'role_skill':'log-role'}}}),encoding='utf-8')
    data=ConfigView(wx,bt,other_home,groups_override=override).read()
    wire=json.dumps(data)
    assert 'override-user' in wire and 'log-role' in wire and 'paimon' in wire
    assert data['warnings']


def test_monitor_http_endpoints_and_html_routes(tmp_path,monkeypatch):
    wx,bt,home=configs(tmp_path)
    path=tmp_path/'q.db'
    QueueStore(path).close()
    with wx.open('a',encoding='utf-8') as fh:
        fh.write('\n[queue]\ndatabase='+json.dumps(str(path))+'\n')
    monkeypatch.setenv('WXBOT_CONFIG',str(wx))
    monkeypatch.setenv('BUTLER_CONFIG',str(bt))
    root=REPO_ROOT
    spec=importlib.util.spec_from_file_location('_dashboard_monitor',root/'src'/'dashboard'/'server.py')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    handler=type('TestHandler',(mod.Handler,),{'home':str(home)})
    server=ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    try:
        for route in ('/api/queue','/api/configuration','/api/flow','/api/workflow'):
            with urllib.request.urlopen(base+route,timeout=3) as response:
                data=json.load(response)
            assert data['read_only'] is (route!='/api/configuration')
            assert 'hermes-secret-000' not in json.dumps(data)
        with urllib.request.urlopen(base+'/api/wxbot',timeout=3) as response:
            payload=json.load(response)
        assert payload['flow']['read_only'] and payload['flow']['status']=='ok'
        opener=urllib.request.build_opener(NoRedirect)
        for target,expected in (('/', '/app/'), ('/?tab=queue', '/app/?tab=queue')):
            with pytest.raises(urllib.error.HTTPError) as error:
                opener.open(base+target,timeout=3)
            assert error.value.code==302 and error.value.headers['Location']==expected
        def bad_workflow(*args,**kwargs):
            raise ValueError('hermes-secret-000 private-config-path')
        monkeypatch.setattr(mod,'WorkflowView',bad_workflow)
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base+'/api/workflow',timeout=3)
        assert error.value.code==500
        wire=error.value.read().decode('utf-8')
        assert 'hermes-secret-000' not in wire and 'private-config-path' not in wire
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
