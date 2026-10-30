import threading

from wxbot.queue_store import Incoming, QueueStore
from wxbot.queue_worker import ModelWorker
from wxbot.reply import Reply


def test_model_wait_does_not_hold_store_or_block_other_users_capture():
    store = QueueStore(":memory:")
    store.capture("A", [], [Incoming("问题A")], now=0)
    started, release, b_called = threading.Event(), threading.Event(), threading.Event()
    calls = []
    class Router:
        def handle_reply(self, contact, text, *, context="", request_id=None, member_key="", member_name=""):
            calls.append(contact)
            if contact == "A":
                started.set()
                assert release.wait(3)
            else:
                b_called.set()
            return Reply.from_text("回答" + contact)
    worker = ModelWorker(store, Router(), quiet=0, max_wait=10, clock=lambda: 10)
    worker.start()
    try:
        assert started.wait(2)
        store.capture("B", [], [Incoming("问题B")], now=1)
        assert len(store.records("inbox")) == 2
        release.set()
        assert b_called.wait(2)
        assert calls == ["A", "B"]
    finally:
        release.set()
        worker.stop()


def test_model_exception_is_preserved_and_not_automatically_replayed():
    store = QueueStore(":memory:")
    store.capture("A", [], [Incoming("建提醒")], now=0)
    calls=[]
    class Router:
        def handle_reply(self, *args, **kwargs):
            calls.append(args)
            raise TimeoutError("结果未知")
    worker=ModelWorker(store, Router(), quiet=0, max_wait=10, clock=lambda: 1)
    assert worker.process_once()
    assert not worker.process_once()
    assert len(calls) == 1
    assert store.records("batches")[0]["state"] == "uncertain"
