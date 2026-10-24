"""Use the received session preview to learn group nicknames without sending WeChat messages."""
from types import SimpleNamespace

import pytest

from wxbot.inbox import MainInbox
from wxbot.queue_store import Incoming, QueueStore
from wxbot.reply import Reply
from wxbot.wechat.chat_window import Message
from wxbot.wechat.main_window import parse_session, preview_sender


KEY = "30438f8712345678"


def make_inbox(store, preview, *, group="测试群"):
    session = parse_session("session_item_" + group, f"{group}\n已置顶\n{preview}\n12:23\n")
    desktop = SimpleNamespace(sessions=lambda **kw: [session])
    cfg = {"bot": {"mention_names": ["Bot"], "group_reply_chance": 0,
                   "reply_delay_min": 0, "reply_delay_max": 0},
           "wechat": {}, "queue": {"quiet_seconds": 0, "max_wait_seconds": 10}}
    router = SimpleNamespace(handle_reply=lambda *a, **kw: Reply.from_text("收到"))
    inbox = MainInbox(cfg, router, desktop=desktop, store=store, clock=lambda: 0)
    inbox._discover()
    return inbox


def capture(inbox, text="@Bot 你好", *, group="测试群", key=KEY, name=None):
    message = Message("other", text, name or "成员-" + key[:8], key)
    inbox._capture(group, SimpleNamespace(group_mode=True), [message], fresh=[message])
    return message


def test_received_preview_maps_avatar_to_nickname_and_reply():
    store = QueueStore(":memory:")
    inbox = make_inbox(store, "我干嘛: @Bot 你好")
    capture(inbox)
    assert inbox.worker.process_once()
    assert store.records("outbox")[0]["text"] == "@我干嘛 收到"
    row = store.records("inbox")[0]
    assert row["member_key"] == KEY
    assert row["member_name"] == "我干嘛"
    assert "群聊发言人：我干嘛" in row["context"]


def test_mapping_survives_restart_and_is_scoped_to_group(tmp_path):
    path = tmp_path / "queue.db"
    store = QueueStore(path)
    capture(make_inbox(store, "群昵称: @Bot 你好"))
    store.close()
    store = QueueStore(path)
    try:
        inbox = make_inbox(store, "摘要已被截断…")
        capture(inbox, "@Bot 下一条")
        assert store.records("inbox")[-1]["member_name"] == "群昵称"
        capture(inbox, "@Bot 其他群", group="另一个群")
        assert store.records("inbox")[-1]["member_name"] == ""
    finally:
        store.close()


def test_mismatched_preview_does_not_learn_or_mention_placeholder():
    store = QueueStore(":memory:")
    inbox = make_inbox(store, "其他人: 别的消息")
    capture(inbox)
    inbox.worker.process_once()
    assert store.records("outbox")[0]["text"] == "收到"
    assert store.records("inbox")[0]["member_name"] == ""


def test_configured_name_takes_precedence_over_learned_nickname():
    store = QueueStore(":memory:")
    inbox = make_inbox(store, "自动昵称: @Bot 你好")
    capture(inbox, name="手动昵称")
    inbox.worker.process_once()
    assert store.records("outbox")[0]["text"] == "@手动昵称 收到"


def test_outgoing_tail_cannot_assign_old_incoming_avatar_to_new_preview():
    store = QueueStore(":memory:")
    inbox = make_inbox(store, "其他人: @Bot 你好")
    messages = [Message("other", "@Bot 你好", "成员-30438f87", KEY), Message("self", "回复")]
    inbox._capture("测试群", SimpleNamespace(group_mode=True), messages, fresh=messages[:1])
    assert store.records("inbox")[0]["member_name"] == ""


@pytest.mark.parametrize("preview,text,expected", [
    ("昵称: @Bot 你好", "@Bot\u2005你好", "昵称"),
    ("昵称：@Bot 你好", "@Bot 你好", "昵称"),
    ("昵称:后缀: @Bot 带:冒号", "@Bot 带:冒号", "昵称:后缀"),
    ("Nick  Name: @Bot 你好", "@Bot 你好", "Nick  Name"),
    ("昵称: @Bot 你好…", "@Bot 你好，完整正文", None),
    ("[草稿] 昵称: @Bot 你好", "@Bot 你好", None),
    ("我: @Bot 你好", "@Bot 你好", None),
    ("昵称: 不同消息", "@Bot 你好", None),
])
def test_preview_requires_complete_matching_body(preview, text, expected):
    assert preview_sender(preview, text) == expected


def test_learning_last_member_does_not_rename_other_members_in_same_batch():
    store = QueueStore(":memory:")
    inbox = make_inbox(store, "最后发言人: @Bot 第二条")
    messages = [Message("other", "@Bot 第一条", "成员-aaaaaaaa", "aaaaaaaa12345678"),
                Message("other", "@Bot 第二条", "成员-30438f87", KEY)]
    inbox._capture("测试群", SimpleNamespace(group_mode=True), messages, fresh=messages)
    assert [row["member_name"] for row in store.records("inbox")] == ["", "最后发言人"]


def test_preview_changing_during_read_cannot_rename_another_sender_with_same_body():
    store = QueueStore(":memory:")
    inbox = make_inbox(store, "甲: @Bot 你好")
    newer = parse_session("session_item_测试群", "测试群\n乙: @Bot 你好\n12:24\n")
    inbox.desktop.sessions = lambda **kw: [newer]
    capture(inbox)
    assert store.records("inbox")[0]["member_name"] == ""


def test_disappearing_session_cannot_reuse_an_old_preview():
    store = QueueStore(":memory:")
    inbox = make_inbox(store, "甲: @Bot 你好")
    inbox.desktop.sessions = lambda **kw: []
    inbox._discover()
    capture(inbox)
    assert store.records("inbox")[0]["member_name"] == ""


@pytest.mark.parametrize("nickname,expected", [("", "收到"), ("已识别昵称", "@已识别昵称 收到")])
def test_old_queued_placeholder_uses_learned_name_or_omits_mention(nickname, expected):
    store = QueueStore(":memory:")
    if nickname:
        store.remember_group_member("测试群", KEY, nickname, now=0)
    store.capture("测试群", [], [Incoming("你好", KEY, "", "成员-30438f87")], group_mode=True, now=0)
    store.prepare(quiet=0, max_wait=10, prefix="/", now=0)
    batch = store.claim_batch(now=0)
    store.finish_batch_parts(batch.id, ("收到",), now=0)
    assert store.records("outbox")[0]["text"] == expected
