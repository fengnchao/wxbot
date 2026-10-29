from contextlib import closing
import sqlite3

import pytest

from wxbot.queue_store import QueueStore,Incoming
from log.workflow_view import WorkflowView


def view(path):return WorkflowView({'path':path},[])


def batch(store,contact,status='done',complete=False):
    store.capture(contact,[],[Incoming('question')],now=1)
    store.prepare(quiet=0,max_wait=1,prefix='/',now=2)
    item=store.claim_batch(now=3)
    with store._transaction() as db:
        db.execute('UPDATE batches SET state=?,reply_complete=?,finished_at=4,error=? WHERE id=?',
                   (status,int(complete),'timeout' if not complete else '',item.id))
    return item.id


def test_delete_terminal_failure_survives_refresh_and_keeps_queue_evidence(tmp_path):
    from log.workflow_history import WorkflowHistory
    path=tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        rid=batch(store,'A')
        message=view(path).read(now=5)['messages'][0]
        assert message['can_delete'] and message['terminal']
        result=WorkflowHistory(path).delete({'action':'single','id':rid,'version':message['delete_version'],'acknowledge':True})
        assert result['removed']==1
        assert view(path).read(now=6)['messages']==[]
        assert view(path).read(now=6)['counts']['closed_issues']==0
        assert store.get_batch(rid)['state']=='done'
        assert store.records('inbox')[0]['text']=='question'
        assert WorkflowHistory(path).delete({'action':'single','id':rid,'version':message['delete_version'],'acknowledge':True})['removed']==0
        from log.workflow_content import read_content
        assert read_content(path,tmp_path/'missing-telegram.toml',rid) is None


def test_bulk_cleanup_protects_current_work_and_successful_history(tmp_path):
    from log.workflow_history import WorkflowHistory
    path=tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        failed=batch(store,'failed')
        success=batch(store,'success',complete=True)
        processing=batch(store,'processing',status='processing')
        uncertain=batch(store,'uncertain',status='uncertain')
        messages={m['id']:m for m in view(path).read(now=5)['messages']}
        assert messages[failed]['can_delete']
        assert not messages[processing]['can_delete'] and not messages[uncertain]['can_delete']
        assert view(path).read(now=5)['counts']['closed_issues']==1
        assert WorkflowHistory(path).delete({'action':'failed','acknowledge':True})['removed']==1
        assert {m['id'] for m in view(path).read(now=6)['messages']}=={success,processing,uncertain}
        assert store.get_batch(processing)['state']=='processing'


def test_delete_checks_snapshot_and_reappears_if_work_is_reopened(tmp_path):
    from log.workflow_history import WorkflowHistory,WorkflowConflict
    path=tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        rid=batch(store,'A')
        old=view(path).read(now=5)['messages'][0]
        payload={'action':'single','id':rid,'version':old['delete_version'],'acknowledge':True}
        with store._transaction() as db:db.execute('UPDATE batches SET state="processing" WHERE id=?',(rid,))
        with pytest.raises(WorkflowConflict):WorkflowHistory(path).delete(payload)
        assert view(path).read(now=6)['messages'][0]['id']==rid
        with store._transaction() as db:db.execute('UPDATE batches SET state="done" WHERE id=?',(rid,))
        current=view(path).read(now=7)['messages'][0]
        WorkflowHistory(path).delete({**payload,'version':current['delete_version']})
        with store._transaction() as db:db.execute('UPDATE batches SET state="ready" WHERE id=?',(rid,))
        assert view(path).read(now=8)['messages'][0]['id']==rid


def test_read_only_projection_does_not_initialize_history_table(tmp_path):
    path=tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        batch(store,'A')
        with sqlite3.connect(path) as db:before=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        view(path).read()
        with sqlite3.connect(path) as db:assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==before


@pytest.mark.parametrize('payload',[{}, {'action':'failed','acknowledge':False}, {'action':'all','acknowledge':True},
    {'action':'failed','acknowledge':True,'path':'other.db'}, {'action':'single','id':'../other','version':'x','acknowledge':True}])
def test_invalid_cleanup_never_touches_store(tmp_path,payload):
    from log.workflow_history import WorkflowHistory
    path=tmp_path/'missing.db'
    with pytest.raises(ValueError):WorkflowHistory(path).delete(payload)
    assert not path.exists()


def test_skipped_push_and_partial_reply_keep_delivery_receipts(tmp_path):
    from log.workflow_history import WorkflowHistory
    path=tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        rid=store.enqueue_delivery('push','discarded',now=1)
        with store._transaction() as db:db.execute("UPDATE outbox SET state='skipped',finished_at=3 WHERE id=?",(rid,))
        package=store.enqueue_package('package',[{'kind':'text','text':'part1'},{'kind':'text','text':'part2'}],
                                      'request-a',media_paths={},now=1)
        first=store.claim_delivery(now=4)
        store.finish_delivery(first.id,'sent',now=5)
        second=store.claim_delivery(now=6)
        store.finish_delivery(second.id,'skipped',now=7,error='discarded')
        before=store.package_receipt(package)
        count=view(path).read(now=8)['counts']['closed_issues']
        assert count>=1
        result=WorkflowHistory(path).delete({'action':'failed','acknowledge':True})
        assert result['removed']==count
        assert store.package_receipt(package)==before
        assert store.get_delivery(first.id)['state']=='sent'
        assert store.enqueue_package('package',[{'kind':'text','text':'part1'},{'kind':'text','text':'part2'}],
                                      'request-a',media_paths={},now=9)==package


def test_hidden_history_does_not_consume_the_recent_history_limit(tmp_path):
    from log.workflow_history import WorkflowHistory
    path=tmp_path/'q.db'
    with closing(QueueStore(path)) as store:
        for index in range(64):batch(store,str(index))
        before=view(path).read(now=5)
        assert len(before['messages'])==60 and before['history_more']
        for item in before['messages']:
            WorkflowHistory(path).delete({'action':'single','id':item['id'],'version':item['delete_version'],'acknowledge':True})
        after=view(path).read(now=6)
        assert len(after['messages'])==4 and after['counts']['closed_issues']==4
        assert not after['history_more']


def test_workflow_delete_http_checks_confirmation_and_origin(tmp_path):
    from email.message import Message
    from io import BytesIO
    from types import SimpleNamespace
    import json
    from log.server import Handler
    path=tmp_path/'q.db'
    base='http://127.0.0.1:8788'
    headers={'Host':'127.0.0.1:8788','Origin':base,'Content-Type':'application/json','X-Wxbot-Workflow-Action':'1'}
    def post(h,payload):
        handler=Handler.__new__(Handler);handler.path='/api/workflow-delete';handler.headers=Message()
        raw=json.dumps(payload).encode()
        for name,value in {**h,'Content-Length':str(len(raw))}.items():handler.headers[name]=value
        handler.rfile=BytesIO(raw);handler.connection=SimpleNamespace(getsockname=lambda:('127.0.0.1',8788))
        handler.server=SimpleNamespace(server_port=8788)
        handler._config_view=lambda:SimpleNamespace(read=lambda:None,queue_options=lambda:{'path':path})
        results=[];handler._json=lambda data,code=200:results.append((code,data))
        handler.do_POST();return results[0]
    with closing(QueueStore(path)) as store:
        batch(store,'A')
        assert post({}, {'action':'failed','acknowledge':True})[0]==403
        assert post({**headers,'Origin':'https://bad.example'},{'action':'failed','acknowledge':True})[0]==403
        assert post(headers,{'action':'failed','acknowledge':False})[0]==400
        assert len(view(path).read()['messages'])==1
        status,result=post(headers,{'action':'failed','acknowledge':True})
        assert status==200 and result['removed']==1
