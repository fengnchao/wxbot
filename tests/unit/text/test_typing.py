from types import SimpleNamespace

import pytest

from wxbot.wechat.chat_window import ChatWindow, Message
from wxbot.delivery import reply_is_visible


def make_chat(monkeypatch):
    from wxbot.wechat import chat_window as module
    chat = ChatWindow("A", {"input": {}})
    root = SimpleNamespace(SetActive=lambda: None,Name='A',NativeWindowHandle=123)
    edit = SimpleNamespace(Click=lambda **kw: None,
                           value="",HasKeyboardFocus=True)
    edit.GetValuePattern = lambda: SimpleNamespace(Value=edit.value)
    from wxbot.wechat import typing as typing_module
    from test_clipboard import FakeClipboard
    clipboard=FakeClipboard()
    original_clipboard=dict(clipboard.data)
    def lease(text):
        from wxbot.wechat.clipboard import ClipboardLease
        return ClipboardLease(text,api=clipboard)
    monkeypatch.setattr(typing_module,'ClipboardLease',lease,raising=False)
    edit.clipboard=clipboard
    edit.original_clipboard=original_clipboard
    edit.pasted=[]
    monkeypatch.setattr(chat, "_window", lambda: root)
    monkeypatch.setattr(chat, "_find", lambda *args: edit)
    monkeypatch.setattr(module.time, "sleep", lambda *args: None)
    sent = []
    def send(keys, **kwargs):
        sent.append(keys)
        if keys in ("{Enter}", "{Ctrl}a{Backspace}"):
            edit.value = ""
        elif keys=='{Ctrl}v':
            edit.pasted.append(clipboard.data[13])
            edit.value+=clipboard.data[13]
        else:
            literal = keys.replace("{Shift}({Enter})", "\n").replace("{{}", "{").replace("{}}", "}")
            edit.value += literal.encode("utf-16-le", "surrogatepass").decode("utf-16-le")
    monkeypatch.setattr(module.auto, "SendKeys", send)
    monkeypatch.setattr(module.auto,'GetForegroundWindow',lambda:123)
    return chat, sent


def test_typing_steps_keep_half_second_between_batches_and_one_final_enter(monkeypatch):
    chat, sent = make_chat(monkeypatch)
    clock = [0.0]
    task = chat.start_send("1234567890", clock=lambda: clock[0])
    assert task.step() == "typing"
    assert sent == ["{Ctrl}v"]
    assert task.edit.pasted==['12345']
    clock[0] = 0.49
    task.step()
    assert sent == ["{Ctrl}v"]
    clock[0] = 0.5
    task.step()
    assert sent == ["{Ctrl}v", "{Ctrl}v"]
    assert task.edit.pasted==['12345','67890']
    clock[0] = 0.6
    assert task.step() == "submitted"
    assert sent == ["{Ctrl}v", "{Ctrl}v", "{Enter}"]
    assert task.edit.clipboard.data==task.edit.original_clipboard
    task.step()
    assert sent.count("{Enter}") == 1


def test_focus_change_during_wait_stops_without_waiting_or_pressing_enter(monkeypatch):
    chat, sent = make_chat(monkeypatch)
    task = chat.start_send("123456", clock=lambda: 0)
    task.step()
    monkeypatch.setattr(chat, "_can_send", lambda *args: False)
    assert task.step() == "blocked"
    assert "{Enter}" not in sent


@pytest.mark.parametrize('field,value,reason',[
    ('actual_contact','B','聊天对象变化'),
    ('actual_contact',None,'标题无法读取'),
    ('actual_group',True,'类型与收件目标不一致'),
    ('foreground_hwnd',456,'前台窗口变化'),
    ('input_focused',False,'输入焦点不在消息输入框'),
])
def test_failure_distinguishes_target_type_foreground_and_focus(monkeypatch,field,value,reason):
    chat,sent=make_chat(monkeypatch)
    task=chat.start_send('secret reply',clock=lambda:0)
    diagnostics={'expected_contact':'A','actual_contact':'A','expected_group':False,'actual_group':False,
                 'expected_hwnd':123,'foreground_hwnd':123,'input_focused':True}
    diagnostics[field]=value
    monkeypatch.setattr(chat,'send_diagnostics',lambda *args:diagnostics)
    monkeypatch.setattr(chat,'target_is_current',lambda *args:field=='input_focused')
    monkeypatch.setattr(chat,'_can_send',lambda *args:False)
    assert task.step()=='blocked' and reason in task.error
    assert task.failure_details['phase']=='input_guard'
    assert task.failure_details['characters_entered']==0
    assert task.failure_details['enter_attempted'] is False
    assert sent==[]


def test_exception_while_pressing_enter_is_uncertain_and_never_clears_or_retries(monkeypatch):
    from wxbot.wechat import chat_window as module
    chat, sent = make_chat(monkeypatch)
    original = module.auto.SendKeys
    def send(keys, **kwargs):
        if keys == "{Enter}":
            sent.append(keys)
            raise RuntimeError("send result unknown")
        original(keys, **kwargs)
    monkeypatch.setattr(module.auto, "SendKeys", send)
    clock = [0]
    task = chat.start_send("hello", clock=lambda: clock[0])
    task.step()
    clock[0] = 1
    assert task.step() == "uncertain"
    task.step()
    assert sent == ["{Ctrl}v", "{Enter}"]


def test_confirmation_requires_a_new_self_message_and_preserves_identical_replies():
    old = [Message("other", "问题"), Message("self", "好的")]
    assert not reply_is_visible(old, old, "好的")
    assert not reply_is_visible(old, old + [Message("other", "好的")], "好的")
    assert reply_is_visible(old, old + [Message("self", "好的")], "好的")
    assert not reply_is_visible(old, [Message("self", "好的")], "好的")


def test_confirmation_sender_detection_does_not_use_previous_reply_text_cache(monkeypatch):
    chat = ChatWindow("A", {})
    chat.remember_sent("好的")
    monkeypatch.setattr(chat, "side_scores", lambda *args: (100, 0))
    assert chat._classify(None, "好的", None) == "other"
    assert chat._classify(None, "好的", None, use_sent_cache=False) == "other"
    monkeypatch.setattr(chat, "side_scores", lambda *args: None)
    assert chat._classify(None, "好的", None) == "self"
    assert chat._classify(None, "好的", None, use_sent_cache=False) == "system"


def test_missing_message_control_is_not_reported_as_an_empty_chat(monkeypatch):
    chat = ChatWindow("A", {"message_list": {}})
    monkeypatch.setattr(chat, "_message_list", lambda: None)
    monkeypatch.setattr(chat, "_find", lambda *args: None)
    with pytest.raises(RuntimeError):
        chat.read_messages()
    with pytest.raises(RuntimeError):
        chat.read_from_window(object())


def test_unreadable_draft_never_types_or_clears_user_input(monkeypatch):
    chat, sent = make_chat(monkeypatch)
    monkeypatch.setattr(chat, "_input_text", lambda *args: None)
    assert chat.start_send("回答") is None
    assert sent == []


def test_paste_preserves_chinese_punctuation_and_non_bmp_characters(monkeypatch):
    chat, sent = make_chat(monkeypatch)
    clock = [0]
    task = chat.start_send("中,文。🤖", clock=lambda: clock[0])
    task.step()
    assert sent==['{Ctrl}v']
    assert task.edit.pasted==['中,文。🤖']
    assert task.edit.value == "中,文。🤖"
    clock[0] = 1
    assert task.step() == "submitted"


def test_punctuation_braces_and_newlines_are_literal_clipboard_text(monkeypatch):
    chat,sent=make_chat(monkeypatch)
    clock=[0]
    text='抱歉，我这边。你好？\n{Enter}，，。。🤖'
    task=chat.start_send(text,clock=lambda:clock[0])
    for _ in range(30):
        task.step()
        clock[0]+=.5
        if task.state!='typing': break
    assert task.state=='submitted'
    assert ''.join(task.edit.pasted)==text
    assert all(key in ('{Ctrl}v','{Enter}') for key in sent)
    assert sent.count('{Enter}')==1
    assert task.edit.clipboard.data==task.edit.original_clipboard


def test_dropped_character_is_detected_before_enter_and_draft_is_preserved(monkeypatch):
    chat, sent = make_chat(monkeypatch)
    clock = [0]
    task = chat.start_send("你好，世界", clock=lambda: clock[0])
    task.step()
    task.edit.value = "你好，，界"  # 复现输入法把汉字替换为前一个标点。
    clock[0] = 1
    assert task.step() == "blocked"
    assert "{Enter}" not in sent
    assert "{Ctrl}a{Backspace}" not in sent
    assert task.edit.value == "你好，，界"


def test_target_and_draft_are_rechecked_after_before_enter_callback(monkeypatch):
    chat, sent = make_chat(monkeypatch)
    clock = [0]
    task = chat.start_send("你好", clock=lambda: clock[0])
    task.step()
    task.before_enter = lambda: setattr(task.edit, "value", "用户编辑了草稿")
    clock[0] = 1
    assert task.step() == "blocked"
    assert "{Enter}" not in sent
    assert task.edit.value == "用户编辑了草稿"


def test_user_copy_before_ctrl_v_blocks_paste_and_preserves_the_copy(monkeypatch):
    from wxbot.wechat import typing as module
    chat,sent=make_chat(monkeypatch)
    original=module.ClipboardLease
    def lease(text):
        result=original(text)
        chat._find(None,None).clipboard.data={13:'user copy'}
        chat._find(None,None).clipboard.seq+=1
        return result
    monkeypatch.setattr(module,'ClipboardLease',lease)
    task=chat.start_send('你好')
    assert task.step()=='blocked'
    assert sent==[] and task.edit.value==''
    assert task.edit.clipboard.data=={13:'user copy'}


def test_user_copy_after_paste_is_preserved_and_the_valid_reply_can_submit(monkeypatch):
    chat,sent=make_chat(monkeypatch)
    clock=[0]
    task=chat.start_send('你好',clock=lambda:clock[0])
    task.step()
    task.edit.clipboard.data={13:'user copy'};task.edit.clipboard.seq+=1
    clock[0]=1
    assert task.step()=='submitted'
    assert sent==['{Ctrl}v','{Enter}']
    assert task.edit.clipboard.data=={13:'user copy'}


def test_clipboard_write_failure_never_falls_back_to_keyboard_or_submits(monkeypatch):
    chat,sent=make_chat(monkeypatch)
    task=chat.start_send('你好')
    task.edit.clipboard.fail_write=True
    assert task.step()=='blocked'
    assert sent==[]
    assert task.edit.clipboard.data==task.edit.original_clipboard


def test_restore_failure_blocks_submit_until_background_cleanup_can_restore(monkeypatch):
    from wxbot.wechat.clipboard import restore_pending
    chat,sent=make_chat(monkeypatch)
    clock=[0]
    task=chat.start_send('你好',clock=lambda:clock[0])
    task.step()
    task.edit.clipboard.busy=True
    try:
        clock[0]=1
        assert task.step()=='blocked'
        assert sent==['{Ctrl}v']
    finally:
        task.edit.clipboard.busy=False
        restore_pending(force=True)
    assert task.edit.clipboard.data==task.edit.original_clipboard


def test_stopping_mid_paste_restores_clipboard_without_enter(monkeypatch):
    chat,sent=make_chat(monkeypatch)
    task=chat.start_send('你好')
    task.step()
    assert task.close()
    assert sent==['{Ctrl}v']
    assert task.edit.clipboard.data==task.edit.original_clipboard


def test_edit_between_batches_stops_before_appending_another_batch(monkeypatch):
    chat,sent=make_chat(monkeypatch)
    clock=[0]
    task=chat.start_send('1234567890',clock=lambda:clock[0])
    task.step()
    clock[0]=.1
    task.step()  # Prefix has been verified; waiting for the next batch.
    task.edit.value='user draft'
    clock[0]=.5
    assert task.step()=='blocked'
    assert sent==['{Ctrl}v'] and task.edit.value=='user draft'


def test_independent_sender_stops_if_another_app_gets_focus(monkeypatch):
    from wxbot.wechat import chat_window as module
    chat,sent=make_chat(monkeypatch)
    clock=[0]
    task=chat.start_send('你好',clock=lambda:clock[0])
    task.step()
    monkeypatch.setattr(module.auto,'GetForegroundWindow',lambda:999)
    clock[0]=1
    assert task.step()=='blocked' and sent==['{Ctrl}v']
    assert task.edit.clipboard.data==task.edit.original_clipboard


def test_independent_sender_stops_if_input_focus_or_title_changes(monkeypatch):
    chat,sent=make_chat(monkeypatch)
    task=chat.start_send('你好')
    task.edit.HasKeyboardFocus=False
    assert task.step()=='blocked' and sent==[]
    task.edit.HasKeyboardFocus=True
    task=chat.start_send('你好')
    task.win.Name='other recipient'
    assert task.step()=='blocked' and sent==[]


def test_post_close_clipboard_version_does_not_block_an_unchanged_batch(monkeypatch):
    import test_clipboard as fixtures
    monkeypatch.setattr(fixtures,'FakeClipboard',fixtures.DeferredClipboard)
    chat,sent=make_chat(monkeypatch)
    clock=[0]
    task=chat.start_send('你好',clock=lambda:clock[0])
    assert task.step()=='typing' and sent==['{Ctrl}v']
    clock[0]=1
    assert task.step()=='submitted' and sent==['{Ctrl}v','{Enter}']
    assert task.edit.clipboard.data==task.edit.original_clipboard
