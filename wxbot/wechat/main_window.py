"""微信主窗口：功能栏、会话列表，以及右侧当前聊天面板。"""
from dataclasses import dataclass, field
import re
import time

import uiautomation as auto

from ..log import log
from .chat_window import ChatWindow
from .locator import find


@dataclass(frozen=True)
class Conversation:
    title: str
    group_mode: bool
    member_count: int | None = None


@dataclass(frozen=True)
class Session:
    contact: str
    unread_count: int = 0
    mentioned: bool = False
    preview: str = field(default="", compare=False)


def preview_sender(preview: str, text: str) -> str | None:
    """Only associate a nickname when the complete preview body matches the message."""
    normalize = lambda value: " ".join(value.split())
    body = normalize(text)
    if not body:
        return None
    for separator in re.finditer(r"[:：]", preview):
        if normalize(preview[separator.end():]) != body:
            continue
        name = preview[:separator.start()].strip()
        if name and name not in {"我", "你"} and not name.startswith("[") and "\n" not in name:
            return name
    return None


def parse_header(title: str, count_text: str = "") -> Conversation:
    """群人数优先读独立标签，兼容合并成「群名(人数)」的标题。"""
    title = title.strip()
    count = re.fullmatch(r"\s*[（(]\s*(\d+)\s*[）)]\s*", count_text)
    if count:
        return Conversation(title, True, int(count[1]))
    combined = re.fullmatch(r"(.+?)\s*[（(]\s*(\d+)\s*[）)]\s*", title)
    if combined:
        return Conversation(combined[1].strip(), True, int(combined[2]))
    return Conversation(title, False)


def parse_session(automation_id: str, name: str) -> Session | None:
    """仅解析会话标题后面的元数据，不把消息正文中的数字当作未读数。"""
    prefix = "session_item_"
    if not automation_id.startswith(prefix):
        return None
    title = automation_id[len(prefix):]
    if not title:
        return None
    lines = name.splitlines()
    unread = 0
    mentioned = False
    preview = ""
    for index, line in enumerate(lines[1:], start=1):
        line = line.strip()
        if line in {"已置顶", "置顶", "消息免打扰", "免打扰"}:
            continue
        count = re.fullmatch(r"\[(\d+)\+?条(?:未读消息)?\]", line)
        if count:
            # 角标后还有「消息摘要 + 时间」两项；摘要本身可能恰好是「[8条]」。
            if index + 2 >= len(lines):
                break
            unread = int(count[1])
            continue
        if line in {"[有人@我]", "[有人@所有人]"}:
            mentioned = True
            continue
        preview = "\n".join(lines[index:-1]).strip()
        break
    return Session(title, unread, mentioned, preview)


class MainWindow:
    def __init__(self, wcfg: dict):
        self.wcfg = wcfg
        self.cfg = wcfg.get("main_window", {})
        self.depth = int(self.cfg.get("search_depth", 32))
        self._win = None
        self.before_switch = None
        self._ambiguous = set()

    def window(self):
        if self._win is None or not self._win.Exists(0):
            self._win = auto.WindowControl(
                searchDepth=1,
                ClassName=self.cfg.get("window_class", "mmui::MainWindow"),
            )
            if not self._win.Exists(0):
                self._win = None
        return self._win

    def available(self) -> bool:
        return self.window() is not None

    def passive_window(self, contacts=(), *, root=None):
        """仅返回当前在前台的聊天窗口，不激活窗口或移动鼠标。"""
        foreground = auto.GetForegroundWindow()
        if root is not None:
            return root if root.NativeWindowHandle == foreground else None
        win = self.window()
        if win is not None and win.NativeWindowHandle == foreground:
            return win
        for name in contacts:
            detached = self._detached(name)
            if detached is not None and detached.NativeWindowHandle == foreground:
                return detached
        return None

    def _find(self, root, spec):
        return find(root, spec, max_depth=self.depth)

    def _session_list(self):
        win = self.window()
        if win is None:
            return None
        spec = {"automation_id": self.cfg.get("session_list_id", "session_list")}
        lst = self._find(win, spec)
        if lst is None or lst.IsOffscreen:
            # 左侧功能栏：微信、通讯录、收藏、发现；只使用「微信」入口。
            button = self._find(win, {"class_name": "mmui::XTabBarItem",
                                      "name": self.cfg.get("chat_tab_name", "微信")})
            if button is not None:
                win.SetActive()
                button.Click(simulateMove=False)
                time.sleep(0.15)
                lst = self._find(win, spec)
        return lst

    @staticmethod
    def _visible_rows(lst):
        area = lst.BoundingRectangle
        return [row for row in lst.GetChildren()
                if row.ControlTypeName == "ListItemControl"
                and row.BoundingRectangle.bottom > area.top
                and row.BoundingRectangle.top < area.bottom]

    def _pages(self, lst):
        """会话列表为虚拟列表；逐页读取，结束后回到顶部等待下一轮新消息。"""
        max_pages = max(1, int(self.cfg.get("max_scan_pages", 20)))
        try:
            scroll = lst.GetScrollPattern()
        except Exception:
            scroll = None
        if scroll and scroll.VerticallyScrollable:
            scroll.SetScrollPercent(-1, 0, waitTime=0.05)
        elif max_pages > 1:
            lst.WheelUp(wheelTimes=max_pages * 5, interval=0.001, waitTime=0.05)
        previous = None
        moved = False
        try:
            for _ in range(max_pages):
                rows = self._visible_rows(lst)
                signature = tuple(row.AutomationId for row in rows)
                if signature == previous or not rows:
                    break
                previous = signature
                yield rows
                if max_pages == 1:
                    break
                if scroll:
                    if not scroll.VerticallyScrollable or scroll.VerticalScrollPercent >= 100:
                        break
                    scroll.Scroll(auto.ScrollAmount.NoAmount, auto.ScrollAmount.LargeIncrement,
                                  waitTime=0.08)
                else:
                    lst.WheelDown(wheelTimes=5, interval=0.001, waitTime=0.08)
                moved = True
        finally:
            if moved:
                if scroll:
                    scroll.SetScrollPercent(-1, 0, waitTime=0.05)
                else:
                    lst.WheelUp(wheelTimes=max_pages * 5, interval=0.001, waitTime=0.05)

    def sessions(self, *, scan=False) -> list[Session]:
        win = self.window()
        if win is None:
            return []
        lst = self._session_list() if scan else self._find(
            win, {"automation_id": self.cfg.get("session_list_id", "session_list")})
        if lst is None or (not scan and getattr(lst, "IsOffscreen", False)):
            return []
        if scan:
            win.SetActive()
        sessions = {}
        identities = {}
        ambiguous = set()
        # 闲时读取 UIA 已暴露的全部行（含可访问的屏外行），不滚轮、不抢焦点。
        pages = self._pages(lst) if scan else [lst.GetChildren()]
        for rows in pages:
            page_names = set()
            for row in rows:
                item = parse_session(row.AutomationId or "", row.Name or "")
                if item is not None:
                    try:
                        runtime_id = tuple(row.GetRuntimeId())
                    except Exception:
                        runtime_id = None
                    if (item.contact in page_names or (runtime_id and item.contact in identities
                            and identities[item.contact] is not None and identities[item.contact] != runtime_id)):
                        ambiguous.add(item.contact)
                    page_names.add(item.contact)
                    identities[item.contact] = runtime_id
                    sessions[item.contact] = item
        for name in ambiguous - self._ambiguous:
            log.error("[%s] 发现同名会话，停止收发；请设置不同的备注或群名", name)
        if scan:
            self._ambiguous = ambiguous
        else:
            self._ambiguous.update(ambiguous)
        return [item for name, item in sessions.items() if name not in self._ambiguous]

    def current_conversation(self, root=None) -> Conversation | None:
        root = root if root is not None else self.window()
        if root is None:
            return None
        title = self._find(root, {"automation_id": r"re:(^|\.)current_chat_name_label$"})
        count = self._find(root, {"automation_id": r"re:(^|\.)current_chat_count_label$"})
        if title is not None and title.Name:
            return parse_header(title.Name, count.Name if count is not None else "")
        return None

    def matches(self, root, contact: str) -> bool:
        if contact in self._ambiguous:
            return False
        try:
            identity = self.current_conversation(root)
            if identity is not None:
                return identity.title == contact
            return root.ClassName == self.wcfg.get("window_class", "mmui::ChatSingleWindow") \
                and root.Name == contact
        except Exception:
            return False

    def _detached(self, contact):
        win = auto.WindowControl(searchDepth=1, Name=contact,
                                 ClassName=self.wcfg.get("window_class", "mmui::ChatSingleWindow"))
        return win if win.Exists(0) else None

    def detached_contacts(self, names):
        return [name for name in names if self._detached(name) is not None]

    def _handoff(self, root, target):
        if self.before_switch is not None:
            current = self.current_conversation(root)
            if current is not None and current.title != target:
                self.before_switch(current, root)

    def select(self, contact: str, *, click_current=False):
        if contact in self._ambiguous:
            log.error("[%s] 同名会话尚未消除，不能安全选择", contact)
            return None
        win = self.window()
        if win is None:
            return None
        if self.matches(win, contact) and not click_current:
            win.SetActive()
            return win
        # 已经拆为独立窗口的聊天，微信点击会话时会激活那个窗口。
        detached = self._detached(contact)
        if detached is not None and not click_current:
            win.SetActive()
            self._handoff(win, contact)
            detached.SetActive()
            return detached
        lst = self._session_list()
        if lst is None:
            return None
        win.SetActive()
        found = False
        pages = self._pages(lst)
        try:
            for rows in pages:
                targets = [row for row in rows
                           if row.AutomationId == "session_item_" + contact]
                if len(targets) > 1:
                    self._ambiguous.add(contact)
                    log.error("[%s] 会话列表存在同名项，无法安全选择", contact)
                    return None
                if targets:
                    self._handoff(win, contact)
                    targets[0].Click(simulateMove=False)
                    if click_current:
                        log.info("[%s] 已主动点击未读会话行", contact)
                    found = True
                    break
        finally:
            pages.close()
        if not found:
            log.warning("[%s] 主窗口会话列表中未找到目标（扫描上限 %s 页）",
                        contact, self.cfg.get("max_scan_pages", 20))
            return None
        target = detached if detached is not None else win
        if detached is not None:
            detached.SetActive()
        deadline = time.monotonic() + float(self.cfg.get("switch_timeout", 3))
        while time.monotonic() < deadline:
            if self.matches(target, contact) and self._find(target, self.wcfg["message_list"]):
                return target
            time.sleep(0.1)
        log.warning("[%s] 点击会话后标题未匹配或消息区未就绪，停止本次处理", contact)
        return None

    def chat(self, contact: str, *, group_mode=False):
        return MainChatWindow(contact, self.wcfg, self, group_mode=group_mode)


class MainChatWindow(ChatWindow):
    """复用文字消息、头像身份和分批键入；窗口由主界面会话选择器提供。"""
    def __init__(self, title: str, wcfg: dict, desktop: MainWindow, *, group_mode=False):
        super().__init__(title, wcfg, group_mode=group_mode)
        self.desktop = desktop
        self._warned_no_input = False
        self.expected_group = None

    def available(self, *, click_current=False) -> bool:
        win = self._window(click_current=True) if click_current else self._window()
        if win is None:
            return False
        if self._find(win, self.wcfg["input"]) is None:
            if not self._warned_no_input:
                log.warning("[%s] 当前面板没有聊天输入框，跳过收件处理", self.title)
                self._warned_no_input = True
            return False
        self._warned_no_input = False
        return True

    def _find(self, win, spec):
        return find(win, spec, max_depth=int(self.wcfg.get("main_window", {}).get("search_depth", 32)))

    def _window(self, *, click_current=False):
        win = (self.desktop.select(self.title, click_current=True) if click_current
               else self.desktop.select(self.title))
        self._list = None  # 主窗口切换会话后消息控件必须重新获取。
        if win is not None:
            identity = self.desktop.current_conversation(win)
            if identity is None:
                log.warning("[%s] 读不到聊天标题，无法确认对象与会话类型，停止本次处理", self.title)
                return None
            if self.expected_group is not None and identity.group_mode != self.expected_group:
                log.error("[%s] 当前会话类型与原收件目标不一致，停止本次处理", self.title)
                return None
            self.group_mode = identity.group_mode
        return win

    def target_is_current(self, win) -> bool:
        identity = self.desktop.current_conversation(win)
        expected = self.expected_group if self.expected_group is not None else self.group_mode
        return (identity is not None and identity.group_mode == expected
                and self.desktop.matches(win, self.title)
                and auto.GetForegroundWindow() == win.NativeWindowHandle)

    def send_diagnostics(self, win=None, edit=None):
        if win is None:
            try:win=self.desktop.window()
            except Exception:pass
        data=super().send_diagnostics(win,edit)
        data['expected_group']=self.expected_group if self.expected_group is not None else self.group_mode
        data['actual_contact'],data['actual_group'],data['target_matches']=None,None,None
        try:
            identity=self.desktop.current_conversation(win)
            if identity is not None:
                data.update(actual_contact=identity.title,actual_group=identity.group_mode)
            data['target_matches']=self.desktop.matches(win,self.title)
        except Exception:pass
        return data

    def _can_send(self, win, edit) -> bool:
        if not self.target_is_current(win):
            return False
        if edit.HasKeyboardFocus:
            return True
        focused = auto.GetFocusedControl()
        return focused is not None and (focused.AutomationId or "").split(".")[0] == "chat_input_field"
