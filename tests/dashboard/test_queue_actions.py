import pytest

from dashboard.queue_actions import QueueActions
from wxbot.queue_store import QueueStore
from support.paths import REPO_ROOT


def setup_task(tmp_path):
    path=tmp_path/'q.db';store=QueueStore(path)
    task=store.enqueue_delivery('A','reply',now=0)
    store.claim_delivery(now=0)
    store.finish_delivery(task,'blocked',now=10,error='focus changed')
    payload={'id':task,'kind':'outbox','contact':'A','action':'retry','acknowledge':True,
             'expected_state':'blocked','expected_finished_at':10}
    return path,store,payload


def setup_expired_draft_hold(tmp_path):
    from dashboard.queue_view import QueueView
    from wxbot.queue_store import Incoming
    path=tmp_path/'q.db';store=QueueStore(path)
    store.capture('A',[],[Incoming('hi')],now=0)
    store.prepare(quiet=0,max_wait=10,prefix='/',now=0)
    batch=store.claim_batch(now=0)
    store.finish_batch_parts(batch.id,('reply','remaining'),now=0)
    task=store.claim_delivery(now=0)
    store.finish_delivery(task.id,'blocked',now=1,error='foreign draft',details={'manual_required':True})
    store.expire_failed_deliveries(now=181)
    reason=QueueView(path).read(scope='issues',now=182)['contacts'][0]['reason']
    assert reason['state']=='skipped' and 'skip' in reason['actions']
    payload={'id':reason['record_id'],'kind':reason['record_kind'],'contact':'A',
             'action':'retry','acknowledge':True,'expected_state':reason['state'],
             'expected_finished_at':reason['finished_at']}
    return path,store,payload


@pytest.mark.parametrize('action,state',[('retry','pending'),('sent','sent'),('skip','skipped')])
def test_expired_draft_hold_accepts_dashboard_actions_and_releases_contact(tmp_path,action,state):
    path,store,payload=setup_expired_draft_hold(tmp_path)
    try:
        later=store.enqueue_delivery('A','next',now=182)
        assert store.claim_delivery(now=182) is None
        result=QueueActions(path).perform({**payload,'action':action},now=183)
        row=store.get_delivery(payload['id'])
        assert result['ok'] and row['state']==state and not row['manual_required']
        assert store.claim_delivery(now=183).id==(payload['id'] if action=='retry' else later)
        assert store.records('outbox')[1]['state']=='skipped'
        event=store.delivery_events()[-1]
        assert event['source']=='log' and 'foreign draft' in event['reason']
    finally:store.close()


def test_skipped_delivery_without_draft_hold_cannot_be_replayed(tmp_path):
    path,store,payload=setup_expired_draft_hold(tmp_path)
    try:
        store.resolve(payload['id'],delivery=True,now=183)
        payload['expected_finished_at']=183
        for action in ('retry','sent','skip'):
            with pytest.raises(ValueError):QueueActions(path).perform({**payload,'action':action},now=184)
        assert store.get_delivery(payload['id'])['state']=='skipped'
    finally:store.close()


@pytest.mark.parametrize('field,value,error',[
    ('contact','B','联系人不匹配'),
    ('expected_state','blocked','状态已变化'),
    ('expected_finished_at',1,'任务已更新'),
])
def test_expired_draft_hold_rejects_mismatched_snapshot(tmp_path,field,value,error):
    path,store,payload=setup_expired_draft_hold(tmp_path)
    try:
        with pytest.raises(ValueError,match=error):QueueActions(path).perform({**payload,field:value},now=183)
        assert store.get_delivery(payload['id'])['manual_required']==1
    finally:store.close()


@pytest.mark.parametrize('action,state',[('retry','pending'),('sent','sent'),('skip','skipped')])
def test_manual_queue_buttons_apply_exact_task_and_record_an_audit(tmp_path,action,state):
    path,store,payload=setup_task(tmp_path)
    payload['action']=action
    result=QueueActions(path).perform(payload,now=20)
    assert result['ok'] and store.get_delivery(payload['id'])['state']==state
    assert store.delivery_events()[-1]['source']=='log'
    assert 'focus changed' in store.delivery_events()[-1]['reason']


@pytest.mark.parametrize('setup',[setup_task,setup_expired_draft_hold],ids=['blocked','expired_draft_hold'])
def test_queue_action_requires_acknowledgement_and_a_snapshot(tmp_path,setup):
    path,store,payload=setup(tmp_path)
    try:
        for key in ('acknowledge','expected_finished_at','expected_state','contact'):
            invalid=dict(payload);invalid.pop(key)
            with pytest.raises(ValueError):QueueActions(path).perform(invalid)
        assert store.get_delivery(payload['id'])['state']==payload['expected_state']
    finally:store.close()


def test_old_page_cannot_replay_action_or_override_an_active_task(tmp_path):
    path,store,payload=setup_task(tmp_path)
    actions=QueueActions(path)
    actions.perform(payload,now=20)
    store.claim_delivery(now=20)
    with pytest.raises(ValueError):actions.perform({**payload,'action':'skip'},now=21)
    assert store.get_delivery(payload['id'])['state']=='sending'


def test_missing_queue_action_never_creates_a_database(tmp_path):
    path=tmp_path/'missing.db'
    with pytest.raises(ValueError):QueueActions(path).perform({})
    assert not path.exists()


def test_old_model_failure_snapshot_cannot_resolve_a_later_attempt(tmp_path):
    from wxbot.queue_store import Incoming
    path=tmp_path/'batch.db';store=QueueStore(path)
    store.capture('A',[],[Incoming('hi')],now=0)
    store.prepare(quiet=0,max_wait=10,prefix='/',now=0)
    batch=store.claim_batch(now=0)
    store.fail_batch(batch.id,'first failure')
    first=store.get_batch(batch.id)
    payload={'id':batch.id,'kind':'batches','contact':'A','action':'retry','acknowledge':True,
             'expected_state':'uncertain','expected_finished_at':first['finished_at'],
             'expected_attempts':first['attempts']}
    actions=QueueActions(path)
    try:
        actions.perform(payload,now=10)
        store.claim_batch(now=10)
        store.fail_batch(batch.id,'second failure')
        # Same timestamp still cannot make the old snapshot valid again.
        store._db.execute('UPDATE batches SET finished_at=? WHERE id=?',(first['finished_at'],batch.id))
        store._db.commit()
        with pytest.raises(ValueError,match='更新|变化'):actions.perform({**payload,'action':'skip'},now=11)
        assert store.get_batch(batch.id)['state']=='uncertain'
    finally:store.close()


@pytest.mark.parametrize('setup',[setup_task,setup_expired_draft_hold],ids=['blocked','expired_draft_hold'])
def test_http_actions_require_same_origin_json_confirmation_and_reject_stale_state(tmp_path,monkeypatch,setup):
    import importlib.util,json,threading,urllib.request,urllib.error
    from http.server import ThreadingHTTPServer
    from pathlib import Path
    from test_log_monitor import configs
    wx,bt,home=configs(tmp_path)
    path,store,payload=setup(tmp_path)
    with wx.open('a',encoding='utf-8') as fh:fh.write('\n[queue]\ndatabase='+json.dumps(str(path))+'\n')
    monkeypatch.setenv('WXBOT_CONFIG',str(wx));monkeypatch.setenv('BUTLER_CONFIG',str(bt))
    spec=importlib.util.spec_from_file_location('_queue_action_http',REPO_ROOT/'src'/'dashboard'/'server.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    server=ThreadingHTTPServer(('127.0.0.1',0),type('TestHandler',(module.Handler,),{'home':str(home)}))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    def post(headers,body=payload):
        request=urllib.request.Request(base+'/api/queue-action',data=json.dumps(body).encode(),headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=3) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as exc:return exc.code,json.load(exc)
    valid={'Content-Type':'application/json','X-Wxbot-Queue-Action':'1','Origin':base}
    try:
        assert post({'Content-Type':'application/json'})[0]==403
        assert post({**valid,'Origin':'https://other.example'})[0]==403
        assert post({**valid,'Host':'attacker.example:'+str(server.server_port),
                     'Origin':'http://attacker.example:'+str(server.server_port)})[0]==403
        assert post(valid,{**payload,'acknowledge':False})[0]==409
        assert post(valid)[0]==200
        assert store.get_delivery(payload['id'])['state']=='pending'
        assert post(valid)[0]==409
        with urllib.request.urlopen(base+'/api/queue') as response:data=json.load(response)
        assert data['read_only'] and data['actions_enabled']
        assert data['events'][0]['action']=='retry'
    finally:
        server.shutdown();server.server_close();thread.join(3);store.close()
