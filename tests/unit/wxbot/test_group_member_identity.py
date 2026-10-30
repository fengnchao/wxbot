"""群聊成员区分：每成员独立会话/记忆、回复 @ 前缀、表情发送、member 透传。"""
from types import SimpleNamespace

import pytest
import requests

from wxbot.queue_store import Incoming, QueueStore, merge_reply_mode
from wxbot.queue_worker import ModelWorker
from wxbot.reply import Reply
from wxbot.processor.butler import ButlerProcessor


# ---------- butler：每成员独立 session / 记忆 ----------

def test_group_member_contact_derives_distinct_uid(make_home):
    home = make_home(contacts=[{"name": "群", "profile": "p", "uid": "g", "channel_type": "group"}])
    c0 = home.butler._contact("群", "group", "")
    c1 = home.butler._contact("群", "group", "m1")
    c2 = home.butler._contact("群", "group", "m2")
    assert c0.uid == "g"
    assert c1.uid == "g::m1"
    assert c2.uid == "g::m2"
    assert c1.key() != c2.key()
    # 私聊不按成员拆分
    assert home.butler._contact("群", "dm", "m1").uid == "g"


def test_group_handle_isolates_session_per_member(make_home):
    home = make_home(replies=["r1", "r2"], pending_items=[],
                     contacts=[{"name": "群", "profile": "p", "uid": "g", "channel_type": "group"}])
    home.butler.handle("群", "你好", channel_type="group", member_key="m1")
    home.butler.handle("群", "你好", channel_type="group", member_key="m2")
    assert [c["uid"] for c in home.hermes.calls] == ["g::m1", "g::m2"]


# ---------- queue_store：@ 前缀与表情发件 ----------

def test_finish_batch_parts_saves_explicit_mention_to_first_part_only():
    store = QueueStore(":memory:")
    store.capture("群", [], [Incoming("你好", "m1", "[群聊发言人：甲; member_id=m1]", "甲")],
                  group_mode=True, now=0)
    store.prepare(quiet=0, max_wait=10, prefix="/", now=0)
    batch = store.claim_batch(now=0)
    assert (batch.member_key, batch.member_name) == ("m1", "甲")
    store.finish_batch_parts(batch.id, ("第一句", "第二句"), now=0, mention_name='甲')
    assert [row["text"] for row in store.records("outbox")] == ["第一句", "第二句"]
    assert [row['mention_name'] for row in store.records('outbox')] == ['甲', '']


def test_dm_reply_has_no_mention_prefix():
    store = QueueStore(":memory:")
    store.capture("101", [], [Incoming("你好")], now=0)
    store.prepare(quiet=0, max_wait=10, prefix="/", now=0)
    batch = store.claim_batch(now=0)
    store.finish_batch_parts(batch.id, ("好",), now=0)
    assert store.records("outbox")[0]["text"] == "好"


def test_enqueue_sticker_creates_emoji_delivery():
    store = QueueStore(":memory:")
    sid = store.enqueue_sticker("群", now=0)
    delivery = store.claim_delivery(now=0)
    assert delivery.id == sid
    assert delivery.kind == "emoji"
    assert delivery.text == ""


# ---------- 透传 member 到模型/管家 ----------

def test_butler_processor_sends_member_fields(monkeypatch):
    calls = []

    def post(*args, **kw):
        calls.append(kw["json"])
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: {"reply": "ok", "meta": {"reply_complete": True}})

    monkeypatch.setattr(requests, "post", post)
    ButlerProcessor({}, raise_errors=True).handle_reply("群", "你好", member_key="m1", member_name="甲")
    assert calls[0]["channel_type"] == "group"
    assert calls[0]["member_key"] == "m1"
    assert calls[0]["member_name"] == "甲"


def test_queue_worker_passes_member_to_router():
    store = QueueStore(":memory:")
    store.capture("群", [], [Incoming("你好", "m1", "ctx", "甲")], group_mode=True, now=0)
    store.prepare(quiet=0, max_wait=10, prefix="/", now=0)
    seen = {}

    class Router:
        def handle_reply(self, contact, text, *, context="", request_id=None, member_key="", member_name=""):
            seen.update(contact=contact, member_key=member_key, member_name=member_name)
            return Reply.from_text("好")

    ModelWorker(store, Router(), quiet=0, max_wait=10, clock=lambda: 0).process_once()
    assert seen == {"contact": "群", "member_key": "m1", "member_name": "甲"}


# ---------- 表情面板发送 ----------

def test_emoji_panel_blocked_without_button(monkeypatch):
    from wxbot.wechat import emoji as emoji_module

    class Chat:
        title = "群"
        wcfg = {"emoji": {"button": {"name": "表情"}}}

        def _window(self):
            return SimpleNamespace(SetActive=lambda: None)

        def _find(self, win, key):
            return None

    assert emoji_module.EmojiPanel(Chat()).send(clock=lambda: 0.0, timeout=0.5) == "blocked"


def test_emoji_panel_clicks_random_item_and_confirms(monkeypatch):
    from wxbot.wechat import emoji as emoji_module
    from wxbot.wechat.chat_window import Message

    monkeypatch.setattr(emoji_module.time, "sleep", lambda *a: None)
    clicks = []

    class Fake:
        def Click(self, **kw):
            clicks.append(self)

    button, item = Fake(), Fake()
    monkeypatch.setattr(emoji_module, "find_all", lambda *a, **k: [item])
    self_count = {"n": 0}

    class Chat:
        title = "群"
        wcfg = {"emoji": {"button": {"name": "b"}, "panel": {"name": "p"}, "item": {"name": "i"}}}

        def _window(self):
            return SimpleNamespace(SetActive=lambda: None)

        def _find(self, win, spec):
            if spec.get("name") == "b":
                return button
            if spec.get("name") == "p":
                return SimpleNamespace()
            return None

        def read_all_messages(self):
            n = self_count["n"]
            self_count["n"] = 1
            return [Message("self", "s")] * n

    clock = {"t": 0.0}

    def mono():
        clock["t"] += 0.2
        return clock["t"]

    assert emoji_module.EmojiPanel(Chat()).send(clock=mono, timeout=1.0) == "sent"
    assert clicks == [button, item]


# ---------- 随机回复：文字 / 表情 / 静默 ----------

def test_merge_reply_mode_priority():
    assert merge_reply_mode([{"reply_mode": "none"}, {"reply_mode": "emoji"}, {"reply_mode": "text"}]) == "text"
    assert merge_reply_mode([{"reply_mode": "none"}, {"reply_mode": "emoji"}]) == "emoji"
    assert merge_reply_mode([{"reply_mode": "none"}]) == "none"
    assert merge_reply_mode([]) == "text"


def test_worker_emoji_mode_skips_model_and_enqueues_sticker():
    store = QueueStore(":memory:")
    store.capture("群", [], [Incoming("你好", "m1", "ctx", "甲", "emoji")], group_mode=True, now=0)
    store.prepare(quiet=0, max_wait=10, prefix="/", now=0)
    called = {}

    class Router:
        def handle_reply(self, contact, text, *, context="", request_id=None, member_key="", member_name=""):
            called["model"] = True
            return Reply.from_text("模型文字")

    ModelWorker(store, Router(), quiet=0, max_wait=10, clock=lambda: 0).process_once()
    assert not called.get("model")
    batch = store.records("batches")[0]
    assert batch["state"] == "waiting_delivery"
    assert [r for r in store.records("outbox") if r["batch_id"] == batch["id"] and r['kind'] == 'text'] == []
    emoji = [r for r in store.records("outbox") if r["kind"] == "emoji"]
    assert len(emoji) == 1 and emoji[0]["text"] == ""


def test_worker_none_mode_is_silent():
    store = QueueStore(":memory:")
    store.capture("群", [], [Incoming("你好", "m1", "ctx", "甲", "none")], group_mode=True, now=0)
    store.prepare(quiet=0, max_wait=10, prefix="/", now=0)

    class Router:
        def handle_reply(self, *a, **k):
            return Reply.from_text("不该发送")

    ModelWorker(store, Router(), quiet=0, max_wait=10, clock=lambda: 0).process_once()
    batch = store.records("batches")[0]
    assert batch["state"] == "done"
    assert store.records("outbox") == []  # 静默：无任何发件


def test_reply_mode_never_emoji_when_panel_unconfigured(monkeypatch):
    from wxbot.inbox import MainInbox
    inbox = MainInbox.__new__(MainInbox)
    inbox.cfg = {"wechat": {}}          # 未配置 [wechat.emoji]
    inbox.bot = {"group_reply_chance": 1.0, "emoji_chance": 1.0}
    monkeypatch.setattr(inbox, "_should_interject", lambda: True)
    assert inbox._emoji_available() is False
    # 即使 emoji_chance=1.0，未校准时也永远降级为文字，不发图
    assert all(inbox._reply_mode(False) == "text" for _ in range(10))
    # 已校准后恢复表情可选
    inbox.cfg = {"wechat": {"emoji": {"button": {"name": "表情"}, "item": {"name": "条"}}}}
    assert inbox._emoji_available() is True
