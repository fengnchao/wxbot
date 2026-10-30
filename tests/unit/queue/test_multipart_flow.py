from types import SimpleNamespace
from wxbot.inbox import MainInbox
from wxbot.reply import Reply
from wxbot.queue_store import Incoming, QueueStore
from wxbot.wechat.chat_window import Message
from wxbot.wechat.main_window import Conversation, Session
from test_main_window import cfg, Desktop, Chat
from test_delivery_queue import Chat as SendingChat


def test_poll_default_passive_and_receive_one_only(monkeypatch):
    desktop=Desktop([Chat('A',[]),Chat('B',[])],[Session('A',1),Session('B',1)])
    inbox=MainInbox(cfg(),None,desktop=desktop)
    received=[]
    def receive(session):
        received.append(session.contact)
        inbox.pending.pop(session.contact)
        return True
    monkeypatch.setattr(inbox,'_receive',receive)
    inbox.poll()
    assert received==[]
    assert inbox._receive_one()
    assert received==['A'] and list(inbox.pending)==['B']


def test_ui_alternates_one_receive_one_send(monkeypatch):
    inbox=MainInbox(cfg(),None,desktop=Desktop([]),monotonic=lambda:0,clock=lambda:0)
    inbox._connected=True
    inbox.pending={'A':Session('A',1),'B':Session('B',1)}
    events=[]
    monkeypatch.setattr(inbox,'poll',lambda **kw:None)
    def receive(session):
        events.append('receive')
        inbox.pending.pop(session.contact)
        return True
    monkeypatch.setattr(inbox,'_receive',receive)
    monkeypatch.setattr(inbox.store,'has_ready_delivery',lambda **kw:True)
    monkeypatch.setattr(inbox.delivery,'start_next',lambda:events.append('send') or True)
    for _ in range(4):
        inbox.tick()
    assert events==['receive','send','receive','send']


def test_reply_arriving_during_capture_waits_for_commit(monkeypatch):
    store=QueueStore(':memory:')
    store.capture('A',[],[Incoming('hi')],now=0)
    store.prepare(quiet=0,max_wait=10,prefix='/',now=0)
    a=store.claim_batch(now=0)
    inbox=MainInbox(cfg(),None,desktop=Desktop([]),store=store,monotonic=lambda:0,clock=lambda:0)
    inbox._connected=True
    inbox.pending={'B':Session('B',1)}
    events=[]
    monkeypatch.setattr(inbox,'poll',lambda **kw:None)
    def receive(session):
        events.append('B capture start')
        store.finish_batch_parts(a.id,('a1',),now=0)
        store.capture('B',[],[Incoming('B message')],now=0)
        inbox.pending.pop('B')
        events.append('B capture commit')
        return True
    monkeypatch.setattr(inbox,'_receive',receive)
    monkeypatch.setattr(inbox.delivery,'start_next',lambda:events.append('A send start') or True)
    inbox.tick()
    inbox.tick()
    assert events==['B capture start','B capture commit','A send start']


def test_receive_failure_backoff_and_other_user_service(monkeypatch):
    clock=[0]
    inbox=MainInbox(cfg(),None,desktop=Desktop([]),monotonic=lambda:clock[0])
    inbox._connected=True
    inbox.pending={'A':Session('A',1),'B':Session('B',1)}
    attempts=[]
    def receive(s):
        attempts.append(s.contact)
        return False
    monkeypatch.setattr(inbox,'_receive',receive)
    assert inbox._receive_one() and inbox._receive_one()
    assert not inbox._receive_one()
    assert attempts==['A','B']
    assert len(inbox.pending)==2


def test_full_a3_b2_flow_preserves_per_user_wait_and_no_switch_while_busy():
    clock=[0]
    store=QueueStore(':memory:')
    chats=[]
    events=[]
    for name in ('A','B'):
        c=Chat(name,[Message('other','hi')])
        c.starts=0
        c.bubble=True
        c.start_send=SendingChat.start_send.__get__(c,Chat)
        def available(c=c, **kwargs):
            desktop.current=Conversation(c.title,False)
            events.append(('select',c.title))
            return True
        c.available=available
        def remembered(text,c=c):
            events.append(('sent',text))
        c.remember_sent=remembered
        chats.append(c)
        store.capture(name,[{'sender':'other','text':'hi'}],[Incoming('hi')],now=0)
    desktop=Desktop(chats,current=Conversation('A',False))
    class Router:
        def handle_reply(self, contact, text, **kw):
            parts=tuple(contact+str(n) for n in range(1,4 if contact=='A' else 3))
            return Reply(''.join(parts),parts)
    inbox=MainInbox(cfg(),Router(),desktop=desktop,store=store,clock=lambda:clock[0],monotonic=lambda:clock[0])
    assert inbox.worker.process_once() and inbox.worker.process_once()
    store.capture('A',[],[Incoming('next round')],now=0)
    for _ in range(30):
        was_busy=inbox.delivery.busy
        before=len([x for x in events if x[0]=='select'])
        inbox.tick()
        if was_busy:
            assert len([x for x in events if x[0]=='select'])==before
        if store.get_batch(store.records('batches')[0]['id'])['state']!='done':
            assert store.prepare(quiet=0,max_wait=10,prefix='/',now=0)==0
        clock[0]+=.1
    assert [text for kind,text in events if kind=='sent']==['A1','B1','A2','B2','A3']
    assert store.prepare(quiet=0,max_wait=10,prefix='/',now=5)==1
    assert store.claim_batch(now=5).text=='next round'


def test_confirming_keeps_ui_until_bubble_visible_but_records_badges():
    clock=[0]
    a=Chat('A',[Message('other','hi')])
    b=Chat('B',[Message('other','B question')])
    a.starts=0
    a.bubble=False
    a.start_send=SendingChat.start_send.__get__(a,Chat)
    desktop=Desktop([a,b],current=Conversation('A',False))
    inbox=MainInbox(cfg(),None,desktop=desktop,clock=lambda:clock[0],monotonic=lambda:clock[0])
    inbox.poll()
    key=inbox.store.enqueue_delivery('A','answer',now=0)
    inbox.tick()  # Start A.
    inbox.tick()  # Type.
    inbox.tick()  # Enter, but no bubble yet.
    assert inbox.store.get_delivery(key)['state']=='confirming'
    desktop.pending=[Session('B',1)]
    clock[0]=2
    inbox.tick()
    assert desktop.current.title=='A' and inbox.delivery.busy
    assert inbox.store.pending_sessions()[0]['contact']=='B'
    assert inbox.store.records('inbox')==[]
    a.messages.append(Message('self','answer'))
    inbox.tick()
    assert not inbox.delivery.busy and desktop.current.title=='A'
    inbox.tick()
    assert desktop.current.title=='B'
    assert [r['text'] for r in inbox.store.records('inbox')]==['B question']
