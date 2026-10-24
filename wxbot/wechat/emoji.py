"""微信表情面板：点开面板，随机点一张表情/贴图发送。

控件定位走 [wechat.emoji] 配置；不同微信版本需要先用 tools/probe.py 校准
button / panel / item 三个定位条件。点击条目默认直接发送贴图；若你的版本是
“点进输入框、需再回车”，把 [wechat.emoji].enter_to_send 设为 true。
"""
import random
import time

from ..log import log
from .locator import find_all


class EmojiPanel:
    def __init__(self, chat):
        self.chat = chat
        self.cfg = chat.wcfg.get("emoji", {})

    def _find(self, win, key):
        spec = self.cfg.get(key) or {}
        if not spec:
            return None
        return self.chat._find(win, spec)

    def _items(self, panel):
        spec = self.cfg.get("item") or {}
        if not spec:
            return []
        return find_all(panel, spec, max_depth=int(self.cfg.get("max_depth", 8)),
                        limit=int(self.cfg.get("max_items", 60)))

    def send(self, *, clock=time.monotonic, timeout=5.0) -> str:
        """返回 'sent' | 'blocked' | 'uncertain'。"""
        win = self.chat._window()
        if win is None:
            log.warning("[%s] 窗口不存在，无法发送表情", self.chat.title)
            return "blocked"
        win.SetActive()
        button = self._find(win, "button")
        if button is None:
            log.warning("[%s] 找不到表情按钮，请校准 [wechat.emoji].button", self.chat.title)
            return "blocked"
        button.Click(simulateMove=False)
        deadline = clock() + 1.0
        panel = None
        while panel is None and clock() < deadline:
            panel = self._find(win, "panel")
            if panel is None:
                time.sleep(0.05)
        if panel is None:
            log.warning("[%s] 表情面板未出现，请校准 [wechat.emoji].panel", self.chat.title)
            return "blocked"
        items = self._items(panel)
        if not items:
            log.warning("[%s] 表情面板里没有可选条目，请校准 [wechat.emoji].item", self.chat.title)
            return "blocked"
        baseline = self.chat.read_all_messages()
        target = random.choice(items)
        target.Click(simulateMove=False)
        if self.cfg.get("enter_to_send"):
            import uiautomation as auto
            auto.SendKeys("{Enter}", waitTime=0.1)
        confirm_deadline = clock() + max(0.5, float(timeout))
        while clock() < confirm_deadline:
            if self._new_self_bubble(baseline, self.chat.read_all_messages()):
                return "sent"
            time.sleep(0.1)
        return "uncertain"

    @staticmethod
    def _new_self_bubble(before, after):
        count = lambda msgs: sum(1 for m in msgs if m.sender == "self")
        return count(after) > count(before)
