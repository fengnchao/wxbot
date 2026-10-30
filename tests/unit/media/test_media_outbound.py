from io import BytesIO
from types import SimpleNamespace
import pytest
from PIL import Image
from wxbot.queue_store import QueueStore
from wxbot.outbound import OutboundQueue

MEDIA = 'a'*32

def test_package_is_atomic_idempotent_ordered_and_rejects_changed_retry(tmp_path):
    store = QueueStore(':memory:')
    items = [{'kind':'text','text':'header'}, {'kind':'image','media_id':MEDIA}]
    paths = {MEDIA:str(tmp_path/'safe.png')}
    package = store.enqueue_package('A', items, 'source-1', media_paths=paths, now=0)
    assert store.enqueue_package('A',items,'source-1',media_paths=paths,now=1) == package
    assert len(store.records('outbox')) == 2
    store.enqueue_delivery('A','later',now=1)
    first=store.claim_delivery(now=1)
    assert first.text == 'header' and first.package_id == package
    store.finish_delivery(first.id,'sent',now=2)
    second=store.claim_delivery(now=2)
    assert second.kind == 'image' and second.media_id == MEDIA
    assert not store.package_receipt(package)['done']
    store.finish_delivery(second.id,'sent',now=3)
    assert store.package_receipt(package) == {'done':True,'ok':True,'state':'sent'}
    assert store.claim_delivery(now=3).text == 'later'
    with pytest.raises(ValueError):
        store.enqueue_package('A',[{'kind':'text','text':'changed'}],'source-1',media_paths={},now=3)


def test_invalid_package_never_inserts_partial_rows():
    store=QueueStore(':memory:')
    with pytest.raises(ValueError):
        store.enqueue_package('A',[{'kind':'text','text':'hi'},{'kind':'image','media_id':'../../secret','path':'x'}],'x',media_paths={},now=0)
    assert store.records('outbox') == []


def test_unknown_package_stops_remaining_items_and_is_never_retried():
    store=QueueStore(':memory:')
    package=store.enqueue_package('A',[{'kind':'text','text':'one'},{'kind':'text','text':'two'}],'x',media_paths={},now=0)
    row=store.claim_delivery(now=0)
    store.finish_delivery(row.id,'uncertain',now=1,error='unknown')
    assert store.claim_delivery(now=100) is None
    assert store.retry_failed_deliveries(now=30) == []
    assert store.package_receipt(package)['state']=='uncertain'
    assert store.package_receipt(package)['done']


def test_restart_unknown_package_does_not_resume_tail():
    store=QueueStore(':memory:')
    package=store.enqueue_package('A',[{'kind':'text','text':'one'},{'kind':'text','text':'two'}],'x',media_paths={},now=0)
    store.claim_delivery(now=0)
    store.recover(now=1)
    assert store.claim_delivery(now=2) is None
    assert store.package_receipt(package)['state']=='uncertain'


def test_media_cache_accepts_only_valid_images_and_no_caller_paths(tmp_path):
    from wxbot.outbound import BundleMediaCache
    data=BytesIO(); Image.new('RGB',(4,4),'red').save(data,format='PNG')
    seen=[]
    cache=BundleMediaCache(tmp_path,lambda mid: seen.append(mid) or data.getvalue())
    paths=cache.resolve([{'kind':'image','media_id':MEDIA}])
    assert paths[MEDIA].is_file() and seen==[MEDIA]
    with pytest.raises(ValueError): cache.resolve([{'kind':'image','media_id':'../secret'}])
    with pytest.raises(ValueError): cache.resolve([{'kind':'image','media_id':MEDIA,'path':'evil'}])
    bad=BundleMediaCache(tmp_path/'bad',lambda mid:b'not an image')
    with pytest.raises(ValueError): bad.resolve([{'kind':'image','media_id':MEDIA}])


def test_bundle_request_survives_queue_as_one_ordered_unit():
    queue=OutboundQueue()
    req=queue.submit_bundle('A',[{'kind':'text','text':'one'}],'source-1',media_paths={})
    assert queue.drain()==[req]
    assert req.request_id=='source-1' and req.items[0]['text']=='one'

def invoke_bundle(queue,payload,*,token='secret',provided='secret',cache=None):
    import json
    from wxbot.outbound import make_handler
    handler=object.__new__(make_handler(queue,token,media_cache=cache))
    data=json.dumps(payload).encode()
    handler.path='/send-bundle'
    handler.headers={'Content-Length':str(len(data)),'X-Wxbot-Token':provided}
    handler.rfile=BytesIO(data)
    results=[];handler._send=lambda code,obj:results.append((code,obj))
    handler.do_POST()
    return results[-1]


def test_bundle_http_requires_configured_auth_and_waits_for_whole_receipt():
    payload={'contact':'A','items':[{'kind':'text','text':'hello'}],'request_id':'source-1','wait':False}
    queue=OutboundQueue()
    assert invoke_bundle(queue,payload,token='',provided='')[0]==401
    assert invoke_bundle(queue,payload,provided='wrong')[0]==401
    assert invoke_bundle(queue,payload)[0]==400
    assert queue.drain()==[]


def test_bundle_http_resolves_every_image_before_any_enqueue(tmp_path):
    from wxbot.outbound import BundleMediaCache
    data=BytesIO(); Image.new('RGB',(2,2)).save(data,format='PNG')
    calls=[]
    def fetch(mid):
        calls.append(mid)
        return data.getvalue() if mid==MEDIA else b'corrupt'
    cache=BundleMediaCache(tmp_path,fetch)
    queue=OutboundQueue()
    payload={'contact':'A','items':[{'kind':'image','media_id':MEDIA},{'kind':'image','media_id':'b'*32}], 'request_id':'source-1'}
    assert invoke_bundle(queue,payload,cache=cache)[0]==400
    assert queue.drain()==[] and calls==[MEDIA,'b'*32]


def test_bundle_http_receipt_binds_recipient_and_request():
    class CompletedQueue(OutboundQueue):
        def submit_bundle(self,*args,**kwargs):
            request=super().submit_bundle(*args,**kwargs)
            request.finish(True,'sent')
            return request
    payload={'contact':'A','items':[{'kind':'text','text':'hello'}],'request_id':'source-1'}
    code,result=invoke_bundle(CompletedQueue(),payload)
    assert code==200 and result=={'ok':True,'detail':'sent','contact':'A','request_id':'source-1'}


def test_package_transaction_rolls_back_if_any_item_insert_fails(tmp_path):
    import sqlite3
    store=QueueStore(':memory:')
    store._db.execute("CREATE TRIGGER fail_image BEFORE INSERT ON outbox WHEN NEW.kind='image' BEGIN SELECT RAISE(ABORT,'rejected'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.enqueue_package('A',[{'kind':'text','text':'first'},{'kind':'image','media_id':MEDIA}], 'source-1',media_paths={MEDIA:tmp_path/'safe'},now=0)
    assert store.records('outbox')==[]
    assert store._db.execute('SELECT COUNT(*) FROM delivery_packages').fetchone()[0]==0


def test_schema_upgrade_backs_up_previous_queue_and_preserves_text(tmp_path):
    import sqlite3
    from wxbot import queue_schema
    path=tmp_path/'q.db'
    store=QueueStore(path)
    record=store.enqueue_delivery('A','existing',now=0)
    store._db.execute('PRAGMA user_version=9');store._db.commit();store.close()
    store=QueueStore(path)
    assert store.get_delivery(record)['text']=='existing'
    assert store._db.execute('PRAGMA user_version').fetchone()[0]==queue_schema.VERSION
    backups=list(tmp_path.glob('q.db.backup-*'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as old:
        assert old.execute('PRAGMA user_version').fetchone()[0]==9
        assert old.execute('SELECT text FROM outbox').fetchone()[0]=='existing'
    store.close()

def test_manual_package_confirm_recomputes_whole_receipt(tmp_path):
    store=QueueStore(':memory:')
    package=store.enqueue_package('A',[{'kind':'image','media_id':MEDIA}],'manual',media_paths={MEDIA:tmp_path/'safe'},now=0)
    row=store.claim_delivery(now=0)
    store.finish_delivery(row.id,'uncertain',now=1)
    store.resolve(row.id,delivery=True,sent=True,now=2)
    assert store.package_receipt(package)=={'done':True,'ok':True,'state':'sent'}


def test_manual_package_retry_reopens_receipt_without_restoring_stopped_tail():
    store=QueueStore(':memory:')
    package=store.enqueue_package('A',[{'kind':'text','text':'one'},{'kind':'text','text':'two'}],'manual',media_paths={},now=0)
    row=store.claim_delivery(now=0)
    store.finish_delivery(row.id,'blocked',now=1)
    store.retry(row.id,delivery=True,now=2)
    assert store.package_receipt(package)=={'done':False,'ok':False,'state':'pending'}
    assert store.records('outbox')[1]['state']=='skipped'
    retried=store.claim_delivery(now=3)
    store.finish_delivery(retried.id,'sent',now=4)
    assert store.package_receipt(package)=={'done':True,'ok':False,'state':'skipped'}
    assert store.claim_delivery(now=5) is None

def test_independent_mode_rejects_bundle_before_body_media_resolution_or_submit():
    from wxbot.outbound import make_handler
    class ForbiddenQueue:
        def submit_bundle(self,*a,**kw):pytest.fail('disabled bundle must never submit')
    class ForbiddenCache:
        def resolve(self,*a,**kw):pytest.fail('disabled bundle must never resolve media')
    handler=object.__new__(make_handler(ForbiddenQueue(),'secret',media_cache=ForbiddenCache(),allow_bundles=False))
    handler.path='/send-bundle';handler.headers={'X-Wxbot-Token':'secret'}
    handler._body=lambda:pytest.fail('disabled bundle must not read body')
    results=[];handler._send=lambda code,obj:results.append((code,obj))
    handler.do_POST()
    assert results[0][0]==400 and results[0][1]['ok'] is False
    assert 'not submitted' in results[0][1]['detail']


def test_butler_media_fetch_ignores_environment_proxy_and_redirects(monkeypatch):
    from wxbot.outbound import ButlerMediaClient
    class Response:
        status_code=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,size):yield b'fake-image'
    class Session:
        trust_env=True
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):
            assert self.trust_env is False
            assert url=='http://127.0.0.1:8766/v1/media/'+MEDIA
            assert kwargs['allow_redirects'] is False and kwargs['stream'] is True
            assert kwargs['headers']=={'Authorization':'Bearer secret'}
            return Response()
    monkeypatch.setattr('requests.Session',Session)
    assert ButlerMediaClient('http://127.0.0.1:8766','secret').fetch(MEDIA)==b'fake-image'
