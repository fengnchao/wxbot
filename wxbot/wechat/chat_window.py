"""
一个绑定联系人或群聊的【独立聊天窗口】：读取消息、发送消息。（适配微信 4.x mmui 界面）

微信 4.x 的消息条目不暴露头像/成员名子控件，只能读到文字；
发送方和群成员头像 ID 用消息行截图判断。
因此运行时聊天窗口必须完整显示在屏幕上，不能被遮挡或最小化。
"""
import time
from collections import deque
from dataclasses import dataclass

import uiautomation as auto
from PIL import Image, ImageGrab

from ..log import log
from .locator import find, matches


@dataclass(frozen=True)
class Message:
    sender: str   # "other" 对方 / "self" 自己 / "system" 时间、系统提示、非文字消息
    text: str
    sender_name: str | None = None  # 群聊成员映射名或稳定头像 ID
    sender_key: str | None = None   # 头像感知哈希，用于稳定区分/配置映射


def _color_diff(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


class ChatWindow:
    def __init__(self, title: str, wcfg: dict, *, group_mode: bool = False):
        self.title = title
        self.wcfg = wcfg
        self.group_mode = group_mode
        self.detect = wcfg.get("sender_detect", {})
        self.group_sender_cfg = wcfg.get("group_sender", {})
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

    def _group_sender_identity(self, item: auto.Control, list_rect):
        """Return a configured display name or stable visual ID for a group avatar."""
        rect = item.BoundingRectangle
        size = int(self.group_sender_cfg.get("avatar_size", 48))
        x_offset = int(self.group_sender_cfg.get("avatar_left_offset", 4))
        y_offset = int(self.group_sender_cfg.get("avatar_top_offset", 0))
        left = max(rect.left + x_offset, list_rect.left)
        top = max(rect.top + y_offset, list_rect.top)
        right = min(rect.right, list_rect.right, left + size)
        bottom = min(rect.bottom, list_rect.bottom, top + size)
        sender_key = None
        sender_name = None
        if right - left >= 16 and bottom - top >= 16:
            try:
                avatar = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
                gray = avatar.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
                low, high = gray.getextrema()
                pixels = gray.load()
                bits = 0
                for y in range(8):
                    for x in range(8):
                        bits = (bits << 1) | int(pixels[x, y] > pixels[x + 1, y])
                if high - low >= 8 and bits not in (0, (1 << 64) - 1):
                    sender_key = f"{bits:016x}"
                    member_names = self.group_sender_cfg.get("member_names", {})
                    sender_name = str(member_names.get(sender_key) or f"成员-{sender_key[:8]}")
            except Exception as e:
                log.debug("[%s] 读取群成员头像失败: %s", self.title, type(e).__name__)

        return sender_name, sender_key

    # ---------- 读取 ----------
    def read_messages(self) -> list[Message]:
        lst = self._message_list()
        if lst is None:
            return []
        list_rect = lst.BoundingRectangle
        result = []
        for item in lst.GetChildren():
            # 只收文字消息条目。时间分隔条（ChatItemView）、图片等其他条目
            # 不进入快照，避免被增量检测当作新消息记录。
            if not matches(item, self.wcfg.get("text_item", {})):
                continue
            text = item.Name or ""
            if not text.strip():
                continue
            sender = self._classify(item, text, list_rect)
            sender_name = None
            sender_key = None
            if self.group_mode and sender == "other":
                sender_name, sender_key = self._group_sender_identity(item, list_rect)
            result.append(Message(sender, text, sender_name, sender_key))
        return result

    # ---------- 发送 ----------
    def _input_text(self, edit) -> str | None:
        """读输入框当前内容；控件不支持 ValuePattern 时返回 None。"""
        try:
            return edit.GetValuePattern().Value or ""
        except Exception:
            return None

    def _wait_paste(self, edit, timeout: float = 3.0) -> bool:
        """等粘贴真的落到输入框里再回车。

        固定 sleep 在长文本 / 慢机器上不够：回车会在空框上触发，消息直接丢掉，
        而且不留痕迹（2026-10-11 实测两条多段长回复没进窗口、输入框也是空的）。
        读不到输入框内容（控件不支持）时退化成定时等待，保持原来的行为。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            val = self._input_text(edit)
            if val is None:
                time.sleep(0.4)
                return True
            if val.strip():
                return True
            time.sleep(0.1)
        return False

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
        for attempt in (1, 2):
            auto.SetClipboardText(text)          # 用剪贴板粘贴，中文和长文本都稳定
            auto.SendKeys("{Ctrl}v", waitTime=0.1)
            if self._wait_paste(edit):
                break
            log.warning("[%s] 粘贴后输入框仍是空的（第 %d 次），重试", self.title, attempt)
            time.sleep(0.3)
        else:
            # 两次都没确认到正文：不按回车（按了发出去的是空的/残文），如实返回失败
            log.error("[%s] 正文没能进输入框，放弃发送（长度 %d）", self.title, len(text))
            return False
        auto.SendKeys("{Enter}", waitTime=0.1)
        self._sent.append(text)
        return True
