import json
from types import SimpleNamespace

import pytest

from butler.business import BusinessStore


def reminder(store, text='test reminder'):
    with store.transaction() as db:
        return store.create_reminder('owner','Alice',text,'in 5m',db=db)


def test_delete_stops_due_task_and_preserves_other_tasks_and_audit(tmp_path):
    from butler.job_admin import delete_job, job_version
    store=BusinessStore(tmp_path/'business.sqlite3')
    first=reminder(store);second=reminder(store,'keep')
    row=next(r for r in store.reminders() if r['id']==first['id'])
    result=delete_job(store,{'job_id':first['id'],'version':job_version(row),'acknowledge':True})
    assert result=={'ok':True,'job_id':first['id']}
    assert [r['id'] for r in store.reminders()]==[second['id']]
    assert [r['id'] for r in store.claim_due(first['due']+100)]==[second['id']]
    assert store.events()[0]['stage']=='job_deleted'


def test_delete_rejects_changed_and_delivering_tasks(tmp_path):
    from butler.job_admin import delete_job, job_version, JobConflict
    store=BusinessStore(tmp_path/'business.sqlite3');item=reminder(store)
    row=store.reminders()[0]
    payload={'job_id':item['id'],'version':job_version(row),'acknowledge':True}
    store.claim_due(item['due']+1)
    with pytest.raises(JobConflict):delete_job(store,payload)
    current=store.reminders()[0]
    with pytest.raises(JobConflict,match='投递'):delete_job(store,{**payload,'version':job_version(current)})
    assert store.reminders()[0]['status']=='delivering'


def test_delete_requires_valid_admin_payload_and_snapshot(tmp_path):
    from butler.job_admin import delete_job,job_version,JobConflict
    store=BusinessStore(tmp_path/'business.sqlite3');item=reminder(store)
    row=store.reminders()[0]
    valid={'job_id':item['id'],'version':job_version(row),'acknowledge':True}
    for payload in [[],{**valid,'acknowledge':False},{**valid,'owner':'another'},{**valid,'job_id':'../file'}, {**valid,'version':True}]:
        with pytest.raises(ValueError):delete_job(store,payload)
    with store.transaction() as db:db.execute("UPDATE reminders SET status='cancelled' WHERE id=?",(item['id'],))
    with pytest.raises(JobConflict):delete_job(store,valid)
    assert len(store.reminders())==1


@pytest.mark.parametrize('status',['scheduled','failed','cancelled','sent','delivering'])
def test_projection_marks_deletable_tasks_and_tracks_changes(status):
    from log.runtime_view import reminder_jobs
    row={'id':'a'*32,'owner':'owner','contact':'Alice','text':'hi','schedule':'in 5m','due':1234,
         'status':status,'detail':'','delivery_id':None,'created':1,'recurring':0}
    job=reminder_jobs({'backend':'codex','reminders':[row]})['users'][0]['jobs'][0]
    assert job['can_delete']==(status!='delivering')
    assert isinstance(job['delete_version'],str) and len(job['delete_version'])==64


def test_butler_delete_endpoint_requires_service_token_and_handles_races(tmp_path):
    from butler.server import make_handler
    from butler.job_admin import job_version
    from test_user_admin import running,request
    store=BusinessStore(tmp_path/'business.sqlite3');item=reminder(store)
    payload={'job_id':item['id'],'version':job_version(store.reminders()[0]),'acknowledge':True}
    with running(make_handler(SimpleNamespace(store=store),SimpleNamespace(token='server-test',provider='codex'))) as base:
        assert request(base,'/v1/jobs/delete',payload)[0]==401
        assert request(base,'/v1/jobs/delete',payload,{'Authorization':'Bearer tool-test'})[0]==401
        status,result=request(base,'/v1/jobs/delete',payload,{'Authorization':'Bearer server-test'})
        assert status==200 and result['ok']
        assert request(base,'/v1/jobs/delete',payload,{'Authorization':'Bearer server-test'})[0]==404


def test_log_delete_requires_confirmed_same_origin(monkeypatch):
    import log.server as server
    import log.job_admin as proxy
    from test_user_admin import running,request
    monkeypatch.setattr(server,'dashboard_mode',lambda:'local')
    monkeypatch.setattr(server,'_load_butler_config',lambda:{'server':{'token':'private-test-secret'}})
    calls=[]
    def fake(config,payload):calls.append(payload);return 409,{'error':'任务状态已变化'}
    monkeypatch.setattr(proxy,'request_job_delete',fake)
    with running(server.Handler) as base:
        payload={'job_id':'a'*32,'version':'b'*64,'acknowledge':True}
        valid={'Content-Type':'application/json','X-Wxbot-Job-Action':'1','Origin':base}
        assert request(base,'/api/jobs/delete',payload)[0]==403
        assert request(base,'/api/jobs/delete',payload,{**valid,'Origin':'https://bad.example'})[0]==403
        assert request(base,'/api/jobs/delete',payload,{**valid,'Host':'bad.example'})[0]==403
        assert calls==[]
        code,result=request(base,'/api/jobs/delete',payload,valid)
        assert code==409 and 'private-test-secret' not in json.dumps(result)
        assert calls==[payload]


def test_log_proxy_deletes_only_the_selected_task(tmp_path):
    from butler.server import make_handler
    from butler.job_admin import job_version
    from log.job_admin import request_job_delete
    from test_user_admin import running
    store=BusinessStore(tmp_path/'business.sqlite3');item=reminder(store);keep=reminder(store,'keep')
    row=next(r for r in store.reminders() if r['id']==item['id'])
    with running(make_handler(SimpleNamespace(store=store),SimpleNamespace(token='server-test',provider='codex'))) as base:
        code,result=request_job_delete({'server':{'port':int(base.rsplit(':',1)[1]),'token':'server-test'}},
            {'job_id':item['id'],'version':job_version(row),'acknowledge':True})
        assert code==200 and result['ok']
    assert [r['id'] for r in store.reminders()]==[keep['id']]
