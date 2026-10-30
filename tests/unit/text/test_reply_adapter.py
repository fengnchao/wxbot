from types import SimpleNamespace
import pytest
import requests

from wxbot.processor.base import EchoProcessor
from wxbot.processor.butler import ButlerProcessor
from wxbot.processor.router import Router
from wxbot.reply import Reply


def response(monkeypatch, data):
    calls=[]
    def post(*args, **kw):
        calls.append(kw['json'])
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: data)
    monkeypatch.setattr(requests,'post',post)
    return calls


@pytest.mark.parametrize('parts', [None, [], ['你好。',None], [''], 'bad', [1]])
def test_bad_parts_whole_fallback(monkeypatch, parts):
    calls=response(monkeypatch, {'reply':'你好。再见！','reply_parts':parts,'meta':{'reply_complete':True,'msg_id':'req'}})
    p=ButlerProcessor({},raise_errors=True)
    assert p.handle_reply('A','hi',request_id='req') == Reply('你好。再见！',('你好。再见！',))
    assert calls[0]['msg_id']=='req' and len(calls)==1


def test_parts_and_old_interface_single_request(monkeypatch):
    calls=response(monkeypatch, {'reply':'你好。再见！','reply_parts':['你好。','再见！'],'meta':{'reply_complete':True}})
    p=ButlerProcessor({})
    assert p.handle_reply('A','hi').parts == ('你好。','再见！')
    assert p.handle('A','hi') == '你好。再见！'
    assert len(calls)==2


@pytest.mark.parametrize('meta',[{'msg_id':'other'}, {'reply_complete':False}])
def test_protocol_mismatch_raises_even_in_compat_mode(monkeypatch, meta):
    response(monkeypatch,{'reply':'wrong','meta':meta})
    with pytest.raises(ValueError):
        ButlerProcessor({}).handle_reply('A','hi',request_id='req')


def test_old_server_and_silent(monkeypatch):
    response(monkeypatch,{'reply':'old。'})
    assert ButlerProcessor({}).handle_reply('A','hi').parts == ('old。',)
    response(monkeypatch,{'reply':None,'reply_parts':[]})
    assert ButlerProcessor({}).handle_reply('A','hi').parts == ()
    assert EchoProcessor().handle_reply('A','hi') == Reply.from_text('收到：hi')


def test_router_group_reset_and_context_once(monkeypatch):
    calls=response(monkeypatch,{'reply':'ok'})
    router=Router(ButlerProcessor({},raise_errors=True))
    assert router.handle_reply('群','/reset',context='[群聊发言人：甲]').text
    assert calls[-1]['channel_type']=='group'
    router.handle_reply('群','hi',context='[群聊发言人：甲]',request_id='r')
    assert calls[-1]['text']=='[群聊发言人：甲]\nhi'
    assert calls[-1]['msg_id']=='r'
