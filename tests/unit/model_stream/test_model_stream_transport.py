import io
import json
from types import SimpleNamespace

import pytest


def test_context_bounded_public_fields_and_nesting():
    from common.model_stream import bind, emit
    outer, inner = [], []
    with bind(outer.append):
        emit('backend', provider='codex', model='test', streaming=True, token='SECRET')
        with bind(inner.append):
            emit('answer_delta', text='hello', sendable=True)
        emit('summary_delta', text='x' * 20000, sendable=True, reasoning='PRIVATE')
    assert outer[0] == {'type':'backend','provider':'codex','model':'test','streaming':True}
    assert inner == [{'type':'answer_delta','text':'hello','sendable':True}]
    assert len(outer[1]['text']) <= 8192
    assert 'sendable' not in outer[1] and 'reasoning' not in outer[1]


def test_router_callback_optional_legacy_and_fallback():
    from wxbot.processor.router import Router
    from wxbot.processor.base import EchoProcessor
    events=[]
    reply=Router(EchoProcessor()).handle_reply('alice','hello',on_event=events.append)
    assert reply.text == '收到：hello'
    assert events[0]['type']=='backend' and events[0]['streaming'] is False
    assert [e['text'] for e in events if e['type']=='answer_delta']==[reply.text]
    class Legacy:
        def handle_reply(self,*a,request_id=None,member_key='',member_name=''):
            return reply
    assert Router(Legacy()).handle_reply('a','b')==reply


def test_hermes_progress_never_exposes_raw_draft():
    from common.model_stream import bind
    from butler.agent.hermes_stream import read_complete
    events=[]
    def frame(kind,data):
        return ('event: '+kind+'\ndata: '+json.dumps(data)+'\n\n').encode()
    stream=io.BytesIO(frame('message',{'id':'a','choices':[{'delta':{'content':'PRIVATE ACTION DRAFT'}}]})+
        frame('hermes.tool.progress',{'status':'running','tool':'lookup','arguments':'SECRET'})+
        frame('hermes.final_response',{'id':'a','completed':True,'content':'final'})+
        frame('message',{'choices':[{'finish_reason':'stop'}]})+b'data: [DONE]\n\n')
    with bind(events.append):
        assert read_complete(stream,5)=='final'
    assert any(e['type']=='tool' for e in events)
    assert 'PRIVATE' not in json.dumps(events) and 'SECRET' not in json.dumps(events)


def test_butler_sse_client_requires_result_and_no_retry(monkeypatch):
    from wxbot.processor.butler import ButlerProcessor
    import wxbot.processor.butler as module
    calls=[]
    class Response:
        headers={'Content-Type':'text/event-stream'}
        status_code=200
        def raise_for_status(self): pass
        def iter_lines(self):
            yield b'data: {"type":"answer_delta","text":"hello","sendable":true}'
            yield b''
        def close(self): pass
    def post(*a,**kw): calls.append((a,kw)); return Response()
    monkeypatch.setattr(module.requests,'post',post)
    events=[]
    with pytest.raises(ValueError):
        ButlerProcessor({},raise_errors=True).handle_reply('a','hi',on_event=events.append)
    assert len(calls)==1 and calls[0][0][0].endswith('/v1/handle-stream')
    assert events[0]['text']=='hello'


def test_codex_public_events_only_final_phase(tmp_path,monkeypatch):
    from common.model_stream import bind
    from test_codex_backend import make_backend,FakeThread
    from butler.identity.contacts import Contact
    class Turn:
        def stream(self):
            for method,payload in [
                ('item/started',{'item':{'id':'x','type':'agentMessage','phase':'commentary'}}),
                ('item/agentMessage/delta',{'itemId':'x','delta':'DO NOT SEND'}),
                ('item/started',{'item':{'id':'y','type':'agentMessage','phase':'final_answer'}}),
                ('item/agentMessage/delta',{'itemId':'y','delta':'hello'}),
                ('item/completed',{'item':{'id':'y','type':'agentMessage','phase':'final_answer','text':'hello'}}),
                ('turn/completed',{'turn':{'status':'completed'}})]:
                yield SimpleNamespace(method=method,payload=payload)
    monkeypatch.setattr(FakeThread,'turn',lambda *a,**kw:Turn())
    events=[];backend=make_backend(tmp_path)
    with bind(events.append):
        assert backend.chat(Contact('a','default','a'),'hi')=='hello'
    backend.close()
    assert ''.join(e['text'] for e in events if e['type']=='answer_delta' and e.get('sendable'))=='hello'
    assert 'DO NOT SEND' not in json.dumps(events)


@pytest.mark.parametrize('responses',[False,True])
def test_direct_stream_live_final_and_terminal_validation(monkeypatch,responses):
    from wxbot.processor.openai_compat import OpenAICompatProcessor
    from wxbot.processor.responses import ResponsesProcessor
    import wxbot.processor.openai_compat as module
    events=[]
    class Response:
        headers={'Content-Type':'text/event-stream'}
        def raise_for_status(self): pass
        def close(self): pass
        def iter_lines(self):
            packets=([
                {'type':'response.output_item.added','item':{'id':'m','type':'message','role':'assistant','phase':'final_answer'}},
                {'type':'response.output_text.delta','item_id':'m','delta':'hello'},
                {'type':'response.completed','response':{'status':'completed','output':[{'type':'message','status':'completed','content':[{'type':'output_text','text':'hello'}]}]}}
            ] if responses else [
                {'choices':[{'index':0,'delta':{'content':'hello'}}]},
                {'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]},'[DONE]'])
            for index,p in enumerate(packets):
                if index==(2 if responses else 1):assert any(e.get('text')=='hello' for e in events)
                yield ('data: '+(p if isinstance(p,str) else json.dumps(p))).encode();yield b''
    def post(*a,**kw):
        assert kw['stream'] is True and kw['json']['stream'] is True
        return Response()
    monkeypatch.setattr(module.requests,'post',post)
    processor=(ResponsesProcessor if responses else OpenAICompatProcessor)({'backend':'openai'})
    assert processor.handle_reply('a','hi',on_event=events.append).text=='hello'
    assert ''.join(e['text'] for e in events if e['type']=='answer_delta')=='hello'


def test_butler_client_rejects_final_prefix_change(monkeypatch):
    import wxbot.processor.butler as module
    class Response:
        status_code=200
        def raise_for_status(self):pass
        def close(self):pass
        def iter_lines(self):
            for packet in [{'type':'answer_delta','text':'sent','sendable':True},
                           {'type':'result','result':{'reply':'changed','meta':{}}}]:
                yield ('data: '+json.dumps(packet)).encode();yield b''
    monkeypatch.setattr(module.requests,'post',lambda *a,**kw:Response())
    with pytest.raises(ValueError):module.ButlerProcessor({}).handle_reply('a','hi',on_event=lambda e:None)


def test_composition_filter_split_markers_and_silent():
    from butler.agent.core import _FinalCompositionStream
    f=_FinalCompositionStream()
    emitted=[f.feed(t) for t in ['  hello ','<','<butler:act','ion {"skill":"x"}', '>> world ']]
    assert ''.join(emitted)=='hello  world'
    f=_FinalCompositionStream()
    assert ''.join(f.feed(t) for t in ['[SI','LENT]',' do not send'])==''


def test_sse_endpoint_auth_and_normal_result_envelope():
    from butler.server import make_handler
    from butler.agent.core import Result
    class Bot:
        def handle(self,contact,text,**kw):
            kw['on_event']({'type':'backend','provider':'fake','streaming':False})
            return Result('hello',meta={'msg_id':kw['msg_id']})
    cfg=SimpleNamespace(token='test-token',reply_chunk_chars=500)
    handler_type=make_handler(Bot(),cfg)
    def request(token):
        h=object.__new__(handler_type);h.path='/v1/handle-stream'
        body=json.dumps({'contact':'a','text':'hi','msg_id':'r'}).encode()
        h.headers={'Authorization':token,'Content-Length':str(len(body))}
        h.rfile=io.BytesIO(body);h.wfile=io.BytesIO();codes=[];headers={}
        h.send_response=codes.append;h.send_header=lambda k,v:headers.update({k:v});h.end_headers=lambda:None
        h.do_POST()
        return codes,headers,h.wfile.getvalue()
    assert request('bad')[0]==[401]
    codes,headers,data=request('Bearer test-token')
    assert codes==[200] and headers['Content-Type'].startswith('text/event-stream')
    packets=[json.loads(line[6:]) for line in data.decode().splitlines() if line.startswith('data: ')]
    assert packets[-1]['type']=='result' and packets[-1]['result']['meta']['msg_id']=='r'


def test_direct_provider_brand_preserved(monkeypatch):
    from wxbot.main import build_processor
    import wxbot.processor.openai_compat as module
    response=SimpleNamespace(headers={'Content-Type':'application/json'},raise_for_status=lambda:None,
        json=lambda:{'choices':[{'finish_reason':'stop','message':{'content':'hello'}}]},close=lambda:None)
    monkeypatch.setattr(module.requests,'post',lambda *a,**kw:response)
    processor=build_processor({'bot':{},'installation':{'provider':'deepseek'},'model':{'backend':'openai'}})
    events=[]
    assert processor.handle_reply('a','hi',on_event=events.append).text=='hello'
    assert events[0]['provider']=='deepseek'
    assert any(e.get('fallback')=='complete_result' for e in events)


@pytest.mark.parametrize('packets',[
    [{'choices':[{'delta':{'content':'draft'}}]}],
    [{'choices':[{'delta':{'tool_calls':[{'function':{'arguments':'secret'}}]}}]}],
    [{'choices':[{'delta':{'content':'draft'},'finish_reason':'length'}]},'[DONE]'],
])
def test_direct_stream_failure_no_history_or_replay(monkeypatch,packets):
    from wxbot.processor.openai_compat import OpenAICompatProcessor
    import wxbot.processor.openai_compat as module
    calls=[]
    class Response:
        headers={'Content-Type':'text/event-stream'}
        def raise_for_status(self):pass
        def close(self):pass
        def iter_lines(self):
            for packet in packets:
                yield ('data: '+(packet if isinstance(packet,str) else json.dumps(packet))).encode();yield b''
    def post(*a,**kw):calls.append(1);return Response()
    monkeypatch.setattr(module.requests,'post',post)
    p=OpenAICompatProcessor({});events=[]
    with pytest.raises(ValueError) as failure:p.handle_reply('a','hi',on_event=events.append)
    assert failure.value.retry_safe is False and len(calls)==1 and not p.histories
    assert 'secret' not in json.dumps(events)


@pytest.mark.parametrize('responses',[False,True])
def test_stream_trim_matches_validated_reply_across_chunks(monkeypatch,responses):
    from wxbot.processor.openai_compat import OpenAICompatProcessor
    from wxbot.processor.responses import ResponsesProcessor
    import wxbot.processor.openai_compat as module
    class Response:
        headers={'Content-Type':'text/event-stream'}
        def raise_for_status(self):pass
        def close(self):pass
        def iter_lines(self):
            packets=([{'type':'response.output_item.added','item':{'id':'m','type':'message'}}] if responses else [])
            for text in ['  ','hello ',' world',' \n']:
                packets.append({'type':'response.output_text.delta','item_id':'m','delta':text} if responses else
                    {'choices':[{'delta':{'content':text}}]})
            packets.extend([{'type':'response.completed','response':{'status':'completed','output':[{'type':'message','status':'completed','content':[{'type':'output_text','text':'  hello  world \n'}]}]}}] if responses else
                [{'choices':[{'delta':{},'finish_reason':'stop'}]},'[DONE]'])
            for p in packets:yield ('data: '+(p if isinstance(p,str) else json.dumps(p))).encode();yield b''
    monkeypatch.setattr(module.requests,'post',lambda *a,**kw:Response())
    events=[];p=(ResponsesProcessor if responses else OpenAICompatProcessor)({})
    reply=p.handle_reply('a','hi',on_event=events.append)
    assert ''.join(e['text'] for e in events if e['type']=='answer_delta')==reply.text=='hello  world'


@pytest.mark.parametrize('channel,pending,live',[('dm',[],True),('group',[],False),('dm',[{'text':'older'}],False)])
def test_core_safe_codex_path_composition_and_group_fallback(make_home,monkeypatch,channel,pending,live):
    from common.model_stream import emit,answer
    home=make_home(pending_items=[])
    home.cfg.provider='codex'
    home.butler.catalogue=SimpleNamespace(validate=lambda policy:policy)
    home.butler.pending=SimpleNamespace(take_and_claim=lambda *a,**kw:pending)
    events=[]
    def chat(*a,**kw):
        emit('backend',provider='codex',model='test',streaming=True)
        answer('hello ')
        assert any(e['type']=='answer_delta' for e in events) is live
        return 'hello world'
    monkeypatch.setattr(home.hermes,'chat',chat)
    result=home.butler.handle('101','hi',channel_type=channel,on_event=events.append)
    assert ''.join(e['text'] for e in events if e['type']=='answer_delta')==result.reply
    assert events[0]['streaming'] is live


def test_ollama_incomplete_fallback_never_sendable(monkeypatch):
    from wxbot.processor.ollama import OllamaProcessor
    monkeypatch.setattr('wxbot.processor.ollama.requests.post',lambda *a,**kw:SimpleNamespace(
        raise_for_status=lambda:None,json=lambda:{'done':False,'message':{'content':'draft'}}))
    events=[]
    with pytest.raises(ValueError):OllamaProcessor({}).handle_reply('a','hi',on_event=events.append)
    assert not any(e['type']=='answer_delta' for e in events)


def test_responses_commentary_final_envelope_not_reply():
    from wxbot.processor.responses import ResponsesProcessor
    result=ResponsesProcessor({})._decode({'status':'completed','output':[
        {'type':'message','phase':'commentary','status':'completed','content':[{'type':'output_text','text':'intermediate draft'}]},
        {'type':'message','phase':'final_answer','status':'completed','content':[{'type':'output_text','text':'final'}]}]})
    assert result=='final'


def test_callback_cancellation_propagates_and_unterminated_frame_rejected():
    from common.model_stream import bind,emit,json_frames
    def cancelled(event):raise RuntimeError('cancelled')
    with bind(cancelled),pytest.raises(RuntimeError):emit('answer_delta',text='hello',sendable=True)
    with pytest.raises(ValueError):list(json_frames([b'data: {"type":"complete"}']))
