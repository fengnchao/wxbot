"""Capture deferrals never advance inbox state or block independently verified sends."""
from types import SimpleNamespace

import pytest

from test_main_window import Chat, Desktop, Router, cfg
from wxbot.inbox import MainInbox
from wxbot.wechat.chat_window import Message, ReadDeferred
from wxbot.wechat.main_window import Conversation, MainWindow, Session


class DeliveryChat(Chat):
    """Synthetic UI boundary; real inbox, delivery pump and temporary queue state."""
    def __init__(self, messages):
        super().__init__('101', messages)
        self.starts = 0
        self.before_submit = lambda: None
        self.after_submit = lambda: None

    def start_send(self, text, **kwargs):
        self.starts += 1
        task = SimpleNamespace(win=object(), enter_attempted=False, error='')
        def step():
            self.before_submit()
            if task.before_enter() is False:
                return 'typing'
            task.enter_attempted = True
            self.messages.append(Message('self', text))
            self.after_submit()
            return 'submitted'
        task.step = step
        return task


def setup_inbox():
    chat = DeliveryChat([Message('other', '历史')])
    desktop = Desktop([chat], current=Conversation('101', False))
    inbox = MainInbox(cfg(), Router(), desktop=desktop, clock=lambda: 10, monotonic=lambda: 10)
    inbox.poll()
    return inbox, chat, desktop


def enqueue(inbox):
    return inbox.deliver(SimpleNamespace(contact='101', text='主动提醒', finish=lambda *args: None))


def send(inbox):
    inbox.delivery.tick()
    inbox.delivery.tick()


def test_unknown_unread_sender_does_not_block_send_or_consume_incoming_checkpoint():
    inbox, chat, desktop = setup_inbox()
    before = inbox.store.snapshots()
    chat.messages.append(Message('system', '新收到'))
    desktop.pending = [Session('101', 1)]
    record_id = enqueue(inbox)
    send(inbox)
    assert inbox.store.get_delivery(record_id)['state'] == 'sent'
    assert inbox.store.snapshots() == before
    assert inbox.store.pending_sessions()[0]['unread_count'] == 1
    assert not inbox.store.records('inbox')
    chat.messages[1] = Message('other', '新收到')
    desktop.pending = []
    inbox.monotonic = lambda: 12
    inbox.poll(allow_switch=True)
    inbox.poll(allow_switch=True)
    assert [row['text'] for row in inbox.store.records('inbox')] == ['新收到']
    assert inbox.store.pending_sessions() == []


@pytest.mark.parametrize('stage', ['before_submit', 'after_submit'])
def test_sender_deferral_during_delivery_keeps_verifiable_self_bubble_independent(stage):
    inbox, chat, desktop = setup_inbox()
    before = inbox.store.snapshots()
    setattr(chat, stage, lambda: chat.messages.append(Message('system', '稍后才读清的新消息')))
    record_id = enqueue(inbox)
    send(inbox)
    assert inbox.store.get_delivery(record_id)['state'] == 'sent'
    assert chat.starts == 1
    assert inbox.store.snapshots() == before
    assert not inbox.store.records('inbox')
    assert inbox.store.pending_sessions()[0]['contact'] == '101'
    chat.messages = [Message('other', message.text) if message.sender == 'system' else message
                     for message in chat.messages]
    inbox.monotonic = lambda: 12
    inbox._receive_one()
    inbox.poll()
    assert [row['text'] for row in inbox.store.records('inbox')] == ['稍后才读清的新消息']


def test_handoff_deferral_preserves_read_retry_and_allows_switch_to_another_chat():
    inbox, chat, desktop = setup_inbox()
    before = inbox.store.snapshots()
    chat.messages.append(Message('system', '无未读角标的新消息'))
    handoff = SimpleNamespace(before_switch=inbox._before_switch,
                              current_conversation=lambda root: Conversation('101', False))
    MainWindow._handoff(handoff, object(), '另一个聊天')
    assert inbox.store.snapshots() == before
    assert inbox.store.pending_sessions()[0]['unread_count'] == 0
    assert inbox.pending['101'] == Session('101')
    chat.messages[1] = Message('other', '无未读角标的新消息')
    inbox.monotonic = lambda: 12
    inbox._receive_one()
    inbox.poll()
    assert [row['text'] for row in inbox.store.records('inbox')] == ['无未读角标的新消息']


@pytest.mark.parametrize('read_number', [1, 2])
def test_unavailable_target_message_list_stops_before_typing(monkeypatch, read_number):
    inbox, chat, desktop = setup_inbox()
    reads = 0
    def read_messages(**kwargs):
        nonlocal reads
        reads += 1
        if reads == read_number:
            raise ReadDeferred('message_list_unavailable', '消息列表暂时不可读取')
        return list(chat.messages)
    monkeypatch.setattr(chat, 'read_messages', read_messages)
    record_id = enqueue(inbox)
    send(inbox)
    assert inbox.store.get_delivery(record_id)['state'] == 'blocked'
    assert chat.starts == 0
    assert all(message.sender != 'self' for message in chat.messages)


def test_non_capture_error_still_blocks_send(monkeypatch):
    inbox, chat, desktop = setup_inbox()
    def broken_capture(*args, **kwargs):
        raise RuntimeError('会话类型变化')
    monkeypatch.setattr(inbox, '_capture', broken_capture)
    record_id = enqueue(inbox)
    send(inbox)
    assert inbox.store.get_delivery(record_id)['state'] == 'blocked'
    assert chat.starts == 0


def test_poll_sender_deferral_does_not_starve_pending_delivery():
    inbox, chat, desktop = setup_inbox()
    before = inbox.store.snapshots()
    chat.messages.append(Message('system', '当前窗口新收到'))
    record_id = enqueue(inbox)
    inbox.tick()
    inbox.tick()
    assert inbox.store.get_delivery(record_id)['state'] == 'sent'
    assert inbox.store.snapshots() == before
    assert not inbox.store.records('inbox')
    assert inbox.store.pending_sessions()[0]['contact'] == '101'


def test_departing_message_list_unavailable_keeps_retry_without_blocking_handoff(monkeypatch):
    inbox, chat, desktop = setup_inbox()
    before = inbox.store.snapshots()
    def unavailable(root, **kwargs):
        raise ReadDeferred('message_list_unavailable', '消息列表暂时不可读取')
    monkeypatch.setattr(chat, 'read_from_window', unavailable)
    inbox._before_switch(Conversation('101', False), object())
    assert inbox.store.snapshots() == before
    assert inbox.store.pending_sessions()[0]['contact'] == '101'


def test_unavailable_target_never_treats_unknown_sender_as_permission_to_type(monkeypatch):
    inbox, chat, desktop = setup_inbox()
    chat.messages.append(Message('system', '新收到'))
    monkeypatch.setattr(chat, 'available', lambda **kwargs: False)
    record_id = enqueue(inbox)
    send(inbox)
    assert inbox.store.get_delivery(record_id)['state'] == 'blocked'
    assert chat.starts == 0
