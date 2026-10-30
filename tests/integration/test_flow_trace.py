import io
import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

import pytest

from butler.identity.contacts import load_contacts
from butler.agent.hermes import HermesClient, HermesError


def read_events(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def test_trace_scopes_keep_concurrent_contacts_separate_and_drop_sensitive_payloads(tmp_path):
    from common.flow_trace import FlowTrace, record
    path=tmp_path/'flow.jsonl'
    trace=FlowTrace(path)
    barrier=threading.Barrier(2)
    def run(name):
        with trace.bind(name,'request-'+name):
            barrier.wait(2)
            record('hermes_tool','running',tool='skill_view',tool_call_id='tool-'+name,
                   arguments={'key':'argument-secret'},label='label-secret',text='private-thought')
    threads=[threading.Thread(target=run,args=(name,)) for name in ('A','B')]
    for t in threads: t.start()
    for t in threads: t.join(3)
    events=read_events(path)
    assert {(e['contact'],e['request_id']) for e in events}=={('A','request-A'),('B','request-B')}
    wire=path.read_text(encoding='utf-8')
    assert all(secret not in wire for secret in ('argument-secret','label-secret','private-thought'))
    record('outside','ok')
    assert len(read_events(path))==2
    with FlowTrace(tmp_path).bind('A','bad-sink'):
        record('butler_received','ok')  # A broken trace sink must never break a message.


class StreamResponse(io.BytesIO):
    status=200
    headers={'Content-Type':'text/event-stream; charset=utf-8','X-Hermes-Session-Id':'echoed-sid'}


def frame(data,event=''):
    return ((('event: '+event+'\n') if event else '')+'data: '+
            (data if isinstance(data,str) else json.dumps(data,ensure_ascii=False))+'\n\n').encode('utf-8')


def chunk(text=None,finish=None,**extra):
    return {'id':'chatcmpl-test','choices':[{'index':0,'delta':{'content':text} if text is not None else {},
                        'finish_reason':finish}],**extra}


def final_frame(text,completion_id='chatcmpl-test'):
    return frame({'id':completion_id,'object':'hermes.final_response','completed':True,
                  'partial':False,'failed':False,'content':text},'hermes.final_response')


def test_hermes_records_tool_progress_but_returns_only_complete_text(make_home,tmp_path,monkeypatch):
    from common.flow_trace import FlowTrace
    from butler.agent import hermes as module
    data=(frame({'tool':'skill_view','status':'running','toolCallId':'tc-1','label':'secret-label'},'hermes.tool.progress')+
          frame({'choices':[{'index':0,'delta':{'reasoning_content':'private-reasoning'},'finish_reason':None}]})+
          frame(chunk('你好'))+
          frame({'tool':'skill_view','status':'completed','toolCallId':'tc-1'},'hermes.tool.progress')+
          frame(chunk('。'))+final_frame('你好。')+frame(chunk(finish='stop'))+frame('[DONE]'))
    captured=[]
    def open_request(req,timeout=None):
        captured.append(json.loads(req.data))
        return StreamResponse(data)
    monkeypatch.setattr(module.urllib.request,'urlopen',open_request)
    cfg=make_home(pending_items=[]).cfg
    client=HermesClient(cfg)
    contact=load_contacts([{'name':'101','uid':'101','profile':'wxbot-101'}]).get('101')
    path=tmp_path/'events.jsonl'
    with FlowTrace(path).bind('101','batch-1'):
        result=client.chat(contact,'你好',skill_policy={'role_skill':'paimon','allowed_skills':['paimon']})
    assert result=='你好。'
    assert captured[0]['stream'] is True and len(captured)==1
    assert captured[0]['skill_policy']['role_skill']=='paimon'
    events=read_events(path)
    assert [(e['tool'],e['status']) for e in events if e['stage']=='hermes_tool']==[
        ('skill_view','running'),('skill_view','completed')]
    assert any(e['stage']=='hermes_request' and e['status']=='accepted' for e in events)
    assert events[-1]['stage']=='hermes_result' and events[-1]['status']=='ok'
    assert client.session_id(contact,skill_policy={'role_skill':'paimon','allowed_skills':['paimon']})=='echoed-sid'
    wire=path.read_text(encoding='utf-8')
    assert 'private-reasoning' not in wire and 'secret-label' not in wire and '你好' not in wire


@pytest.mark.parametrize('ending',[b'',frame('[DONE]'),frame(chunk(finish='length'))+frame('[DONE]'),
                                   frame(chunk(finish='error'))+frame('[DONE]'),
                                   frame(chunk(finish='stop'))+frame('[DONE]')])
def test_incomplete_or_failed_hermes_stream_never_becomes_a_partial_reply(make_home,tmp_path,monkeypatch,ending):
    from common.flow_trace import FlowTrace
    from butler.agent import hermes as module
    calls=[]
    def open_request(req,timeout=None):
        calls.append(req)
        return StreamResponse(frame(chunk('half-reply'))+ending)
    monkeypatch.setattr(module.urllib.request,'urlopen',open_request)
    cfg=make_home(pending_items=[]).cfg
    client=HermesClient(cfg)
    contact=cfg.contacts.get('101')
    path=tmp_path/'failure.jsonl'
    with FlowTrace(path).bind('101','batch-failed'),pytest.raises(HermesError):
        client.chat(contact,'hi')
    assert len(calls)==1
    events=read_events(path)
    assert events[-1]['stage']=='hermes_result' and events[-1]['status']=='error'
    assert 'half-reply' not in path.read_text(encoding='utf-8')


def test_butler_arrival_is_logged_before_waiting_for_its_session_lock(make_home):
    from common.flow_trace import butler_trace_path
    home=make_home(replies=['ok'],pending_items=[])
    contact=home.cfg.contacts.get('101')
    path=butler_trace_path(home.cfg.flow_log_path())
    with home.butler.runtime_locks.session(contact):
        thread=threading.Thread(target=home.butler.handle,args=('101','hi'),kwargs={'msg_id':'batch-lock'})
        thread.start()
        import time
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            if path.is_file() and 'butler_received' in path.read_text(encoding='utf-8'):
                break
            threading.Event().wait(.01)
        events=read_events(path)
        assert events[0]['stage']=='butler_received'
        assert not any(e['stage']=='butler_result' for e in events)
    thread.join(3)
    assert not thread.is_alive()
    assert read_events(path)[-1]['stage']=='butler_result'


def test_model_worker_links_butler_receipt_and_complete_reply_with_batch_id(make_home,start_server,tmp_path):
    from common.flow_trace import FlowTrace,butler_trace_path
    from wxbot.processor.butler import ButlerProcessor
    from wxbot.processor.router import Router
    from wxbot.queue_store import QueueStore,Incoming
    from wxbot.queue_worker import ModelWorker
    home=make_home(replies=['full answer'],pending_items=[])
    base=start_server(home.butler,home.cfg)
    store=QueueStore(tmp_path/'queue.db')
    path=tmp_path/'wx-events.jsonl'
    store.capture('101',[],[Incoming('hello')],now=0)
    worker=ModelWorker(store,Router(ButlerProcessor({'url':base,'token':'t0ken'},raise_errors=True)),
                       trace=FlowTrace(path),quiet=0,clock=lambda:1)
    try:
        assert worker.process_once()
        batch=store.records('batches')[0]
        wx=read_events(path)
        bt=read_events(butler_trace_path(home.cfg.flow_log_path()))
        assert {e['request_id'] for e in wx+bt}=={batch['id']}
        assert any(e['stage']=='wxbot_butler' and e['status']=='ok' for e in wx)
        assert any(e['stage']=='butler_received' for e in bt)
        assert store.records('outbox')[0]['text']=='full answer'
    finally:
        store.close()


def test_butler_http_rejection_does_not_claim_success_or_retry(tmp_path,monkeypatch):
    from common.flow_trace import FlowTrace
    from wxbot.processor.butler import ButlerProcessor
    import requests
    calls=[]
    def post(*args,**kwargs):
        calls.append(args)
        raise requests.HTTPError('fake-secret')
    monkeypatch.setattr(requests,'post',post)
    path=tmp_path/'http.jsonl'
    with FlowTrace(path).bind('101','request-http'),pytest.raises(requests.HTTPError):
        ButlerProcessor({},raise_errors=True).handle_reply('101','hi',request_id='request-http')
    events=read_events(path)
    assert len(calls)==1
    assert events[-1]['stage']=='wxbot_butler' and events[-1]['status']=='error'
    assert not any(e['status']=='ok' for e in events)
    assert 'fake-secret' not in path.read_text(encoding='utf-8')


def test_live_tool_event_is_visible_before_full_reply_is_released(make_home,tmp_path):
    from common.flow_trace import FlowTrace
    ready,release=threading.Event(),threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.end_headers()
            self.wfile.write(frame({'tool':'skill_view','toolCallId':'live-1','status':'running'},'hermes.tool.progress'))
            self.wfile.flush()
            ready.set()
            release.wait(4)
            self.wfile.write(frame(chunk('full reply'))+final_frame('full reply')+frame(chunk(finish='stop'))+frame('[DONE]'))
            self.wfile.flush()
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    serving=threading.Thread(target=server.serve_forever,daemon=True)
    serving.start()
    cfg=make_home(pending_items=[]).cfg
    cfg.hermes_url='http://127.0.0.1:'+str(server.server_port)
    path=tmp_path/'live.jsonl'
    reply=[]
    def run():
        with FlowTrace(path).bind('101','live-request'):
            reply.append(HermesClient(cfg).chat(cfg.contacts.get('101'),'hi'))
    thread=threading.Thread(target=run)
    thread.start()
    try:
        assert ready.wait(2)
        import time
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            if path.is_file() and 'hermes_tool' in path.read_text(encoding='utf-8'):
                break
            threading.Event().wait(.01)
        assert any(e['stage']=='hermes_tool' for e in read_events(path))
        assert reply==[] and thread.is_alive()
        release.set()
        thread.join(2)
        assert reply==['full reply']
    finally:
        release.set()
        thread.join(3)
        server.shutdown()
        server.server_close()
        serving.join(2)


def test_json_fallback_rejects_explicitly_incomplete_hermes_result(make_home,tmp_path,monkeypatch):
    from common.flow_trace import FlowTrace
    from butler.agent import hermes as module
    class JsonResponse(StreamResponse):
        headers={'Content-Type':'application/json'}
    body={'choices':[{'message':{'content':'partial answer'},'finish_reason':'length'}],
          'hermes':{'completed':False,'partial':True}}
    monkeypatch.setattr(module.urllib.request,'urlopen',lambda *a,**k:JsonResponse(json.dumps(body).encode()))
    cfg=make_home(pending_items=[]).cfg
    with FlowTrace(tmp_path/'fallback.jsonl').bind('101','fallback'),pytest.raises(HermesError):
        HermesClient(cfg).chat(cfg.contacts.get('101'),'hi')


@pytest.mark.parametrize('canonical_id',['chatcmpl-test','wrong-request'])
def test_canonical_reply_replaces_interim_text_and_removed_actions(make_home,tmp_path,monkeypatch,canonical_id):
    from common.flow_trace import FlowTrace
    from butler.agent import hermes as module
    from butler.agent.router import parse_actions
    raw='interim '+ '<<butler:action {"skill":"reminder.list","args":{}}>>'
    payload=(frame(chunk(raw))+frame(chunk('rewritten text'))+final_frame('safe final answer',canonical_id)+
             frame(chunk(finish='stop'))+frame('[DONE]'))
    monkeypatch.setattr(module.urllib.request,'urlopen',lambda *a,**k:StreamResponse(payload))
    cfg=make_home(pending_items=[]).cfg
    with FlowTrace(tmp_path/'canonical.jsonl').bind('101','canonical'):
        if canonical_id!='chatcmpl-test':
            with pytest.raises(HermesError):
                HermesClient(cfg).chat(cfg.contacts.get('101'),'hi')
        else:
            reply=HermesClient(cfg).chat(cfg.contacts.get('101'),'hi')
            assert reply=='safe final answer'
            assert parse_actions(reply)[1]==[]
