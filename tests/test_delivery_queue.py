from types import SimpleNamespace

from wxbot.delivery import DeliveryPump
from wxbot.queue_store import QueueStore
from wxbot.wechat.chat_window import Message


class Chat:
    def __init__(self, *, bubble=True):
        self.messages = [Message("other", "问题")]
        self.bubble = bubble
        self.starts = 0
        self.remembered = []

    def available(self):
        return True

    def read_messages(self, **kwargs):
        return list(self.messages)

    def read_from_window(self, root, **kwargs):
        return self.read_messages()

    def target_is_current(self, root):
        return True

    def remember_sent(self, text):
        self.remembered.append(text)

    def start_send(self, text, **kwargs):
        self.starts += 1
        task = SimpleNamespace(win=object(), state="typing", enter_attempted=False, error="", steps=0)
        def step():
            task.steps += 1
            if task.steps == 2:
                if getattr(task, "before_enter", None):
                    task.before_enter()
                task.enter_attempted, task.state = True, "submitted"
                if self.bubble:
                    self.messages.append(Message("self", text))
            return task.state
        task.step = step
        return task


def pump(store, chat, clock):
    return DeliveryPump(store, lambda name: chat, lambda name: True, lambda: None,
                        clock=lambda: clock[0], monotonic=lambda: clock[0], timeout=5)


def test_outbound_waiter_only_finishes_after_new_self_bubble_is_confirmed():
    store, chat, clock = QueueStore(":memory:"), Chat(), [0]
    sender = pump(store, chat, clock)
    finished = []
    record_id = sender.enqueue(SimpleNamespace(contact="A", text="回答", finish=lambda *args: finished.append(args)))
    assert finished == []
    sender.tick()
    sender.tick()
    assert store.get_delivery(record_id)["state"] == "sending"
    assert finished == []
    sender.tick()
    assert store.get_delivery(record_id)["state"] == "sent"
    assert finished == [(True, "sent")]
    assert chat.remembered == ["回答"]


def test_unconfirmed_enter_stays_uncertain_and_is_not_automatically_replayed():
    store, chat, clock = QueueStore(":memory:"), Chat(bubble=False), [0]
    record_id = store.enqueue_delivery("A", "回答", now=0)
    sender = pump(store, chat, clock)
    sender.tick(); sender.tick(); sender.tick()
    assert store.get_delivery(record_id)["state"] == "confirming"
    clock[0] = 6
    sender.tick(); sender.tick()
    assert store.get_delivery(record_id)["state"] == "uncertain"
    assert chat.starts == 1


def test_recovery_can_confirm_existing_bubble_without_typing_or_enter_again():
    store, chat, clock = QueueStore(":memory:"), Chat(), [0]
    record_id = store.enqueue_delivery("A", "回答", now=0)
    store.claim_delivery(now=0)
    store.save_baseline(record_id, [{"sender": "other", "text": "问题"}])
    store.recover()
    chat.messages.append(Message("self", "回答"))
    sender = pump(store, chat, clock)
    sender.reconcile()
    assert store.get_delivery(record_id)["state"] == "sent"
    assert chat.starts == 0


def test_confirmation_read_errors_eventually_release_ui_for_other_conversations():
    store, chat, clock = QueueStore(":memory:"), Chat(bubble=False), [0]
    record_id = store.enqueue_delivery("A", "回答", now=0)
    sender = pump(store, chat, clock)
    sender.tick(); sender.tick(); sender.tick()
    def broken_read(*args, **kwargs):
        raise RuntimeError("UIA unavailable")
    chat.read_from_window = broken_read
    clock[0] = 6
    sender.tick()
    assert store.get_delivery(record_id)["state"] == "uncertain"
    assert not sender.busy


def test_recovery_preserves_unread_before_selecting_and_checking_target():
    store, chat, clock = QueueStore(":memory:"), Chat(), [0]
    record_id = store.enqueue_delivery("A", "回答", now=0)
    store.claim_delivery(now=0)
    store.save_baseline(record_id, [{"sender": "other", "text": "问题"}])
    store.recover()
    order = []
    sender = DeliveryPump(store, lambda name: chat,
                          lambda name: order.append("capture") or True,
                          lambda: order.append("discover"))
    sender.reconcile()
    assert order == ["discover", "capture"]


def test_model_reply_preserves_original_conversation_type_before_selecting_target():
    from wxbot.queue_store import Incoming
    store, chat, clock = QueueStore(":memory:"), Chat(), [0]
    store.capture("A", [], [Incoming("私聊问题")], group_mode=False, now=0)
    store.prepare(quiet=0, max_wait=10, prefix="/", now=0)
    batch = store.claim_batch(now=0)
    store.finish_batch(batch.id, "私聊回复", now=0)
    seen = []
    def capture_target(name):
        seen.append(chat.expected_group)
        return False  # 检测到不匹配时不会输入。
    sender = DeliveryPump(store, lambda name: chat, capture_target, lambda: None)
    sender.tick()
    assert seen == [False]
    assert chat.starts == 0


def test_new_incoming_during_typing_refreshes_confirmation_anchor_and_releases_next_batch():
    from wxbot.queue_store import Incoming
    from wxbot.queue_worker import ModelWorker
    store, chat, clock = QueueStore(":memory:"), Chat(), [0]
    class Router:
        def handle_reply(self, *args, **kwargs):
            from wxbot.reply import Reply
            return Reply.from_text("回答")
    worker = ModelWorker(store, Router(), quiet=0, max_wait=10, clock=lambda: clock[0])
    store.capture("A", [], [Incoming("你好")], now=0)
    assert worker.process_once()
    sender = pump(store, chat, clock)
    sender.tick(); sender.tick()
    chat.messages = [Message("other", "新问题")]  # 新消息挤出旧的确认锚点。
    store.capture("A", [], [Incoming("新问题")], now=1)
    assert not worker.process_once()
    sender.tick()
    assert store.records("outbox")[0]["state"] == "sent"
    clock[0] = 2
    assert worker.process_once()
    assert len(store.records("batches")) == 2


def test_user_confirmed_actual_text_recovers_old_mismatched_reply_without_resending():
    store, chat, clock = QueueStore(":memory:"), Chat(), [0]
    record_id = store.enqueue_delivery("A", "你好，我在这里", now=0)
    store.claim_delivery(now=0)
    store.save_baseline(record_id, [{"sender": "other", "text": "问题"}])
    store.recover()
    store.record_submitted_text(record_id, "你好，，在这里", user_confirmed=True)
    chat.messages.append(Message("self", "你好，，在这里"))
    sender = pump(store, chat, clock)
    sender.reconcile()
    assert store.get_delivery(record_id)["state"] == "sent"
    assert store.get_delivery(record_id)["text"] == "你好，我在这里"
    assert chat.starts == 0
