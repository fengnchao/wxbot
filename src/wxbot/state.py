"""
新消息检测：对比上一次和这一次读到的消息列表，找出新增在末尾的部分。

消息列表只显示最近的若干条，会随新消息滚动，所以用"重叠部分"来对齐。
"""
from .wechat.chat_window import Message


def _texts(items: list[Message]) -> list[str]:
    return [(i.text or "") for i in items]


def overlap_end(prev: list[Message], curr: list[Message]) -> int | None:
    """返回当前列表中旧尾部的结束位置；优先最长、最早的重叠。"""
    pt, ct = _texts(prev), _texts(curr)
    for k in range(min(len(pt), len(ct)), 0, -1):
        tail = pt[-k:]
        for end in range(k, len(ct) + 1):
            if ct[end - k:end] == tail:
                return end
    return None


def new_messages(prev: list[Message], curr: list[Message]) -> list[Message]:
    """按**正文**对齐（不看发送方），返回末尾新增的消息。

    只看正文的理由：发送方是截图猜头像左右得出的，窗口被遮挡或条目在可视边缘时会抖
    —— 同一条消息这次判 self、下次判 other。旧实现整条 (sender, text) 比较，一抖就整体
    对不齐 → 兜底 `curr[-1:]` 把最后一条当新消息，于是老消息被无限重送（2026-10-11 实测：
    20:11 发的提醒在 20:12 / 20:13 / 20:15 每 ~85 秒被当成新消息回送一次）。
    """
    if not prev:
        return []
    pt, ct = _texts(prev), _texts(curr)
    if ct == pt:
        return []
    # 最长重叠优先；同样的重叠出现多次时取最早一个，保留连续发送的相同正文。
    end = overlap_end(prev, curr)
    if end is not None:
        return curr[end:]
    # 完全对不上（比如窗口被重新打开、滚动过多），只取最后一条，避免一次回复一大堆
    return curr[-1:] if curr and ct[-1] != pt[-1] else []
