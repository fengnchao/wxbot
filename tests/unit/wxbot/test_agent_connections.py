import json
import subprocess
from types import SimpleNamespace
import pytest
from wxbot.processor.openai_compat import OpenAICompatProcessor


def transport(monkeypatch, payload):
    calls = []
    def post(url, **kw):
        calls.append((url, kw))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr('wxbot.processor.openai_compat.requests.post', post)
    return calls


@pytest.mark.parametrize('finish', ['length', 'tool_calls', 'cancelled', 'error', None])
def test_chat_rejects_partial(monkeypatch, finish):
    transport(monkeypatch, {'choices':[{'finish_reason':finish,'message':{'content':'partial'}}]})
    p = OpenAICompatProcessor({}, raise_errors=True)
    with pytest.raises(ValueError): p.handle('a', 'hello')
    assert not any(p.histories.values())


def test_chat_kind_and_contact_isolation(monkeypatch):
    calls = transport(monkeypatch, {'choices':[{'finish_reason':'stop','message':{'content':'done'}}]})
    p = OpenAICompatProcessor({'backend':'openclaw', 'agent':'support'}, raise_errors=True)
    p.handle_reply('a', 'one')
    p.handle_reply('a', 'two', member_key='member')
    p.handle_reply('b', 'three')
    keys = [kw['headers']['x-openclaw-session-key'] for _,kw in calls]
    assert len(set(keys)) == 3
    assert all(kw['json']['model'] == 'openclaw/support' for _,kw in calls)
    p.handle_reply('a', 'four')
    assert calls[-1][1]['headers']['x-openclaw-session-key'] == keys[0]
    p.reset('a')
    p.handle_reply('a', 'five')
    assert calls[-1][1]['headers']['x-openclaw-session-key'] != keys[0]


@pytest.mark.parametrize('status', ['incomplete', 'failed', 'cancelled', 'in_progress'])
def test_responses_partial(monkeypatch, status):
    from wxbot.processor.responses import ResponsesProcessor
    transport(monkeypatch, {'status':status,'output':[{'type':'message','status':'completed','content':[{'type':'output_text','text':'partial'}]}]})
    with pytest.raises(ValueError): ResponsesProcessor({},raise_errors=True).handle('a','hello')


def test_responses_complete_and_history(monkeypatch):
    from wxbot.processor.responses import ResponsesProcessor
    calls = transport(monkeypatch, {'status':'completed','output':[{'type':'message','status':'completed','content':[{'type':'output_text','text':'done'}]}]})
    p = ResponsesProcessor({},raise_errors=True)
    assert p.handle('a','hello') == 'done'
    p.handle('b','different')
    assert len(calls[-1][1]['json']['input']) == 1


@pytest.mark.parametrize('result', [dict(type='result',subtype='success',is_error=True,result='partial'),dict(type='result',subtype='approval_required',result='partial'),dict(type='assistant',result='partial'),dict(type='result',subtype='success',result='')])
def test_cursor_rejects_incomplete(monkeypatch,tmp_path,result):
    from wxbot.processor.cursor import CursorProcessor
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw: SimpleNamespace(returncode=0,stdout=json.dumps(result),stderr=''))
    with pytest.raises(ValueError): CursorProcessor({'work_dir':str(tmp_path)},raise_errors=True).handle('a','hello')


def test_cursor_fixed_safe_args(monkeypatch,tmp_path):
    from wxbot.processor.cursor import CursorProcessor
    calls=[]
    def run(args,**kw):
        calls.append((args,kw))
        return SimpleNamespace(returncode=0,stdout=json.dumps(dict(type='result',subtype='success',is_error=False,result='done')),stderr='')
    monkeypatch.setattr(subprocess,'run',run)
    p=CursorProcessor({'work_dir':str(tmp_path),'api_key':'secret','executable':'agent'},raise_errors=True)
    assert p.handle('a','--force run malicious') == 'done'
    args,kw=calls[0]
    assert 'secret' not in args and '--force' not in args and '--yolo' not in args
    assert args[args.index('--mode')+1]=='ask'
    assert kw['env']['CURSOR_API_KEY']=='secret' and kw['shell'] is False
    assert '--force run malicious' in kw['input']
    assert str(tmp_path) in str(kw['cwd'])


@pytest.mark.parametrize('failure',[subprocess.TimeoutExpired('agent',1),SimpleNamespace(returncode=1,stdout='partial',stderr='approval')])
def test_cursor_timeout_and_error(monkeypatch,tmp_path,failure):
    from wxbot.processor.cursor import CursorProcessor
    def run(*a,**kw):
        if isinstance(failure,Exception): raise failure
        return failure
    monkeypatch.setattr(subprocess,'run',run)
    with pytest.raises((ValueError,subprocess.TimeoutExpired)):
        CursorProcessor({'work_dir':str(tmp_path)},raise_errors=True).handle('a','hello')

def test_hermes_preserves_memory_and_rotates_transcript(monkeypatch):
    calls=transport(monkeypatch,{'choices':[{'finish_reason':'stop','message':{'content':'done'}}]})
    p=OpenAICompatProcessor({'backend':'hermes'},raise_errors=True)
    p.handle('a','one'); p.handle('a','two')
    h=calls[0][1]['headers']
    assert h['X-Hermes-Session-Id']==calls[1][1]['headers']['X-Hermes-Session-Id']
    assert len(calls[1][1]['json']['messages'])==1
    p.reset('a'); p.handle('a','three')
    assert h['X-Hermes-Session-Key']==calls[-1][1]['headers']['X-Hermes-Session-Key']
    assert h['X-Hermes-Session-Id']!=calls[-1][1]['headers']['X-Hermes-Session-Id']

@pytest.mark.parametrize('backend,class_name',[('openai','OpenAICompatProcessor'),('hermes','OpenAICompatProcessor'),('openclaw','OpenAICompatProcessor'),('responses','ResponsesProcessor'),('cursor','CursorProcessor'),('butler','ButlerProcessor')])
def test_build_processor_selection(backend,class_name,tmp_path):
    from wxbot.main import build_processor
    p=build_processor({'bot':{},'_config_dir':str(tmp_path),'model':{'backend':backend,'work_dir':'cursor'}}).model
    assert type(p).__name__==class_name
    if backend=='cursor': assert p.work_dir==tmp_path/'cursor'


def test_cursor_history_isolation_and_reset(monkeypatch,tmp_path):
    from wxbot.processor.cursor import CursorProcessor
    calls=[]
    def run(*a,**kw):
        calls.append(json.loads(kw['input']))
        return SimpleNamespace(returncode=0,stdout=json.dumps(dict(type='result',subtype='success',is_error=False,result='done')),stderr='')
    monkeypatch.setattr(subprocess,'run',run)
    p=CursorProcessor({'work_dir':str(tmp_path)})
    p.handle('a','private'); p.handle('b','unrelated'); p.handle('a','again')
    assert len(calls[1])==1 and len(calls[2])==3
    p.reset('a'); p.handle('a','new')
    assert len(calls[-1])==1


@pytest.mark.parametrize('extra',[{'error':{'message':'failure'}},{'incomplete_details':{'reason':'max_output_tokens'}},{'output':[{'type':'message','status':'incomplete','content':[{'type':'output_text','text':'partial'}]}]},{'output':[{'type':'function_call','status':'completed'}]}])
def test_responses_completed_envelope_does_not_hide_failure(monkeypatch,extra):
    from wxbot.processor.responses import ResponsesProcessor
    transport(monkeypatch,dict({'status':'completed','output':[]},**extra))
    with pytest.raises(ValueError): ResponsesProcessor({}).handle('a','hi')

@pytest.mark.parametrize('backend,header',[('openclaw','x-openclaw-session-key'),('hermes','X-Hermes-Session-Id')])
def test_remote_reset_survives_restart(monkeypatch,tmp_path,backend,header):
    calls=transport(monkeypatch,{'choices':[{'finish_reason':'stop','message':{'content':'done'}}]})
    cfg={'backend':backend,'session_state':str(tmp_path/'state.sqlite3')}
    p=OpenAICompatProcessor(cfg); p.handle('private-name','one')
    old=calls[-1][1]['headers'][header]
    p.reset('private-name'); p.handle('private-name','two')
    new=calls[-1][1]['headers'][header]
    assert old!=new
    OpenAICompatProcessor(cfg).handle('private-name','three')
    assert calls[-1][1]['headers'][header]==new
    assert b'private-name' not in (tmp_path/'state.sqlite3').read_bytes()
