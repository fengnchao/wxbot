import sqlite3

import pytest

from wxbot.queue_store import Incoming, QueueStore


def capture(store, contact, text, at, *, member="", context="", snapshot=None):
    return store.capture(contact, snapshot or [], [Incoming(text, member, context)],
                         group_mode=bool(member), now=at)


def prepare(store, at):
    return store.prepare(quiet=3, max_wait=10, prefix="/", now=at)


def test_a_b_interleaving_buffers_independently_and_ready_user_goes_first():
    store = QueueStore(":memory:")
    capture(store, "A", "你好", 0)
    capture(store, "A", "我的问题", 1)
    capture(store, "B", "天气", 2)
    capture(store, "A", "补充条件", 3)
    assert prepare(store, 4) == 0
    assert prepare(store, 5) == 1
    b = store.claim_batch(now=5)
    assert (b.contact, b.text) == ("B", "天气")
    assert prepare(store, 6) == 1
    a = store.claim_batch(now=6)
    assert (a.contact, a.text) == ("A", "你好\n我的问题\n补充条件")


def test_continuous_messages_are_cut_at_maximum_wait():
    store = QueueStore(":memory:")
    for at in range(0, 15, 2):
        capture(store, "A", str(at), at)
    prepare(store, 14)
    batch = store.claim_batch(now=14)
    assert batch.text.splitlines() == [str(at) for at in range(0, 11, 2)]
    assert len([r for r in store.records("inbox") if not r["batch_id"]]) == 2


def test_same_conversation_waits_for_delivery_and_does_not_jump_other_ready_users():
    store = QueueStore(":memory:")
    capture(store, "A", "第一批", 0)
    prepare(store, 3)
    a = store.claim_batch(now=3)
    capture(store, "A", "第二批", 4)
    capture(store, "B", "B的问题", 5)
    store.finish_batch(a.id, "第一批回答", now=6)
    prepare(store, 8)
    assert len(store.records("batches")) == 2
    delivery = store.claim_delivery(now=8)
    store.finish_delivery(delivery.id, "sent", now=9)
    prepare(store, 9)
    assert store.claim_batch(now=9).contact == "B"


def test_commands_and_group_members_form_separate_ordered_batches():
    store = QueueStore(":memory:")
    capture(store, "群", "甲的问题", 0, member="甲", context="甲身份")
    capture(store, "群", "乙的问题", 1, member="乙", context="乙身份")
    capture(store, "群", "/reset", 2, member="乙", context="乙身份")
    prepare(store, 2)
    first = store.claim_batch(now=2)
    assert (first.text, first.context) == ("甲的问题", "甲身份")
    store.finish_batch(first.id, None, now=2)
    prepare(store, 2)
    second = store.claim_batch(now=2)
    assert second.text == "乙的问题"
    store.finish_batch(second.id, None, now=2)
    prepare(store, 2)
    assert store.claim_batch(now=2).text == "/reset"


def test_repeated_identical_messages_get_distinct_local_ids():
    store = QueueStore(":memory:")
    capture(store, "A", "你好", 0)
    capture(store, "A", "你好", 1)
    assert len({r["id"] for r in store.records("inbox")}) == 2
    prepare(store, 4)
    assert store.claim_batch(now=4).text == "你好\n你好"


def test_message_and_snapshot_commit_atomically():
    store = QueueStore(":memory:")
    store.capture("A", [{"text": "原快照"}], [], now=0)
    with pytest.raises(sqlite3.IntegrityError):
        store.capture("A", [{"text": "新快照"}], [Incoming("有效"), Incoming(None)], now=1)
    assert store.snapshots()["A"][0] == [{"text": "原快照"}]
    assert store.records("inbox") == []


def test_restart_keeps_unread_task_and_snapshot(tmp_path):
    path = tmp_path / "queue.sqlite3"
    store = QueueStore(path)
    store.remember_session("A", 3, False, now=0)
    store.capture("B", [{"text": "锚点"}], [Incoming("新消息")], now=1)
    store.close()
    reopened = QueueStore(path)
    assert reopened.pending_sessions()[0]["contact"] == "A"
    assert reopened.snapshots()["B"][0] == [{"text": "锚点"}]
    assert reopened.records("inbox")[0]["text"] == "新消息"


def test_restart_does_not_replay_running_model_or_uncertain_send(tmp_path):
    path = tmp_path / "queue.sqlite3"
    store = QueueStore(path)
    capture(store, "A", "可能调用过工具", 0)
    prepare(store, 3)
    batch = store.claim_batch(now=3)
    pending_id = store.enqueue_delivery("B", "还没发送", now=3)
    sending = store.claim_delivery(now=3)
    store.close()
    reopened = QueueStore(path)
    reopened.recover()
    assert reopened.get_batch(batch.id)["state"] == "uncertain"
    assert reopened.get_delivery(sending.id)["state"] == "uncertain"
    assert reopened.claim_batch(now=10) is None
    assert reopened.claim_delivery(now=10) is None
    assert pending_id == sending.id


def test_silent_model_result_finishes_batch_without_outbox():
    store = QueueStore(":memory:")
    capture(store, "A", "不必回复", 0)
    prepare(store, 3)
    batch = store.claim_batch(now=3)
    store.finish_batch(batch.id, None, now=3)
    assert store.get_batch(batch.id)["state"] == "done"
    assert store.records("outbox") == []


def test_blocked_delivery_only_blocks_its_own_conversation():
    store = QueueStore(":memory:")
    a = store.enqueue_delivery("A", "A1", now=0)
    assert store.claim_delivery(now=0).id == a
    store.finish_delivery(a, "blocked", now=0)
    store.enqueue_delivery("A", "A2", now=1)
    b = store.enqueue_delivery("B", "B1", now=2)
    assert store.claim_delivery(now=3).id == b


def test_runtime_lock_rejects_second_ui_owner_but_allows_status_reader(tmp_path):
    first = QueueStore(tmp_path / "queue.sqlite3")
    second = QueueStore(tmp_path / "queue.sqlite3", access='readonly')
    try:
        first.acquire_runtime()
        assert second.counts()["unbatched"] == 0
        with pytest.raises(RuntimeError):
            second.acquire_runtime()
    finally:
        second.close()
        first.close()


def test_known_new_unread_blocks_flushing_incomplete_older_buffer():
    store = QueueStore(":memory:")
    capture(store, "A", "你好", 0)
    store.remember_session("A", 1, False, now=2)
    assert prepare(store, 4) == 0
    capture(store, "A", "我的问题", 4)
    assert prepare(store, 7) == 1
    assert store.claim_batch(now=7).text == "你好\n我的问题"


def test_old_database_migrates_submission_field_without_resetting_tasks(tmp_path):
    path = tmp_path / "queue.sqlite3"
    first = QueueStore(path)
    record_id = first.enqueue_delivery("A", "原始模型正文", now=0)
    first.close()
    with sqlite3.connect(path) as old:
        old.execute("ALTER TABLE outbox DROP COLUMN submitted_text")
    migrated = QueueStore(path)
    row = migrated.get_delivery(record_id)
    assert row["state"] == "pending"
    assert row["text"] == "原始模型正文"
    assert row["submitted_text"] is None
    migrated.close()


def test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker():
    store = QueueStore(":memory:")
    capture(store, "A", "你好", 0)
    prepare(store, 3)
    batch = store.claim_batch(now=3)
    store.finish_batch(batch.id, "原模型回复", now=3)
    record_id = store.claim_delivery(now=3).id
    store.recover()
    capture(store, "A", "第二个问题", 4)
    store.record_submitted_text(record_id, "实际已发送正文", user_confirmed=True)
    assert store.get_delivery(record_id)["state"] == "uncertain"
    assert store.get_batch(batch.id)["state"] == "uncertain"
    assert prepare(store, 10) == 0
    assert store.claim_delivery(now=10) is None
    with pytest.raises(ValueError):
        store.record_submitted_text(record_id, "未经用户确认的正文")
