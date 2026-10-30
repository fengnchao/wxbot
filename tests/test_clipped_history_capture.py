"""Read real capture logic against synthetic UI rows and pixels, never WeChat."""
from types import SimpleNamespace

import pytest
from PIL import Image

from test_main_window import Desktop, Router, cfg
from wxbot.inbox import MainInbox
from wxbot.wechat.chat_window import ChatWindow, Message, ReadDeferred
from wxbot.wechat.main_window import Conversation, Session


def row(text, top, bottom, cls='mmui::ChatTextItemView'):
    return SimpleNamespace(
        Name=text, ClassName=cls,
        BoundingRectangle=SimpleNamespace(left=1471, top=top, right=1846, bottom=bottom),
    )


@pytest.fixture
def capture_ui(monkeypatch):
    import wxbot.wechat.chat_window as module

    rows = [row('顶部残缺历史', 386, 463), row('新消息一', 470, 550), row('新消息二', 560, 640)]
    chat = ChatWindow('鸭王集训营', {'message_list': {'automation_id': 'chat_message_list'},
                                   'text_item': {'class_name': 'mmui::ChatTextItemView'}},
                      group_mode=True)
    lst = SimpleNamespace(
        BoundingRectangle=SimpleNamespace(left=1471, top=413, right=1846, bottom=773),
        GetChildren=lambda: rows,
    )
    monkeypatch.setattr(chat, '_message_list', lambda: lst)
    monkeypatch.setattr(chat, '_find', lambda *args: lst)
    monkeypatch.setattr(chat, '_runtime_avatar', lambda *args: None)

    def screenshot(*, bbox, all_screens):
        left, top, right, bottom = bbox
        image = Image.new('RGB', (right-left, bottom-top), (31, 31, 31))
        image.paste((200, 200, 200), (12, 2, 48, min(38, bottom-top)))
        return image

    monkeypatch.setattr(module.ImageGrab, 'grab', screenshot)
    desktop = Desktop([chat], [Session(chat.title, 8)])

    def available(**kwargs):
        desktop.current = Conversation(chat.title, True)
        desktop.pending = []  # Selecting the session acknowledges its real UI badge.
        return True

    monkeypatch.setattr(chat, 'available', available)
    return chat, rows, desktop


@pytest.mark.parametrize('previous', [None, [Message('other', '已滚出加载区的旧快照')]])
def test_clipped_history_does_not_block_visible_unread_or_replay_it(capture_ui, previous):
    chat, rows, desktop = capture_ui
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    if previous is not None:
        inbox._capture(chat.title, chat, previous)

    inbox.poll(allow_switch=True)

    assert [item['text'] for item in inbox.store.records('inbox')] == ['新消息一', '新消息二']
    assert inbox.store.pending_sessions() == []
    assert [message.text for message in inbox.snapshots[chat.title] if message.sender == 'other'] == [
        '新消息一', '新消息二',
    ]
    inbox.poll(allow_switch=True)
    assert len(inbox.store.records('inbox')) == 2


@pytest.mark.parametrize('strict_sender', [False, True])
def test_message_reads_keep_clipped_text_only_as_overlap_anchor(capture_ui, strict_sender):
    chat, rows, desktop = capture_ui
    messages = chat.read_messages(strict_sender=strict_sender)
    assert [message.text for message in messages] == ['顶部残缺历史', '新消息一', '新消息二']
    assert [message.text for message in messages if message.sender == 'other'] == [
        '新消息一', '新消息二',
    ]
    assert [message.text for message in chat.read_bundle(8)[1]] == ['新消息一', '新消息二']


def test_passive_capture_keeps_overlap_when_previous_tail_is_now_clipped(capture_ui):
    chat, rows, desktop = capture_ui
    desktop.pending = []
    desktop.current = Conversation(chat.title, True)
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox._capture(chat.title, chat, [Message('other', '顶部残缺历史')])

    inbox.poll()

    assert [item['text'] for item in inbox.store.records('inbox')] == ['新消息一', '新消息二']
    inbox.poll()
    assert len(inbox.store.records('inbox')) == 2


def test_only_clipped_rows_keep_unread_task_until_messages_are_visible(capture_ui):
    chat, rows, desktop = capture_ui
    rows[:] = rows[:1]
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox.poll(allow_switch=True)
    assert inbox.store.snapshots() == {}
    assert inbox.store.pending_sessions()[0]['unread_count'] == 8
    assert inbox.store.records('inbox') == []
    with pytest.raises(ReadDeferred):
        chat.read_bundle(8)


@pytest.mark.parametrize('capture_path', ['handoff', 'delivery'])
def test_other_capture_paths_preserve_unread_task_when_only_history_is_clipped(capture_ui, capture_path):
    chat, rows, desktop = capture_ui
    rows[:] = rows[:1]
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox._capture(chat.title, chat, [Message('other', '已采集的旧消息')])
    before = inbox.store.snapshots()
    inbox.poll(allow_switch=True)

    if capture_path == 'handoff':
        inbox._before_switch(Conversation(chat.title, True), object())
    else:
        inbox._capture_for_delivery(chat.title, chat, chat.read_messages())

    assert inbox.store.snapshots() == before
    assert inbox.store.pending_sessions()[0]['unread_count'] == 8
    assert inbox.store.records('inbox') == []


def test_bottom_clipped_new_message_still_preserves_unread_checkpoint(capture_ui):
    chat, rows, desktop = capture_ui
    rows[:] = [row('尚未完整显示的新消息', 750, 830)]
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox.poll(allow_switch=True)
    assert inbox.store.snapshots() == {}
    assert inbox.store.pending_sessions()[0]['unread_count'] == 8
    assert inbox.store.records('inbox') == []


def test_verified_bundle_consumes_image_unread_without_incoming_text(capture_ui, monkeypatch):
    chat, rows, desktop = capture_ui
    rows[:] = [rows[0], row('自己旧消息', 470, 530), row('自己新消息', 540, 600),
               row('图片', 610, 690, 'mmui::ChatImageItemView')]
    monkeypatch.setattr(chat, '_classify', lambda item, *args, **kwargs:
                        'self' if item.Name.startswith('自己') else 'other')
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox._capture(chat.title, chat, [Message('self', '自己旧消息')])

    inbox.poll(allow_switch=True)

    assert inbox.store.pending_sessions() == []
    assert inbox.store.records('inbox') == []
    assert [message.text for message in inbox.snapshots[chat.title]] == [
        '顶部残缺历史', '自己旧消息', '自己新消息',
    ]
