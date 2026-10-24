"""主窗口会话发现、首次未读处理和发送对象校验；不操作真实微信。"""
from types import SimpleNamespace

import pytest

from wxbot.wechat.chat_window import Message
from wxbot.wechat.main_window import (
    Conversation, MainChatWindow, MainWindow, Session, parse_header, parse_session,
)
from wxbot.inbox import MainInbox
from wxbot.reply import Reply


@pytest.mark.parametrize("title,count,expected", [
    ("101", "", Conversation("101", False)),
    ("鸭王集训营(11)", "", Conversation("鸭王集训营", True, 11)),
    ("Bott （3）", "", Conversation("Bott", True, 3)),
    ("群名(2026)", "(11)", Conversation("群名(2026)", True, 11)),
    ("小王(备注)", "", Conversation("小王(备注)", False)),
])
def test_header_classifies_group_by_member_count(title, count, expected):
    assert parse_header(title, count) == expected


def test_session_reads_badge_metadata_without_treating_message_numbers_as_unread():
    session = parse_session("session_item_Bott", "Bott\n[3条] \n[有人@我]\n101: @Bot\n19:29\n")
    assert session == Session("Bott", 3, True)
    assert parse_session("session_item_101", "101\n已置顶\n123\n19:29\n") == Session("101")
    assert parse_session("session_item_101", "101\n已置顶\n[1条]\n123\n19:29\n") == Session("101", 1)
    assert parse_session("session_item_101", "101\n普通消息\n[8条]\n19:29\n") == Session("101")
    assert parse_session("session_item_101", "101\n[8条]\n19:29\n") == Session("101")


class Chat:
    def __init__(self, title, messages, group=False):
        self.title, self.messages, self.group_mode = title, list(messages), group
        self.sent = []

    def available(self, **kwargs):
        desktop = getattr(self, 'desktop', None)
        if desktop is not None:
            desktop.current = Conversation(self.title, self.group_mode)
            desktop.pending = [s for s in desktop.pending if s.contact != self.title]
        return True

    def read_messages(self, **kwargs):
        return list(self.messages)

    def read_from_window(self, root, **kwargs):
        return list(self.messages)

    def target_is_current(self, root):
        return True

    def remember_sent(self, text):
        self.sent.append(text)

    def read_unread_messages(self, count):
        return [m for m in self.messages if m.sender == "other"][-count:]

    def read_bundle(self, count):
        return self.read_messages(), self.read_unread_messages(count)

    def send(self, text):
        self.sent.append(text)
        self.messages.append(Message("self", text))
        return True


class Desktop:
    def __init__(self, chats, sessions=(), current=None):
        self.chats = {c.title: c for c in chats}
        self.pending = list(sessions)
        self.current = current

    def available(self):
        return True

    def sessions(self, **kwargs):
        return list(self.pending)

    def current_conversation(self, root=None):
        return self.current

    def passive_window(self, contacts=(), *, root=None):
        return root if root is not None else object()

    def matches(self, root, name):
        return self.current is not None and self.current.title == name

    def detached_contacts(self, names):
        return []

    def chat(self, name, **kwargs):
        self.chats[name].desktop = self
        return self.chats[name]


class Router:
    def __init__(self):
        self.calls = []
        self.on_handle = lambda: None

    def handle(self, contact, text, *, context="", member_key="", member_name=""):
        self.calls.append((contact, text, context))
        self.on_handle()
        return "回复：" + text

    def handle_reply(self, contact, text, *, context='', request_id=None, member_key="", member_name=""):
        return Reply.from_text(self.handle(contact,text,context=context))


def cfg():
    return {"bot": {"bound_users": ["101"], "bound_groups": ["鸭王集训营"],
                    "mention_names": ["Bot"], "reply_delay_min": 0, "reply_delay_max": 0,
                    "group_reply_chance": 0},
            "wechat": {"mode": "main"},
            "queue": {"database": ":memory:", "quiet_seconds": 0, "max_wait_seconds": 10}}


def finish_outbox(inbox):
    while delivery := inbox.store.claim_delivery(now=inbox.clock() + 100):
        inbox.store.finish_delivery(delivery.id, "sent", now=inbox.clock())


def process(inbox):
    while inbox.worker.process_once():
        finish_outbox(inbox)


def test_first_unread_only_processes_unread_tail():
    chat = Chat("101", [Message("other", t) for t in ["历史", "第一条", "第二条"]])
    desktop = Desktop([chat], [Session("101", 2)])
    router = Router()
    inbox = MainInbox(cfg(), router, desktop=desktop)
    inbox.poll(allow_switch=True)
    assert router.calls == []  # 采集线程不调用模型。
    process(inbox)
    assert [call[1] for call in router.calls] == ["第一条\n第二条"]


def test_group_messages_all_enter_context_and_mention_is_stripped():
    private = Chat("101", [Message("other", "123")])
    group = Chat("鸭王集训营", [Message("other", "12")], True)
    mentioned = Chat("Bott", [Message("other", "普通消息"), Message("other", "@别人 hi"),
                              Message("other", "@Bot\u2005你好", "成员甲", "abc")], True)
    desktop = Desktop([private, group, mentioned],
                      [Session("101", 1), Session("鸭王集训营", 1), Session("Bott", 3, True)])
    router = Router()
    inbox = MainInbox(cfg(), router, desktop=desktop)
    inbox.poll(allow_switch=True)
    inbox.poll(allow_switch=True)
    inbox.poll(allow_switch=True)
    process(inbox)
    pairs = [(c, t) for c, t, _ in router.calls]
    # 私聊进模型
    assert ("101", "123") in pairs
    # 非 @群消息也进模型（进上下文），不再被跳过
    assert ("鸭王集训营", "12") in pairs
    assert ("Bott", "普通消息") in pairs
    # @Bot 前缀被去掉，并保留 member_id 上下文
    assert ("Bott", "你好") in pairs
    assert any("member_id=abc" in ctx for _, _, ctx in router.calls)
    assert group.sent == []


def test_active_chat_is_polled_even_without_badge_and_baselines_history():
    chat = Chat("101", [Message("other", "历史")])
    desktop = Desktop([chat], current=Conversation("101", False))
    router = Router()
    inbox = MainInbox(cfg(), router, desktop=desktop)
    inbox.poll(allow_switch=True)
    process(inbox)
    assert router.calls == []
    chat.messages.append(Message("other", "当前窗口新消息"))
    inbox.poll(allow_switch=True)
    process(inbox)
    assert [call[1] for call in router.calls] == ["当前窗口新消息"]


def test_incoming_during_model_call_is_not_discarded_by_post_send_snapshot():
    chat = Chat("101", [Message("other", "第一条")])
    desktop = Desktop([chat], [Session("101", 1)], Conversation("101", False))
    router = Router()
    def arrived():
        chat.messages.append(Message("other", "等待回复时收到"))
        router.on_handle = lambda: None
    router.on_handle = arrived
    inbox = MainInbox(cfg(), router, desktop=desktop)
    inbox.poll(allow_switch=True)
    process(inbox)
    desktop.pending = []
    inbox.poll(allow_switch=True)
    process(inbox)
    assert [call[1] for call in router.calls] == ["第一条", "等待回复时收到"]


@pytest.mark.parametrize("text,first_chunk", [("1234", "1234"), ("1234567890", "12345")])
def test_switching_recipient_during_typing_never_presses_enter(monkeypatch, text, first_chunk):
    from wxbot.wechat import chat_window as module
    from wxbot.wechat import typing as typing_module
    from wxbot.wechat.clipboard import ClipboardLease
    from test_clipboard import FakeClipboard
    clipboard=FakeClipboard()
    monkeypatch.setattr(typing_module,'ClipboardLease',lambda text: ClipboardLease(text,api=clipboard))

    root = SimpleNamespace(SetActive=lambda: None, NativeWindowHandle=123)
    edit = SimpleNamespace(Click=lambda **kw: None, HasKeyboardFocus=True,
                           GetValuePattern=lambda: SimpleNamespace(Value=""))
    desktop = SimpleNamespace(select=lambda name: root, selected="101",
                              current_conversation=lambda root=None: Conversation(desktop.selected, False),
                              matches=lambda root, name: desktop.selected == name)
    chat = MainChatWindow("101", {"input": {}}, desktop)
    monkeypatch.setattr(chat, "_find", lambda win, spec: edit)
    monkeypatch.setattr(module.auto, "GetForegroundWindow", lambda: 123)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    typed = []
    def send(keys, **kwargs):
        typed.append(keys)
        desktop.selected = "另一个人"
    monkeypatch.setattr(module.auto, "SendKeys", send)
    assert chat.send(text) is False
    assert typed == ['{Ctrl}v']
    assert clipboard.data[13]=='original text'


def test_main_mode_allows_empty_binding_lists(tmp_path):
    from wxbot.config import load_config
    path = tmp_path / "wx.toml"
    path.write_text('[bot]\n[wechat]\nmode="main"\n', encoding="utf-8")
    assert load_config(path)["wechat"]["mode"] == "main"
    path.write_text('[bot]\n[wechat]\nmode="independent"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_outbound_select_preserves_unread_messages_before_clearing_badge():
    chat = Chat("101", [Message("other", t) for t in ["历史", "新收到"]])
    desktop = Desktop([chat], [Session("101", 1)], Conversation("101", False))
    request = SimpleNamespace(contact="101", text="主动提醒", finish=lambda *args: None)
    router = Router()
    inbox = MainInbox(cfg(), router, desktop=desktop)
    inbox.deliver(request)
    assert chat.sent == []  # HTTP 入队后尚未操作微信。
    assert desktop.pending == [Session("101", 1)]
    inbox.poll(allow_switch=True)
    finish_outbox(inbox)
    process(inbox)
    assert [call[1] for call in router.calls] == ["新收到"]


def test_missing_header_never_defaults_unknown_group_to_private_chat():
    desktop = SimpleNamespace(select=lambda name: object(),
                              current_conversation=lambda root: None)
    chat = MainChatWindow("未知聊天", {}, desktop)
    assert chat.available() is False


def test_non_chat_panel_without_message_input_is_not_received(monkeypatch):
    root = object()
    desktop = SimpleNamespace(select=lambda name: root,
                              current_conversation=lambda root: Conversation("通知面板", False))
    chat = MainChatWindow("通知面板", {"input": {}}, desktop)
    monkeypatch.setattr(chat, "_find", lambda root, spec: None)
    assert chat.available() is False


def test_unread_count_includes_images_without_replaying_older_text(monkeypatch):
    from wxbot.wechat.chat_window import ChatWindow
    def item(cls, text):
        return SimpleNamespace(ClassName=cls, Name=text)
    rows = [item("mmui::ChatTextItemView", "较早的历史"),
            item("mmui::ChatItemView", "19:29"),
            item("mmui::ChatImageItemView", "图片"),
            item("mmui::ChatTextItemView", "新文字")]
    chat = ChatWindow("测试", {"text_item": {"class_name": "mmui::ChatTextItemView"}})
    monkeypatch.setattr(chat, "_message_list",
                        lambda: SimpleNamespace(BoundingRectangle=None, GetChildren=lambda: rows))
    monkeypatch.setattr(chat, "_classify", lambda *args: "other")
    assert [m.text for m in chat.read_unread_messages(2)] == ["新文字"]


def test_switch_handoff_captures_already_read_messages_arriving_during_reply():
    chat = Chat("101", [Message("other", "第一条")])
    desktop = Desktop([chat], [Session("101", 1)], Conversation("101", False))
    router = Router()
    inbox = MainInbox(cfg(), router, desktop=desktop)
    inbox.poll(allow_switch=True)
    process(inbox)
    # 第一轮回复过程中到达的消息在微信中已读；随后机器人切换到另一个聊天。
    chat.messages.append(Message("other", "没有未读角标的新消息"))
    desktop.pending = []
    desktop.current = Conversation("另一个聊天", False)
    desktop.chats["另一个聊天"] = Chat("另一个聊天", [])
    inbox._before_switch(Conversation("101", False), object())
    inbox.poll(allow_switch=True)
    process(inbox)
    assert [call[1] for call in router.calls] == ["第一条", "没有未读角标的新消息"]


def test_capture_checkpoint_survives_restart_without_duplicate_model_message():
    from wxbot.queue_store import QueueStore
    store = QueueStore(":memory:")
    chat = Chat("101", [Message("other", "新消息")])
    desktop = Desktop([chat], [Session("101", 1)], Conversation("101", False))
    first = MainInbox(cfg(), Router(), desktop=desktop, store=store)
    first.poll(allow_switch=True)
    desktop.pending = []
    second = MainInbox(cfg(), Router(), desktop=desktop, store=store)
    second.poll(allow_switch=True)
    assert len(store.records("inbox")) == 1


def test_typing_poll_records_other_badges_without_switching_away_from_partial_draft():
    a = Chat("101", [Message("other", "原消息")])
    b = Chat("B", [Message("other", "B的问题")])
    desktop = Desktop([a, b], current=Conversation("101", False))
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox.poll(allow_switch=True)
    a.messages.append(Message("other", "打字期间的补充"))
    desktop.pending = [Session("B", 1)]
    inbox.delivery.active = SimpleNamespace(typing=SimpleNamespace(win=object(), enter_attempted=False))
    inbox.poll(allow_switch=False)
    assert [row["text"] for row in inbox.store.records("inbox")] == ["打字期间的补充"]
    assert inbox.store.pending_sessions()[0]["contact"] == "B"
    inbox.delivery.active = None
    inbox.poll(allow_switch=True)
    assert [row["text"] for row in inbox.store.records("inbox")] == ["打字期间的补充", "B的问题"]


def test_poll_failure_does_not_starve_delivery_tick():
    inbox = MainInbox(cfg(), Router(), desktop=Desktop([]), monotonic=lambda: 0)
    calls = []
    def broken_poll(**kwargs):
        raise RuntimeError("session list temporarily unavailable")
    inbox.poll = broken_poll
    inbox.delivery.tick = lambda **kw: calls.append("delivery")
    inbox.tick()
    assert calls == ["delivery"]
    assert inbox._next_poll > 0


def test_unread_count_recovers_visible_messages_when_old_snapshot_no_longer_overlaps():
    chat = Chat("101", [Message("other", "旧锚点")])
    desktop = Desktop([chat], current=Conversation("101", False))
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox.poll(allow_switch=True)
    chat.messages = [Message("other", text) for text in ("新问题一", "新问题二", "新问题三")]
    desktop.pending = [Session("101", 3)]
    inbox.poll(allow_switch=True)
    assert [row["text"] for row in inbox.store.records("inbox")] == ["新问题一", "新问题二", "新问题三"]


def test_failed_read_preserves_checkpoint_and_pending_task(monkeypatch):
    chat = Chat("101", [Message("other", "旧锚点")])
    desktop = Desktop([chat], current=Conversation("101", False))
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox.poll(allow_switch=True)
    desktop.pending = [Session("101", 1)]
    before = inbox.store.snapshots()
    def broken_read(count):
        raise RuntimeError("message control unavailable")
    monkeypatch.setattr(chat, "read_bundle", broken_read)
    inbox.poll(allow_switch=True)
    assert inbox.store.snapshots() == before
    assert inbox.store.pending_sessions()[0]["contact"] == "101"
    assert inbox.store.records("inbox") == []


def test_explicit_unread_preserves_new_identical_text_with_unchanged_snapshot():
    chat = Chat("101", [Message("other", "你好")])
    desktop = Desktop([chat], current=Conversation("101", False))
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox.poll(allow_switch=True)
    desktop.pending = [Session("101", 1)]  # 有界列表滚出旧的“你好”、进入新的“你好”。
    inbox.poll(allow_switch=True)
    assert [row["text"] for row in inbox.store.records("inbox")] == ["你好"]


def test_ambiguous_session_name_is_never_accepted_as_current_target(monkeypatch):
    desktop = MainWindow({})
    root = object()
    lst = SimpleNamespace(GetChildren=lambda: rows)
    rows = [SimpleNamespace(AutomationId="session_item_同名", Name="同名\n[1条]\nhi\n10:00",
                            GetRuntimeId=lambda i=i: [1, i]) for i in range(2)]
    monkeypatch.setattr(desktop, "window", lambda: root)
    monkeypatch.setattr(desktop, "_find", lambda *args: lst)
    monkeypatch.setattr(desktop, "_visible_rows", lambda *args: rows)
    monkeypatch.setattr(desktop, "current_conversation", lambda *args: Conversation("同名", False))
    assert desktop.sessions(scan=False) == []
    assert not desktop.matches(root, "同名")
    assert desktop.select("同名") is None


def test_expected_private_chat_does_not_send_to_same_named_group():
    desktop = SimpleNamespace(select=lambda name: object(),
                              current_conversation=lambda root: Conversation("同名", True, 11))
    chat = MainChatWindow("同名", {}, desktop)
    chat.expected_group = False
    assert chat._window() is None


def test_idle_poll_never_selects_a_chat_or_scrolls_discovery(monkeypatch):
    chat = Chat("101", [Message("other", "历史")])
    desktop = Desktop([chat], current=Conversation("101", False))
    scans = []
    def passive_sessions(*, scan):
        scans.append(scan)
        assert scan is False
        return []
    def no_selection():
        raise AssertionError("idle poll must not select/activate a window")
    monkeypatch.setattr(desktop, "sessions", passive_sessions)
    monkeypatch.setattr(chat, "available", no_selection)
    monkeypatch.setattr(chat, "read_messages", no_selection)
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox.poll()
    assert scans == [False]
    assert inbox.snapshots["101"] == chat.messages


def test_default_session_discovery_never_activates_or_moves_mouse(monkeypatch):
    desktop = MainWindow({})
    def no_action(*args, **kwargs):
        raise AssertionError("passive session discovery moved the UI")
    row = SimpleNamespace(ControlTypeName="ListItemControl", AutomationId="session_item_101",
                          Name="101\n[1条]\n你好\n12:00", GetRuntimeId=lambda: [1, 2])
    lst = SimpleNamespace(IsOffscreen=False, GetChildren=lambda: [row])
    root = SimpleNamespace(SetActive=no_action)
    monkeypatch.setattr(desktop, "window", lambda: root)
    monkeypatch.setattr(desktop, "_find", lambda *args: lst)
    monkeypatch.setattr(desktop, "_pages", no_action)
    assert desktop.sessions() == [Session("101", 1)]


def test_passive_current_capture_respects_ambiguous_recipient_guard(monkeypatch):
    chat = Chat("101", [Message("other", "历史")])
    desktop = Desktop([chat], current=Conversation("101", False))
    inbox = MainInbox(cfg(), Router(), desktop=desktop)
    inbox.poll(allow_switch=True)
    chat.messages.append(Message("other", "同名对象的新问题"))
    monkeypatch.setattr(desktop, "matches", lambda *args: False)
    inbox.poll(allow_switch=True)
    assert inbox.store.records("inbox") == []


def test_arrival_just_before_enter_is_collected_even_without_another_poll():
    chat = Chat("101", [Message("other", "你好")])
    desktop = Desktop([chat], [Session("101", 1)], Conversation("101", False))
    router = Router()
    inbox = MainInbox(cfg(), router, desktop=desktop)
    inbox.poll(allow_switch=True)
    desktop.pending = []
    assert inbox.worker.process_once()
    def start_send(text, **kwargs):
        task = SimpleNamespace(win=object(), enter_attempted=False, error="", state="typing", steps=0)
        def step():
            task.steps += 1
            if task.steps == 2:
                chat.messages = [Message("other", "回车前刚到的新问题")]
                if getattr(task, "before_enter", None):
                    task.before_enter()
                task.enter_attempted, task.state = True, "submitted"
                chat.messages.append(Message("self", text))
            return task.state
        task.step = step
        return task
    chat.start_send = start_send
    inbox.delivery.tick(); inbox.delivery.tick(); inbox.delivery.tick()
    assert inbox.store.records("outbox")[0]["state"] == "sent"
    assert [row["text"] for row in inbox.store.records("inbox")] == ["你好", "回车前刚到的新问题"]
    assert inbox.worker.process_once()
    assert [call[1] for call in router.calls] == ["你好", "回车前刚到的新问题"]
