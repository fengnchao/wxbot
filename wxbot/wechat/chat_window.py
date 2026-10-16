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

_SEND_CHARS_PER_BATCH = 5
_SEND_BATCH_INTERVAL_SECONDS = 1.0


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
    @staticmethod
    def _input_text(edit) -> str | None:
        """读取输入框当前内容；控件不支持 ValuePattern 时返回 None。"""
        try:
            return edit.GetValuePattern().Value or ""
        except Exception:
            return None

    @staticmethod
    def _escape_sendkeys_text(text: str) -> str:
        """转义 SendKeys 的特殊键语法，并将换行作为 Shift+Enter 输入。"""
        return "".join(
            "{{}" if char == "{" else
            "{}}" if char == "}" else
            "{Shift}({Enter})" if char == "\n" else
            char
            for char in text
        )

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
        if not text:
            log.warning("[%s] 消息正文为空，放弃发送", self.title)
            return False
        input_before = self._input_text(edit)
        if input_before:
            log.warning("[%s] 输入框已有未发送内容，放弃发送以免拼接消息", self.title)
            return False

        # 统一换行，再按字符分批键入；Shift+Enter 保留消息中的换行而不提前发送。
        normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
        chunks = [
            normalized_text[i:i + _SEND_CHARS_PER_BATCH]
            for i in range(0, len(normalized_text), _SEND_CHARS_PER_BATCH)
        ]
        for index, chunk in enumerate(chunks):
            try:
                auto.SendKeys(
                    self._escape_sendkeys_text(chunk),
                    interval=0.01,
                    waitTime=0.05,
                    charMode=False,
                )
            except Exception as exc:
                # 不按回车，避免把只输入了一部分的内容发出去。
                log.error(
                    "[%s] 键盘输入失败，第 %d/%d 批；未按回车发送: %s",
                    self.title, index + 1, len(chunks), type(exc).__name__,
                )
                if input_before == "":
                    try:
                        edit.Click(simulateMove=False)
                        auto.SendKeys("{Ctrl}a{Backspace}", waitTime=0.1)
                    except Exception as cleanup_exc:
                        log.warning(
                            "[%s] 未能清理未发送的部分草稿: %s",
                            self.title, type(cleanup_exc).__name__,
                        )
                return False
            if index + 1 < len(chunks):
                time.sleep(_SEND_BATCH_INTERVAL_SECONDS)

        auto.SendKeys("{Enter}", waitTime=0.1)
        self._sent.append(text)
        return True
