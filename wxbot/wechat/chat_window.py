"""
一个绑定联系人或群聊的【独立聊天窗口】：读取消息、发送消息。（适配微信 4.x mmui 界面）

微信 4.x 的消息条目不暴露头像/成员名子控件，只能读到文字；
发送方和群成员头像 ID 用消息行截图判断。
因此运行时聊天窗口必须完整显示在屏幕上，不能被遮挡或最小化。
"""
import time
from collections import deque
from dataclasses import dataclass
from statistics import median

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

    def _find(self, win, spec):
        return find(win, spec)

    def _message_list(self) -> auto.Control | None:
        win = self._window()
        if win is None:
            return None
        if self._list is None or not self._list.Exists(0):
            self._list = self._find(win, self.wcfg["message_list"])
        return self._list

    # ---------- 判断发送方 ----------
    def side_scores(self, item: auto.Control, list_rect) -> tuple[int, int] | None:
        """返回 (左侧非背景像素数, 右侧非背景像素数)；条目不在可见区域时返回 None。"""
        r = item.BoundingRectangle
        # Only the avatar-height band carries reliable direction evidence. The
        # middle of a wide outgoing bubble is NOT the conversation background.
        # A clipped row may have lost its avatar; do not classify its text tail.
        top = r.top
        avatar_band = max(48, int(self.group_sender_cfg.get("avatar_size", 48))) + 8
        bottom = min(r.bottom, top + avatar_band)
        left, right = r.left, r.right
        if (top < list_rect.top or bottom > list_rect.bottom
                or left < list_rect.left or right > list_rect.right):
            return None
        if bottom - top < 10 or right - left < 100:
            return None
        img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).convert("RGB")
        w, h = img.size
        px = img.load()
        strip = int(self.detect.get("strip_width", 80))
        threshold = int(self.detect.get("diff_threshold", 40))
        # Sample the two outer gutters, away from bubbles. Require agreement:
        # an overlay, partial row or nonstandard layout is not sender evidence.
        def gutter_color(columns):
            samples = [px[x, y] for x in columns for y in range(0, h, 2)]
            return tuple(int(median(p[channel] for p in samples)) for channel in range(3))

        bg = gutter_color((0, 1, 2))
        right_bg = gutter_color((w - 3, w - 2, w - 1))
        if _color_diff(bg, right_bg) > threshold:
            return None
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

    def _classify(self, item: auto.Control, text: str, list_rect, *, use_sent_cache=True) -> str:
        scores = self.side_scores(item, list_rect)
        sender = "unknown"
        if scores:
            lc, rc = scores
            min_px = int(self.detect.get("min_pixels", 20))
            if lc >= min_px and lc > rc * 2:
                sender = "other"
            elif rc >= min_px and rc > lc * 2:
                sender = "self"
        if sender == "unknown" and use_sent_cache and text in self._sent:
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
    def _read_entries(self, lst=None, *, strict_sender=False) -> list[tuple[Message, bool]]:
        lst = self._message_list() if lst is None else lst
        if lst is None:
            raise RuntimeError(f"[{self.title}] 消息列表暂时不可读取")
        list_rect = lst.BoundingRectangle
        result = []
        for item in lst.GetChildren():
            is_text = matches(item, self.wcfg.get("text_item", {}))
            cls = item.ClassName or ""
            # 时间提示不计数；图片等真实消息参与未读数量对齐，但不交给模型。
            if not is_text and (not cls.startswith("mmui::Chat")
                                or not cls.endswith("ItemView") or cls == "mmui::ChatItemView"):
                continue
            text = item.Name or ""
            if is_text and not text.strip():
                continue
            sender = (self._classify(item, text, list_rect, use_sent_cache=False)
                      if strict_sender else self._classify(item, text, list_rect))
            sender_name = None
            sender_key = None
            if self.group_mode and sender == "other":
                sender_name, sender_key = self._group_sender_identity(item, list_rect)
            result.append((Message(sender, text, sender_name, sender_key), is_text))
        return result

    def read_messages(self, *, strict_sender=False) -> list[Message]:
        return [message for message, is_text in self._read_entries(strict_sender=strict_sender) if is_text]

    def read_from_window(self, root, *, strict_sender=False) -> list[Message]:
        """只读当前面板，不选择会话；用于离开会话前的最后一次收件。"""
        lst = self._find(root, self.wcfg["message_list"])
        if lst is None:
            raise RuntimeError(f"[{self.title}] 当前面板消息列表暂时不可读取")
        return [message for message, is_text in self._read_entries(lst, strict_sender=strict_sender) if is_text]

    def read_unread_messages(self, count: int) -> list[Message]:
        return self.read_bundle(count)[1]

    def read_bundle(self, count: int):
        all_entries = self._read_entries()
        messages = [message for message, is_text in all_entries if is_text]
        entries = [(message, is_text) for message, is_text in all_entries
                   if message.sender == "other"]
        if count > len(entries):
            log.warning("[%s] 未读 %d 条，当前可读取 %d 条；超出已加载消息区的历史不会自动补读",
                        self.title, count, len(entries))
        fresh = [message for message, is_text in entries[-count:] if is_text] if count > 0 else []
        return messages, fresh

    # ---------- 发送 ----------
    @staticmethod
    def _input_text(edit) -> str | None:
        """读取输入框当前内容；控件不支持 ValuePattern 时返回 None。"""
        try:
            return edit.GetValuePattern().Value or ""
        except Exception:
            return None

    def _can_send(self, win, edit) -> bool:
        return self.target_is_current(win) and edit.HasKeyboardFocus

    def target_is_current(self, win) -> bool:
        return win.Name == self.title and auto.GetForegroundWindow() == win.NativeWindowHandle

    def send_diagnostics(self, win=None, edit=None):
        """Failure metadata only; never read drafts, clipboard text or other apps' titles."""
        data={'expected_contact':self.title,'expected_group':self.group_mode}
        for key,read in (
            ('actual_contact',lambda:win.Name),('expected_hwnd',lambda:win.NativeWindowHandle),
            ('foreground_hwnd',auto.GetForegroundWindow),('input_focused',lambda:bool(edit.HasKeyboardFocus))):
            try:data[key]=read()
            except Exception:data[key]=None
        return data

    def remember_sent(self, text):
        self._sent.append(text)

    def start_send(self, text: str, *, clock=time.monotonic):
        from .typing import TypingSession

        win = self._window()
        if win is None:
            log.warning("[%s] 窗口不存在，无法发送", self.title)
            return None
        win.SetActive()
        time.sleep(0.2)
        edit = self._find(win, self.wcfg["input"])
        if edit is None:
            log.error("[%s] 找不到输入框，请检查 [wechat.input] 配置", self.title)
            return None
        edit.Click(simulateMove=False)
        if not text:
            log.warning("[%s] 消息正文为空，放弃发送", self.title)
            return None
        input_before = self._input_text(edit)
        if input_before is None:
            log.warning("[%s] 无法确认输入框是否为空，停止发送并保留输入内容", self.title)
            return None
        if input_before:
            log.warning("[%s] 输入框已有未发送内容，放弃发送以免拼接消息", self.title)
            return None
        return TypingSession(self, win, edit, text, clock=clock)

    def send(self, text: str) -> bool:
        """兼容独立窗口模式；主窗口队列使用 start_send 后逐步调用 step。"""
        task = self.start_send(text)
        if task is None:
            return False
        try:
            while task.state == "typing":
                task.step()
                if task.state == "typing":
                    time.sleep(0.05)
        finally:
            task.close()
        if task.state == "submitted":
            self.remember_sent(text)
            return True
        log.warning("[%s] 输入/发送停止，状态=%s: %s", self.title, task.state, task.error)
        return False
