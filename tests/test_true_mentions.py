from types import SimpleNamespace
import sqlite3

import pytest

from wxbot.queue_store import Incoming, QueueStore
from test_typing import make_chat


def batch(store, *, group=True, avatar='avatar'):
    store.capture('群', [], [Incoming('你好', 'm1', '', '甲', avatar=avatar)], group_mode=group, now=0)
    store.prepare(quiet=0, max_wait=10, prefix='/', now=0)
    return store.claim_batch(now=0)


def test_body_and_first_part_mention_are_separate_and_avatar_survives():
    store = QueueStore(':memory:')
    item = batch(store)
    assert item.avatar == 'avatar'
    store.finish_batch_parts(item.id, ('第一句', '第二句'), now=0, mention_name='甲')
    rows = store.records('outbox')
    assert [(r['text'], r['mention_name']) for r in rows] == [('第一句', '甲'), ('第二句', '')]
    assert store.claim_delivery(now=0).mention_name == '甲'


def test_dm_and_unverified_member_never_infer_mention_from_name_or_body():
    for group in (False, True):
        store = QueueStore(':memory:')
        item = batch(store, group=group)
        store.finish_batch_parts(item.id, ('@甲 正文',), now=0)
        row = store.records('outbox')[0]
        assert row['text'] == '@甲 正文' and row['mention_name'] == ''


def mention_chat(monkeypatch, names=('甲',), *, rich=True):
    chat, sent = make_chat(monkeypatch)
    chat.group_mode = True
    chat.wcfg['mention'] = {'panel': {'name': '选择提醒的人'}, 'item': {'control_type': 'ListItemControl'}}
    edit = chat._find(None, None)
    edit.objects = []
    edit.GetTextPattern = lambda: SimpleNamespace(DocumentRange=SimpleNamespace(
        GetText=lambda: edit.value, GetChildren=lambda: edit.objects))
    def choose():
        edit.value = '\ufffc ' if rich else '@甲 '
        edit.objects = [SimpleNamespace(Name='甲', GetRuntimeId=lambda: [1, 99])] if rich else []
    candidates = [SimpleNamespace(Name=name, ControlTypeName='ListItemControl',
                                  GetChildren=lambda: [], Click=lambda **kw: choose()) for name in names]
    panel = SimpleNamespace(Name='选择提醒的人', GetChildren=lambda: candidates)
    monkeypatch.setattr(chat, '_find', lambda win, spec: panel if spec.get('name') == panel.Name else edit)
    from wxbot.wechat import mentions
    original = mentions.auto.SendKeys
    edit.selection = False
    def send(keys, **kwargs):
        if keys == '{Esc}':
            sent.append(keys)
        elif keys == '{Ctrl}a':
            sent.append(keys); edit.selection = True
        elif keys == '{Backspace}':
            sent.append(keys)
            if edit.selection:
                edit.value = ''; edit.objects = []; edit.selection = False
        else:
            original(keys, **kwargs)
    monkeypatch.setattr(mentions.auto,'SendKeys',send)
    return chat, sent, edit


def advance(task, clock):
    for _ in range(20):
        result = task.step()
        clock[0] += 1
        if result != 'typing':
            return result
    return task.state


def test_real_mention_picker_selects_object_then_types_and_submits_visible_text(monkeypatch):
    chat, sent, edit = mention_chat(monkeypatch)
    clock = [0]
    task = chat.start_send('正文', mention_name='甲', clock=lambda: clock[0])
    assert advance(task, clock) == 'submitted'
    assert task.mention_verified is True
    assert task.submitted_text == '@甲 正文'
    assert sent.count('{Enter}') == 1
    assert edit.pasted == ['正文']


@pytest.mark.parametrize('names', [(), ('甲', '甲'), ('甲','甲乙'), ('甲','')])
def test_missing_or_ambiguous_picker_sends_body_without_literal_at(monkeypatch, names):
    chat, sent, edit = mention_chat(monkeypatch, names=names)
    clock = [0]
    task = chat.start_send('正文', mention_name='甲', clock=lambda: clock[0])
    assert advance(task, clock) == 'submitted'
    assert not task.mention_verified and task.submitted_text == '正文'
    assert sent.count('{Enter}') == 1 and edit.pasted == ['正文']
    assert task.failure_details.get('mention_fallback')


def test_unverified_literal_selection_is_removed_before_body_only_submission(monkeypatch):
    chat, sent, edit = mention_chat(monkeypatch, rich=False)
    clock = [0]
    task = chat.start_send('正文', mention_name='甲', clock=lambda: clock[0])
    assert advance(task, clock) == 'submitted'
    assert not task.mention_verified and task.submitted_text == '正文'


def test_unreadable_rich_object_is_not_cleared_as_if_it_were_owned_literal_text(monkeypatch):
    chat,sent,edit=mention_chat(monkeypatch,rich=False)
    clock=[0]
    task=chat.start_send('正文',mention_name='甲',clock=lambda:clock[0])
    task.step(); task.step(); clock[0]=1; task.step()
    edit.value='\ufffc '
    assert advance(task,clock)=='blocked'
    assert edit.value=='\ufffc ' and '{Enter}' not in sent and not edit.pasted


def test_replaced_mention_object_or_focus_change_prevents_enter(monkeypatch):
    chat, sent, edit = mention_chat(monkeypatch)
    clock = [0]
    task = chat.start_send('正文', mention_name='甲', clock=lambda: clock[0])
    for _ in range(10):
        task.step(); clock[0] += 1
        if edit.pasted:
            break
    edit.objects = [SimpleNamespace(Name='甲', GetRuntimeId=lambda: [1, 100])]
    assert advance(task, clock) == 'blocked'
    assert '{Enter}' not in sent


def test_migration_backs_up_old_queue_and_blocks_legacy_prefix_without_binding(tmp_path):
    path = tmp_path / 'queue.db'
    store = QueueStore(path)
    item = batch(store)
    store.finish_batch_parts(item.id, ('原文',), now=0)
    store._db.execute("UPDATE outbox SET text='@甲 原文'")
    store._db.execute('PRAGMA user_version=8'); store._db.commit(); store.close()
    reopened = QueueStore(path)
    row = reopened.records('outbox')[0]
    assert row['text'] == '@甲 原文' and row['state'] == 'blocked' and row['manual_required'] == 1
    backups = list(tmp_path.glob('queue.db.backup-*'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 8
    reopened.close()


def test_runtime_avatar_uses_tight_crop_and_shared_normalization(monkeypatch):
    import base64
    from io import BytesIO
    from PIL import Image
    from wxbot.wechat import chat_window as module
    from common.avatar_identity import normalize_avatar
    chat = module.ChatWindow('群', {}, group_mode=True)
    monkeypatch.setattr(chat, '_avatar_scale', lambda: 1.5)
    bbox = []
    image = Image.new('RGB', (54, 54))
    for x in range(54):
        for y in range(54):
            image.putpixel((x, y), ((x * 17) % 255, (y * 13) % 255, (x * y) % 255))
    monkeypatch.setattr(module.ImageGrab, 'grab', lambda **kw: (bbox.append(kw['bbox']), image)[1])
    rect = SimpleNamespace(left=100, right=700, top=200, bottom=400)
    listing = SimpleNamespace(left=100, right=700, top=100, bottom=800)
    result = chat._runtime_avatar(SimpleNamespace(BoundingRectangle=rect), listing)
    assert bbox == [(118, 200, 172, 254)]
    stream = BytesIO(); image.save(stream, format='PNG')
    assert result == normalize_avatar(stream.getvalue())
    assert Image.open(BytesIO(base64.b64decode(result['image']))).size == (36, 36)


def test_clipped_avatar_fails_closed_without_using_configured_hash(monkeypatch):
    from wxbot.wechat import chat_window as module
    chat = module.ChatWindow('群', {'group_sender': {'member_names': {'1234': '甲'}}}, group_mode=True)
    monkeypatch.setattr(chat, '_avatar_scale', lambda: 1)
    rect = SimpleNamespace(left=100, right=700, top=200, bottom=220)
    listing = SimpleNamespace(left=100, right=700, top=100, bottom=800)
    monkeypatch.setattr(module.ImageGrab, 'grab', lambda **kw: pytest.fail('clipped avatar must not be sampled'))
    assert chat._runtime_avatar(SimpleNamespace(BoundingRectangle=rect), listing) is None


def test_batch_sticker_keeps_parent_pending_until_confirmed_and_prevents_overtake():
    store = QueueStore(':memory:')
    item = batch(store)
    store.finish_batch_sticker(item.id, now=0)
    row = store.records('outbox')[0]
    assert row['batch_id'] == item.id and row['kind'] == 'emoji'
    assert store.get_batch(item.id)['state'] == 'waiting_delivery'
    store.capture('群', [], [Incoming('下一条')], group_mode=True, now=1)
    assert store.prepare(quiet=0, max_wait=10, prefix='/', now=1) == 0
    delivery = store.claim_delivery(now=1)
    store.finish_delivery(delivery.id, 'sent', now=2)
    assert store.get_batch(item.id)['state'] == 'done'
    assert store.prepare(quiet=0, max_wait=10, prefix='/', now=2) == 1


def test_mention_focus_loss_during_selection_preserves_draft_without_enter(monkeypatch):
    chat, sent, edit = mention_chat(monkeypatch)
    clock = [0]
    task = chat.start_send('正文', mention_name='甲', clock=lambda: clock[0])
    task.step()
    edit.HasKeyboardFocus = False
    assert task.step() == 'blocked'
    assert sent == ['@'] and edit.value == '@'


def test_migration_never_rewrites_started_or_uncertain_prefix_rows(tmp_path):
    path = tmp_path / 'queue.db'
    store = QueueStore(path)
    item = batch(store)
    store.finish_batch_parts(item.id, ('原文',), now=0)
    store._db.execute("UPDATE outbox SET text='@甲 原文',state='uncertain',submitted_text='@甲 原文',submitted_at=1")
    store._db.execute('PRAGMA user_version=8'); store._db.commit()
    before = store.records('outbox')[0]
    store.close()
    reopened = QueueStore(path)
    assert reopened.records('outbox')[0] == before
    reopened.close()


def test_owned_new_popup_discovery_requires_process_and_owner_identity(monkeypatch):
    from wxbot.wechat import mentions
    chat, sent, edit = mention_chat(monkeypatch)
    chat.wcfg.pop('mention')
    root = chat._window(); root.ProcessId = 7
    target = SimpleNamespace(Name='甲', ControlTypeName='ListItemControl', GetChildren=lambda: [],
        Click=lambda **kw: (setattr(edit, 'value', '\ufffc '), setattr(edit, 'objects',
            [SimpleNamespace(Name='甲', GetRuntimeId=lambda: [1, 99])])))
    popup = SimpleNamespace(NativeWindowHandle=456, ProcessId=7, GetChildren=lambda: [target])
    existing = SimpleNamespace(NativeWindowHandle=500, ProcessId=7, GetChildren=lambda: [target])
    stranger = SimpleNamespace(NativeWindowHandle=600, ProcessId=8, GetChildren=lambda: [target])
    calls = [0]
    def windows():
        calls[0] += 1
        return [existing] if calls[0] == 1 else [existing, stranger, popup]
    monkeypatch.setattr(mentions, 'top_level_windows', windows)
    monkeypatch.setattr(mentions, 'window_owner', lambda hwnd: 123)
    clock = [0]
    task = chat.start_send('正文', mention_name='甲', clock=lambda: clock[0])
    assert advance(task, clock) == 'submitted'
    assert task.mention_verified and sent.count('{Enter}') == 1


def test_new_popup_with_wrong_owner_is_ignored_and_plain_body_is_sent(monkeypatch):
    from wxbot.wechat import mentions
    chat, sent, edit = mention_chat(monkeypatch)
    chat.wcfg.pop('mention')
    chat._window().ProcessId = 7
    popup = SimpleNamespace(NativeWindowHandle=456, ProcessId=7, GetChildren=lambda: pytest.fail('wrong-owner popup must not be inspected'))
    monkeypatch.setattr(mentions, 'top_level_windows', lambda: [popup] if sent else [])
    monkeypatch.setattr(mentions, 'window_owner', lambda hwnd: 999)
    clock = [0]
    task = chat.start_send('正文', mention_name='甲', clock=lambda: clock[0])
    assert advance(task, clock) == 'submitted'
    assert not task.mention_verified and task.submitted_text == '正文'
    assert edit.pasted == ['正文']


def test_filter_is_typed_even_when_picker_is_not_discoverable(monkeypatch):
    chat,sent,edit=mention_chat(monkeypatch)
    monkeypatch.setattr(chat,'_find',lambda win,spec: None if spec.get('name') else edit)
    clock=[0]
    task=chat.start_send('正文',mention_name='甲',clock=lambda:clock[0])
    assert task.step()=='typing'
    assert task.step()=='typing'
    assert sent[:2]==['@','甲']
    assert advance(task,clock)=='submitted' and task.submitted_text=='正文'


def test_unreadable_picker_control_falls_back_without_retrying_a_click(monkeypatch):
    chat,sent,edit=mention_chat(monkeypatch)
    def find(win,spec):
        if spec.get('name'):
            raise RuntimeError('stale UIA picker')
        return edit
    monkeypatch.setattr(chat,'_find',find)
    clock=[0]
    task=chat.start_send('正文',mention_name='甲',clock=lambda:clock[0])
    assert advance(task,clock)=='submitted' and task.submitted_text=='正文'
    assert not task.mention_verified


def test_fallback_does_not_erase_user_modified_draft(monkeypatch):
    chat,sent,edit=mention_chat(monkeypatch,names=('甲','甲'))
    clock=[0]
    task=chat.start_send('正文',mention_name='甲',clock=lambda:clock[0])
    task.step(); task.step(); task.step()
    edit.value+='用户输入'
    assert advance(task,clock)=='blocked'
    assert edit.value.endswith('用户输入') and '{Enter}' not in sent


def test_fallback_cleanup_failure_blocks_body_paste_and_enter(monkeypatch):
    from wxbot.wechat import mentions
    chat,sent,edit=mention_chat(monkeypatch,names=())
    original=mentions.auto.SendKeys
    monkeypatch.setattr(mentions.auto,'SendKeys',lambda keys,**kw: None if keys=='{Backspace}' else original(keys,**kw))
    clock=[0]
    task=chat.start_send('正文',mention_name='甲',clock=lambda:clock[0])
    assert advance(task,clock)=='blocked'
    assert '{Enter}' not in sent and not edit.pasted


def test_inline_new_picker_is_discovered_without_matching_existing_chat_lists(monkeypatch):
    from wxbot.wechat import mentions
    chat,sent,edit=mention_chat(monkeypatch)
    chat.wcfg.pop('mention')
    root=chat._window()
    def chosen(**kwargs):
        edit.value='\ufffc '
        edit.objects=[SimpleNamespace(Name='甲',GetRuntimeId=lambda:[1,99])]
    candidate=SimpleNamespace(Name='甲',ControlTypeName='ListItemControl',GetChildren=lambda:[],Click=chosen)
    picker=SimpleNamespace(ControlTypeName='ListControl',AutomationId='mention_members',
                          GetRuntimeId=lambda:[20],GetChildren=lambda:[candidate])
    previous=SimpleNamespace(ControlTypeName='ListControl',AutomationId='session_list',
                             GetRuntimeId=lambda:[10],GetChildren=lambda:[])
    nested=picker
    for _ in range(20):
        child=nested
        nested=SimpleNamespace(ControlTypeName='CustomControl',GetChildren=lambda child=child:[child])
    root.GetChildren=lambda:[previous]+([nested] if sent else [])
    monkeypatch.setattr(mentions,'top_level_windows',lambda:[])
    clock=[0]
    task=chat.start_send('正文',mention_name='甲',clock=lambda:clock[0])
    assert advance(task,clock)=='submitted'
    assert task.mention_verified and task.submitted_text=='@甲 正文'


def test_focus_loss_during_fallback_does_not_clear_or_send(monkeypatch):
    chat,sent,edit=mention_chat(monkeypatch,names=())
    clock=[0]
    task=chat.start_send('正文',mention_name='甲',clock=lambda:clock[0])
    for _ in range(8):
        task.step(); clock[0]+=1
        if task._mention.phase=='mention_fallback_select':
            break
    edit.HasKeyboardFocus=False
    assert advance(task,clock)=='blocked'
    assert edit.value=='@甲' and '{Backspace}' not in sent and '{Enter}' not in sent


def test_mention_identity_rechecked_after_clipboard_acquisition_before_paste(monkeypatch):
    from wxbot.wechat import typing as module
    chat, sent, edit = mention_chat(monkeypatch)
    original = module.ClipboardLease
    def lease(text):
        result = original(text)
        edit.objects = [SimpleNamespace(Name='甲', GetRuntimeId=lambda: [1, 100])]
        return result
    monkeypatch.setattr(module, 'ClipboardLease', lease)
    clock = [0]
    task = chat.start_send('正文', mention_name='甲', clock=lambda: clock[0])
    assert advance(task, clock) == 'blocked'
    assert edit.pasted == [] and '{Enter}' not in sent


def test_batch_persists_reason_from_highest_priority_reply_mode():
    store = QueueStore(':memory:')
    store.capture('群', [], [Incoming('普通', 'm1', reply_mode='none', reply_reason='cooldown'),
                             Incoming('请求', 'm1', reply_mode='text', reply_reason='direct')],
                  group_mode=True, now=0)
    store.prepare(quiet=0, max_wait=10, prefix='/', now=0)
    item = store.claim_batch(now=0)
    assert item.reply_reason == 'direct'
    assert store.records('inbox')[0]['reply_reason'] == 'cooldown'
    assert store.records('batches')[0]['reply_reason'] == 'direct'


def test_delivery_success_records_object_and_bubble_evidence_without_body():
    store = QueueStore(':memory:')
    item = batch(store)
    store.finish_batch_parts(item.id, ('敏感正文',), now=0, mention_name='甲')
    delivery = store.claim_delivery(now=0)
    store.finish_delivery(delivery.id, 'sent', now=1, details={
        'mention_verified': True, 'bubble_verified': True, 'body': '敏感正文'})
    event = store.delivery_events()[0]
    assert event['state'] == 'sent'
    assert event['details'] == {'mention_verified': True, 'bubble_verified': True}


def test_avatar_dpi_probe_never_selects_or_activates_a_chat(monkeypatch):
    import ctypes
    from wxbot.wechat import chat_window as module
    chat = module.ChatWindow('群', {})
    monkeypatch.setattr(chat, '_window', lambda: pytest.fail('avatar sampling must not select a chat'))
    monkeypatch.setattr(module.auto, 'GetForegroundWindow', lambda: 123)
    def dpi(hwnd):
        assert hwnd == 123
        return 144
    monkeypatch.setattr(ctypes.windll.user32, 'GetDpiForWindow', dpi)
    assert chat._avatar_scale() == 1.5


def test_rich_mention_keeps_wechat_unicode_separator_for_bubble_confirmation(monkeypatch):
    chat, sent, edit = mention_chat(monkeypatch)
    clock = [0]
    task = chat.start_send('正文', mention_name='甲', clock=lambda: clock[0])
    task.step(); task.step(); clock[0]=1; task.step()
    edit.value = '\ufffc\u2005'
    assert advance(task, clock) == 'submitted'
    assert task.submitted_text == '@甲\u2005正文'
