import pytest


def test_independent_loop_keeps_polling_after_model_failure(monkeypatch):
    import wxbot.main as entry
    from wxbot.wechat.chat_window import Message
    class StopLoop(Exception):pass
    sent=[];calls=[];sleeps=[]
    class Chat:
        def __init__(self,*a,**kw):self.reads=0
        def available(self):return True
        def read_messages(self):
            self.reads+=1
            old=[Message('other','old message')]
            if self.reads==1:return old
            messages=old+[Message('other','failed turn')]
            return messages if self.reads<4 else messages+[Message('other','successful turn')]
        def send(self,text):sent.append(text);return True
    class Router:
        def handle(self,*a,**kw):
            calls.append(a)
            if len(calls)==1:raise TimeoutError('private payload')
            return 'complete reply'
    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps)>=6:raise StopLoop()
    monkeypatch.setattr(entry,'load_config',lambda:{'wechat':{'mode':'independent'},
        'bot':{'bound_users':['Alice']},'outbound':{'enabled':False}})
    monkeypatch.setattr(entry,'build_processor',lambda _:Router())
    monkeypatch.setattr(entry,'ChatWindow',Chat)
    monkeypatch.setattr(entry,'restore_pending',lambda:None)
    monkeypatch.setattr(entry.time,'sleep',sleep)
    with pytest.raises(StopLoop):entry.run()
    assert len(calls)==2 and sent==['complete reply']


def test_unknown_group_member_reset_clears_the_same_api_history(monkeypatch):
    from types import SimpleNamespace
    from wxbot.processor.router import Router
    from wxbot.processor.openai_compat import OpenAICompatProcessor
    calls=[]
    def post(url,**kw):
        calls.append(kw['json'])
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'choices':[{'finish_reason':'stop','message':{'content':'done'}}]})
    monkeypatch.setattr('wxbot.processor.openai_compat.requests.post',post)
    router=Router(OpenAICompatProcessor({'backend':'openai'}))
    context='[群聊发言人：未知成员; member_id=unknown]'
    router.handle('Team','before',context=context)
    router.handle('Team','/reset',context=context)
    router.handle('Team','after',context=context)
    assert len(calls[-1]['messages'])==1
