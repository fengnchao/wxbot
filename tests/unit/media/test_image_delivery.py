from contextlib import contextmanager
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
import pytest
from PIL import Image

class Clipboard:
    def __init__(self): self.data={13:'original',99:b'rich'}; self.seq=1; self.disposed=False
    @contextmanager
    def open(self): yield
    def sequence(self): return self.seq
    def snapshot(self): return deepcopy(self.data)
    def write_dib(self,data): self.data={8:data}; self.seq+=1
    def restore(self,saved): self.data=deepcopy(saved); self.seq+=1
    def free_snapshot(self,saved): pass
    def dispose(self): self.disposed=True


def test_image_clipboard_lease_restores_formats_and_does_not_overwrite_user_copy():
    from wxbot.wechat.clipboard import ImageClipboardLease
    api=Clipboard(); before=deepcopy(api.data)
    lease=ImageClipboardLease(b'dib',api=api)
    assert api.data=={8:b'dib'} and lease.is_current()
    assert lease.close() and api.data==before
    api=Clipboard(); lease=ImageClipboardLease(b'dib',api=api)
    api.data={13:'new copy'}; api.seq+=1
    assert lease.close() and api.data=={13:'new copy'}


def test_image_clipboard_refuses_unbackupable_formats():
    from wxbot.wechat.clipboard import ImageClipboardLease
    api=Clipboard(); api.snapshot=lambda: (_ for _ in ()).throw(OSError('unsupported'))
    with pytest.raises(OSError): ImageClipboardLease(b'dib',api=api)
    assert api.data=={13:'original',99:b'rich'} and api.disposed

class Chat:
    def __init__(self):
        self.good=True; self.preview=False; self.sent=0; self.bubbles=[]; self.draft=''
        self.wcfg={'image':{'preview':{'x':1},'send':{'x':2}}}
    def _can_send(self,win,edit): return self.good
    def target_is_current(self,win): return self.good
    def _input_text(self,edit): return self.draft
    def image_preview(self,win): return ('preview','button') if self.preview else None
    def image_preview_draft(self,preview): return ()
    def image_preview_is_current(self,win,preview,button): return self.good and self.preview
    def image_bubbles(self,win): return list(self.bubbles)
    def submit_image_preview(self,button): self.sent+=1


def test_image_session_guards_paste_preview_and_single_submission(tmp_path):
    from wxbot.wechat.image import ImageSession
    path=tmp_path/'x.png'; Image.new('RGB',(2,2),'red').save(path)
    chat=Chat(); api=Clipboard(); clock=[0]; keys=[]
    session=ImageSession(chat,object(),object(),path,clock=lambda:clock[0],
                         clipboard_factory=lambda data: __import__('wxbot.wechat.clipboard',fromlist=['ImageClipboardLease']).ImageClipboardLease(data,api=api),send_keys=lambda *a,**k:keys.append(a))
    assert session.step()=='typing' and keys
    assert api.data.get(8) and not session.enter_attempted
    chat.preview=True
    assert session.step()=='typing' and api.data.get(13)=='original'
    assert session.step()=='submitted' and session.enter_attempted and chat.sent==1
    assert session.step()=='submitted' and chat.sent==1
    assert not session.confirmation_visible()
    chat.bubbles=[{'id':[1,2], 'sender':'self'}]
    assert session.confirmation_visible()


def test_image_session_focus_change_or_missing_preview_never_sends(tmp_path):
    from wxbot.wechat.image import ImageSession
    path=tmp_path/'x.png'; Image.new('RGB',(2,2)).save(path)
    chat=Chat(); api=Clipboard(); clock=[0]
    def lease(data):
        from wxbot.wechat.clipboard import ImageClipboardLease
        return ImageClipboardLease(data,api=api)
    session=ImageSession(chat,object(),object(),path,clock=lambda:clock[0],clipboard_factory=lease,send_keys=lambda *a,**k:None)
    session.step(); clock[0]=3
    assert session.step()=='blocked' and not session.enter_attempted and chat.sent==0
    assert session.failure_details['manual_required'] and api.data.get(13)=='original'
    chat=Chat(); chat.good=False; api=Clipboard()
    session=ImageSession(chat,object(),object(),path,clipboard_factory=lease,send_keys=lambda *a,**k:pytest.fail('no input'))
    assert session.step()=='blocked' and not session.enter_attempted

def test_package_receipt_waits_for_every_image_and_text_bubble(tmp_path):
    from wxbot.delivery import DeliveryPump
    from wxbot.outbound import OutboundRequest
    from wxbot.queue_store import QueueStore
    from wxbot.wechat.chat_window import Message
    class DeliveryChat:
        expected_group=False
        def __init__(self): self.messages=[Message('other','hello')]; self.images=0
        def read_messages(self,**kw): return list(self.messages)
        def read_from_window(self,win,**kw): return list(self.messages)
        def target_is_current(self,win): return True
        def remember_sent(self,text): pass
        def start_send(self,text,**kw):
            task=SimpleNamespace(win=object(),enter_attempted=False,error='',state='typing')
            def step():
                task.before_enter(); task.enter_attempted=True
                self.messages.append(Message('self',text))
                return 'submitted'
            task.step=step
            return task
        def start_image(self,path,**kw):
            task=SimpleNamespace(win=object(),enter_attempted=False,error='',state='typing')
            def step():
                task.before_enter(); task.enter_attempted=True
                self.images+=1
                return 'submitted'
            task.step=step
            task.confirmation_visible=lambda:self.images>0
            return task
    store=QueueStore(':memory:'); chat=DeliveryChat()
    pump=DeliveryPump(store,lambda c:chat,lambda c:True,lambda:None,clock=lambda:0,monotonic=lambda:0)
    items=[{'kind':'text','text':'one'},{'kind':'image','media_id':'a'*32}]
    req=OutboundRequest('A','',items=items,request_id='source-1',media_paths={'a'*32:tmp_path/'safe'})
    duplicate=OutboundRequest('A','',items=items,request_id='source-1',media_paths={'a'*32:tmp_path/'safe'})
    pump.enqueue(req);pump.enqueue(duplicate)
    pump.tick();pump.tick()
    assert not req.event.is_set() and not duplicate.event.is_set()
    pump.tick();pump.tick()
    assert req.event.is_set() and req.ok and duplicate.ok and chat.images==1
    completed=OutboundRequest('A','',items=items,request_id='source-1',media_paths={'a'*32:tmp_path/'safe'})
    pump.enqueue(completed)
    assert completed.event.is_set() and completed.ok

def test_read_clipboard_lease_accepts_only_expected_process_and_preserves_new_copy():
    from wxbot.wechat.clipboard import ClipboardReadLease
    api=Clipboard(); api.pid=123; api.owner_process_id=lambda:api.pid; api.read_text=lambda:api.data[13]
    before=deepcopy(api.data)
    lease=ClipboardReadLease(api=api)
    api.data={13:'https://t.me/channel/1'}; api.seq+=1
    assert lease.read(expected_process_id=123)=='https://t.me/channel/1'
    assert lease.close() and api.data==before
    api=Clipboard(); api.pid=123; api.owner_process_id=lambda:api.pid; api.read_text=lambda:api.data[13]
    lease=ClipboardReadLease(api=api)
    api.data={13:'source'};api.seq+=1
    assert lease.read(expected_process_id=123)=='source'
    api.data={13:'user copied'};api.seq+=1;api.pid=456
    assert lease.close() and api.data=={13:'user copied'}


def test_read_clipboard_lease_rejects_unchanged_or_wrong_owner():
    from wxbot.wechat.clipboard import ClipboardReadLease
    api=Clipboard(); api.owner_process_id=lambda:999;api.read_text=lambda:api.data[13]
    lease=ClipboardReadLease(api=api)
    with pytest.raises(OSError): lease.read(expected_process_id=123)
    api.seq+=1
    with pytest.raises(OSError): lease.read(expected_process_id=123)
    assert lease.close() and api.data[13]=='original'

def test_image_review_holds_ui_across_restart_until_explicit_resolution(tmp_path):
    from wxbot.delivery import DeliveryPump
    from wxbot.queue_store import QueueStore
    path=tmp_path/'queue.db'; store=QueueStore(path)
    package=store.enqueue_package('A',[{'kind':'image','media_id':'a'*32}],'review',media_paths={'a'*32:tmp_path/'safe'},now=0)
    row=store.claim_delivery(now=0)
    store.recover(now=1)
    pump=DeliveryPump(store,lambda c:None,lambda c:False,lambda:None)
    assert pump.requires_ui_review
    store.close();store=QueueStore(path)
    pump=DeliveryPump(store,lambda c:None,lambda c:False,lambda:None)
    assert pump.requires_ui_review
    store.resolve(row.id,delivery=True,sent=False,now=3)
    assert not pump.requires_ui_review

def test_image_confirmation_requires_prior_image_ids_to_remain_stable(tmp_path):
    from wxbot.wechat.image import ImageSession
    path=tmp_path/'x.png'; Image.new('RGB',(2,2)).save(path)
    chat=Chat(); chat.bubbles=[{'id':[1], 'sender':'self'}]
    session=ImageSession(chat,object(),object(),path,send_keys=lambda *a,**kw:None)
    session.enter_attempted=True
    session.baseline_images=[{'id':[1], 'sender':'self'}]
    # A recycled/recreated row is not proof that another picture was sent.
    chat.bubbles=[{'id':[2], 'sender':'self'}]
    assert not session.confirmation_visible()
    chat.bubbles=[{'id':[1], 'sender':'self'},{'id':[2], 'sender':'self'}]
    assert session.confirmation_visible()

def package_pump(authorizer, *, image=False):
    from wxbot.delivery import DeliveryPump
    from wxbot.queue_store import QueueStore
    from wxbot.wechat.chat_window import Message
    store=QueueStore(':memory:')
    items=[{'kind':'image','media_id':'a'*32}] if image else [{'kind':'text','text':'news'}]
    package=store.enqueue_package('A',items,'authorization',media_paths={'a'*32:'safe'},now=0)
    calls=[]
    class DeliveryChat:
        def read_messages(self,**kw): return [Message('other','anchor')]
        def read_from_window(self,*a,**kw): return self.read_messages()
        def target_is_current(self,win): return True
        def start_send(self,text,**kw):
            task=SimpleNamespace(win=object(),enter_attempted=False,error='',index=0,_pasted=False)
            def step():
                calls.append('step')
                task.index=1;task._pasted=True
                if task.before_enter() is False:return 'typing'
                task.enter_attempted=True
                return 'submitted'
            task.step=step
            return task
        def start_image(self,path,**kw): return self.start_send('',**kw)
    chat=DeliveryChat()
    pump=DeliveryPump(store,lambda c:calls.append('get') or chat,
                      lambda c:calls.append('capture') or True,lambda:calls.append('discover'),
                      package_authorizer=authorizer,clock=lambda:0,monotonic=lambda:0)
    return store,pump,package,calls


def test_package_pending_authorization_defers_without_any_ui_or_failure():
    store,pump,package,calls=package_pump(lambda row:None)
    pump.tick()
    assert calls==[] and not pump.busy
    row=store.records('outbox')[0]
    assert row['state']=='pending' and row['failed_at'] is None and row['retries']==0
    assert not store.package_receipt(package)['done']


def test_revoked_package_never_touches_ui_and_finishes_receipt():
    store,pump,package,calls=package_pump(lambda row:False)
    pump.tick()
    assert calls==[] and not pump.busy
    assert store.package_receipt(package)=={'done':True,'ok':False,'state':'skipped'}


def test_active_package_rechecks_authorization_and_never_enters_after_revocation():
    verdict=[True]
    store,pump,package,calls=package_pump(lambda row:verdict[0],image=True)
    pump.tick();task=pump.active.typing
    task._pasted=True
    verdict[0]=None
    pump.tick()
    assert calls==['discover','get','capture'] and pump.busy
    verdict[0]=False
    pump.tick()
    assert not task.enter_attempted and not pump.busy and pump.requires_ui_review
    row=store.records('outbox')[0]
    assert row['manual_required'] and row['state']=='blocked'


def test_final_authorization_check_pauses_then_stops_already_pasted_text():
    answers=iter([True,True,None,True,False])
    store,pump,package,calls=package_pump(lambda row:next(answers))
    pump.tick(); task=pump.active.typing
    pump.tick()
    assert pump.busy and not task.enter_attempted
    pump.tick()
    assert not task.enter_attempted and pump.requires_ui_review and not pump.busy


def test_image_before_enter_callback_can_pause_without_submitting(tmp_path):
    from wxbot.wechat.image import ImageSession
    from wxbot.wechat.clipboard import ImageClipboardLease
    path=tmp_path/'x.png';Image.new('RGB',(2,2)).save(path)
    chat=Chat();api=Clipboard()
    session=ImageSession(chat,object(),object(),path,clipboard_factory=lambda data:ImageClipboardLease(data,api=api),send_keys=lambda *a,**kw:None)
    session.step();chat.preview=True;session.step()
    session.before_enter=lambda:False
    assert session.step()=='typing' and not session.enter_attempted and chat.sent==0

def test_authorization_pause_extends_image_preview_deadline(tmp_path):
    from wxbot.wechat.image import ImageSession
    from wxbot.wechat.clipboard import ImageClipboardLease
    from wxbot.delivery import ActiveDelivery
    path=tmp_path/'x.png';Image.new('RGB',(2,2)).save(path)
    chat=Chat();api=Clipboard();clock=[0];verdict=[True]
    store,pump,package,calls=package_pump(lambda row:verdict[0],image=True)
    pump.tick();delivery=pump.active.delivery
    session=ImageSession(chat,object(),object(),path,clock=lambda:clock[0],clipboard_factory=lambda data:ImageClipboardLease(data,api=api),send_keys=lambda *a,**kw:None)
    session.step();chat.preview=True;session.step()
    pump.active=ActiveDelivery(delivery,chat,session,[])
    pump.monotonic=lambda:clock[0]
    verdict[0]=None;pump.tick();clock[0]=10
    verdict[0]=True
    session.before_enter=lambda:False
    pump.tick()
    assert session.state=='typing' and not session.enter_attempted
    assert not store.package_receipt(package)['done']


def test_real_text_before_enter_false_never_presses_enter(monkeypatch):
    from test_typing import make_chat
    chat,keys=make_chat(monkeypatch)
    now=[0.0];task=chat.start_send('one',clock=lambda:now[0])
    task.before_enter=lambda:False
    task.step();now[0]=1;task.step()
    assert not task.enter_attempted and '{Enter}' not in keys
    task.before_enter=lambda:None
    task.step()
    assert task.enter_attempted and keys[-1]=='{Enter}'

@pytest.mark.parametrize('field',['draft','caption'])
@pytest.mark.parametrize('stage',['preview','submit','after_guard'])
def test_image_session_external_draft_or_caption_never_submits(tmp_path,field,stage):
    from wxbot.wechat.image import ImageSession
    from wxbot.wechat.clipboard import ImageClipboardLease
    path=tmp_path/'x.png';Image.new('RGB',(2,2)).save(path)
    chat=Chat();api=Clipboard();chat.caption=''
    chat.image_preview_draft=lambda preview:(((99,),chat.caption),)
    session=ImageSession(chat,object(),object(),path,clipboard_factory=lambda data:ImageClipboardLease(data,api=api),send_keys=lambda *a,**kw:None)
    session.step();chat.preview=True
    if stage=='preview':setattr(chat,field,'unapproved user content')
    else:
        assert session.step()=='typing'
        if stage=='submit':setattr(chat,field,'unapproved user content')
        else:session.before_enter=lambda:setattr(chat,field,'unapproved user content')
    assert session.step()=='blocked'
    assert not session.enter_attempted and chat.sent==0
    assert session.failure_details['manual_required']
    assert getattr(chat,field)=='unapproved user content'
    assert api.data.get(13)=='original'


def test_image_session_unreadable_caption_proof_fails_closed(tmp_path):
    from wxbot.wechat.image import ImageSession
    from wxbot.wechat.clipboard import ImageClipboardLease
    path=tmp_path/'x.png';Image.new('RGB',(2,2)).save(path)
    chat=Chat();api=Clipboard();chat.image_preview_draft=lambda preview:None
    session=ImageSession(chat,object(),object(),path,clipboard_factory=lambda data:ImageClipboardLease(data,api=api),send_keys=lambda *a,**kw:None)
    session.step();chat.preview=True
    assert session.step()=='blocked' and not session.enter_attempted and chat.sent==0
    assert session.failure_details['manual_required']

def test_read_clipboard_lease_restores_expected_nontext_copy_after_read_failure():
    from wxbot.wechat.clipboard import ClipboardReadLease
    api=Clipboard();api.owner_process_id=lambda:123
    before=deepcopy(api.data)
    lease=ClipboardReadLease(api=api)
    api.data={8:b'copy from expected native app'};api.seq+=1
    api.read_text=lambda:(_ for _ in ()).throw(OSError('not text'))
    with pytest.raises(OSError):lease.read(expected_process_id=123)
    assert lease.close() and api.data==before


def test_read_clipboard_lease_read_failure_does_not_overwrite_user_copy():
    from wxbot.wechat.clipboard import ClipboardReadLease
    api=Clipboard();api.pid=123;api.owner_process_id=lambda:api.pid
    lease=ClipboardReadLease(api=api)
    api.data={8:b'copy from expected native app'};api.seq+=1
    def fail_read():
        api.data={13:'new user copy'};api.seq+=1;api.pid=456
        raise OSError('copy raced')
    api.read_text=fail_read
    with pytest.raises(OSError):lease.read(expected_process_id=123)
    assert lease.close() and api.data=={13:'new user copy'}


def test_native_preview_caption_proof_requires_complete_readable_tree():
    from wxbot.wechat.chat_window import ChatWindow
    class Node:
        def __init__(self,kind='PaneControl',text='',children=()):
            self.ControlTypeName=kind;self.text=text;self.children=children
        def GetRuntimeId(self):return [id(self)]
        def GetValuePattern(self):return SimpleNamespace(Value=self.text)
        def GetChildren(self):return self.children
    chat=ChatWindow('A',{})
    editor=Node('EditControl','');root=Node(children=[editor])
    proof=chat.image_preview_draft(root)
    assert proof==(((id(editor),),''),)
    editor.text='external caption'
    assert chat.image_preview_draft(root)==(((id(editor),),'external caption'),)
    editor.GetValuePattern=lambda:(_ for _ in ()).throw(OSError('not exposed'))
    assert chat.image_preview_draft(root) is None
    root.GetChildren=lambda:(_ for _ in ()).throw(OSError('tree unreadable'))
    assert chat.image_preview_draft(root) is None
