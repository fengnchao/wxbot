"""
新消息检测：对比上一次和这一次读到的消息列表，找出新增在末尾的部分。

消息列表只显示最近的若干条，会随新消息滚动，所以用"重叠部分"来对齐。
"""
from .wechat.chat_window import Message


def new_messages(prev: list[Message], curr: list[Message]) -> list[Message]:
    if not prev:
        return []
    if curr == prev:
        return []
    # 找到 prev 的末尾在 curr 中最靠后出现的位置，之后的都是新消息
    for k in range(min(len(prev), len(curr)), 0, -1):
        tail = prev[-k:]
        for end in range(len(curr), k - 1, -1):
            if curr[end - k:end] == tail:
                return curr[end:]
    # 完全对不上（比如窗口被重新打开、滚动过多），只取最后一条，避免一次回复一大堆
    return curr[-1:] if curr and curr[-1] != prev[-1] else []
