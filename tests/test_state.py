"""new_messages 的对齐语义：发送方判定会抖，不能因此把老消息当新消息重送。

复现的是 2026-10-11 实测的回环：20:11 发的提醒被主循环每 ~85 秒当成新消息回送一次
（窗口里始终只有一份），根因就是发送方在 self/system/other 之间抖 + 兜底取 curr[-1:]。
"""
from wxbot.state import new_messages
from wxbot.wechat.chat_window import Message


def m(sender: str, text: str) -> Message:
    return Message(sender, text)


def test_sender_flip_on_last_message_is_not_new():
    """最后一条的发送方判反了（system → other）不算新消息。"""
    prev = [m("self", "在想"), m("other", "行，你慢慢想"), m("self", "1分钟后提醒我喝水"),
            m("system", "⏰ 该喝水啦～")]
    curr = [m("self", "在想"), m("other", "行，你慢慢想"), m("self", "1分钟后提醒我喝水"),
            m("other", "⏰ 该喝水啦～")]
    assert new_messages(prev, curr) == []


def test_any_sender_flip_does_not_resurrect_old_messages():
    prev = [m("self", "A"), m("system", "B"), m("self", "C"), m("system", "D")]
    curr = [m("system", "A"), m("other", "B"), m("self", "C"), m("other", "D")]
    assert new_messages(prev, curr) == []


def test_genuinely_new_trailing_message_is_detected():
    prev = [m("self", "A"), m("other", "B")]
    curr = [m("self", "A"), m("other", "B"), m("other", "在")]
    assert [x.text for x in new_messages(prev, curr)] == ["在"]


def test_new_message_after_sender_flip_is_still_detected():
    """抖动 + 真新消息：新消息要能挑出来，老的不重复。"""
    prev = [m("other", "A"), m("system", "B")]
    curr = [m("other", "A"), m("other", "B"), m("other", "在")]
    assert [x.text for x in new_messages(prev, curr)] == ["在"]


def test_scroll_mismatch_falls_back_to_last_only():
    prev = [m("other", "A"), m("other", "B"), m("other", "C")]
    curr = [m("other", "X"), m("other", "Y")]
    assert [x.text for x in new_messages(prev, curr)] == ["Y"]


def test_no_prev_returns_nothing():
    assert new_messages([], [m("other", "在")]) == []


def test_identical_lists_return_nothing():
    same = [m("other", "在"), m("self", "在的")]
    assert new_messages(same, list(same)) == []
