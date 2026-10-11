"""
一个绑定联系人的【独立聊天窗口】：读取消息、发送消息。（适配微信 4.x mmui 界面）

微信 4.x 的消息条目不暴露头像等子控件，只能读到文字，
所以"谁发的"用截图判断：对方的头像在左侧，自己的在右侧。
因此运行时聊天窗口必须完整显示在屏幕上，不能被遮挡或最小化。
"""
import time
from collections import deque
from dataclasses import dataclass

import uiautomation as auto
from PIL import ImageGrab

from ..log import log
from .locator import find, matches


@dataclass(frozen=True)
class Message:
    sender: str   # "other" 对方 / "self" 自己 / "system" 时间、系统提示、非文字消息
    text: str


def _color_diff(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


class ChatWindow:
    def __init__(self, title: str, wcfg: dict):
        self.title = title
        self.wcfg = wcfg
        self.detect = wcfg.get("sender_detect", {})
        self._win: auto.WindowControl | None = None
        self._list: auto.Control | None = None
        self._sent: deque[str] = deque(maxlen=50)   # 机器人自己发过的内容，作为兜底判断

    # ---------- 窗口 ----------
    def _window(self) -> auto.WindowControl | None:
        if self._win is not None and self._win.Exists(0):
            return self._win
        kwargs = {"searchDepth": 1, "Name": self.title}
        if self.wcfg.get("window_class"):
            kwargs["ClassName"] = self.wcfg["window_class"]
        win = auto.WindowControl(**kwargs)
        if not win.Exists(0):
            self._win = self._list = None
            return None
        self._win, self._list = win, None
        return win

    def available(self) -> bool:
        return self._window() is not None

    def _message_list(self) -> auto.Control | None:
        win = self._window()
        if win is None:
            return None
        if self._list is None or not self._list.Exists(0):
            self._list = find(win, self.wcfg["message_list"])
        return self._list

    # ---------- 判断发送方 ----------
    def side_scores(self, item: auto.Control, list_rect) -> tuple[int, int] | None:
        """返回 (左侧非背景像素数, 右侧非背景像素数)；条目不在可见区域时返回 None。"""
        r = item.BoundingRectangle
        top, bottom = max(r.top, list_rect.top), min(r.bottom, list_rect.bottom)
        left, right = r.left, r.right
        if bottom - top < 10 or right - left < 100:
            return None
        img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).convert("RGB")
        w, h = img.size
        px = img.load()
        bg = px[w // 2, 1]                       # 条目顶部中间的空白处作为背景色
        strip = int(self.detect.get("strip_width", 80))
        threshold = int(self.detect.get("diff_threshold", 40))
        step = 2
        lcount = rcount = 0
        for y in range(0, h, step):
            for x in range(0, min(strip, w), step):
                if _color_diff(px[x, y], bg) > threshold:
                    lcount += 1
            for x in range(max(0, w - strip), w, step):
                if _color_diff(px[x, y], bg) > threshold:
                    rcount += 1
        return lcount, rcount

    def _classify(self, item: auto.Control, text: str, list_rect) -> str:
        if not matches(item, self.wcfg.get("text_item", {})):
            return "system"
        scores = self.side_scores(item, list_rect)
        sender = "unknown"
        if scores:
            lc, rc = scores
            min_px = int(self.detect.get("min_pixels", 20))
            if lc >= min_px and lc > rc * 2:
                sender = "other"
            elif rc >= min_px and rc > lc * 2:
                sender = "self"
        if text in self._sent:           # 机器人自己发过的，一定不是对方的
            return "self"
        return sender if sender != "unknown" else "system"

    # ---------- 读取 ----------
    def read_messages(self) -> list[Message]:
        lst = self._message_list()
        if lst is None:
            return []
        list_rect = lst.BoundingRectangle
        result = []
        for item in lst.GetChildren():
            text = item.Name or ""
            if not text.strip():
                continue
            result.append(Message(self._classify(item, text, list_rect), text))
        return result

    # ---------- 发送 ----------
    def send(self, text: str) -> bool:
        win = self._window()
        if win is None:
            log.warning("[%s] 窗口不存在，无法发送", self.title)
            return False
        win.SetActive()
        time.sleep(0.2)
        edit = find(win, self.wcfg["input"])
        if edit is None:
            log.error("[%s] 找不到输入框，请检查 [wechat.input] 配置", self.title)
            return False
        edit.Click(simulateMove=False)
        auto.SetClipboardText(text)          # 用剪贴板粘贴，中文和长文本都稳定
        auto.SendKeys("{Ctrl}v", waitTime=0.1)
        time.sleep(0.15)
        auto.SendKeys("{Enter}", waitTime=0.1)
        self._sent.append(text)
        return True
