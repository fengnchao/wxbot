"""UI-thread mention picker with verified, body-only fallback.

Calibrate ``wechat.mention.panel`` and ``item`` for the installed WeChat.
TextPattern embedded children provide the rich object proof, not an @ string.
"""
import time

import uiautomation as auto

from .locator import find_all


def top_level_windows():
    return auto.GetRootControl().GetChildren()


def window_owner(hwnd):
    import ctypes
    function = ctypes.windll.user32.GetWindow
    function.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    function.restype = ctypes.c_void_p
    return function(hwnd, 4)  # GW_OWNER; do not confuse parent with owner.


def rich_draft(edit, name):
    """Return (raw text, embedded object's runtime identity), or no proof."""
    try:
        document = edit.GetTextPattern().DocumentRange
        children = document.GetChildren()
        if len(children) != 1 or children[0].Name not in (name, '@' + name):
            return None
        identity = tuple(children[0].GetRuntimeId())
        raw = document.GetText().replace('\r\n', '\n').replace('\r', '\n')
        if not identity or not (raw.startswith('\ufffc') or raw.startswith('@' + name)):
            return None
        return raw, identity
    except Exception:
        return None


def literal_keys(text):
    return ''.join('{{}' if c == '{' else '{}}' if c == '}' else c for c in text)


class MentionSelection:
    """One bounded UI operation per step; no sleeps or Enter key selection."""
    def __init__(self, chat, win, edit, name, *, clock=time.monotonic):
        self.chat, self.win, self.edit, self.name = chat, win, edit, name
        self.clock = clock
        self.phase = 'mention_trigger'
        self.deadline = clock() + 2
        self.error = ''
        self.proof = None
        self.cfg = chat.wcfg.get('mention', {})
        self.existing_windows = set()
        self.existing_panels = set()
        self.fallback_reason = ''
        self.fallback_draft = None
        self.clicked = False
        self.filter_ready = 0

    @staticmethod
    def _identity(control):
        try:
            identity = tuple(control.GetRuntimeId())
            return identity or None
        except Exception:
            return None

    def _inline_panels(self):
        panels = {}
        depth = int(self.chat.wcfg.get('main_window',{}).get('search_depth',32))
        for kind in ('ListControl','MenuControl'):
            for panel in find_all(self.win,{'control_type':kind},max_depth=depth):
                automation_id = getattr(panel,'AutomationId','') or ''
                identity = self._identity(panel)
                if (identity and not getattr(panel,'IsOffscreen',False)
                        and not any(value in automation_id for value in ('session_list','chat_message_list'))):
                    panels[identity] = panel
        return panels

    def _panel(self):
        if self.cfg.get('panel'):
            panel = self.chat._find(self.win, self.cfg['panel'])
            return panel if panel is not None and not getattr(panel,'IsOffscreen',False) else None
        # A candidate list elsewhere in WeChat is not an @ selector. Only a
        # popup created after our trigger, in this process and owned by this
        # exact chat HWND, is eligible for discovery.
        popups = []
        for popup in top_level_windows():
            handle = popup.NativeWindowHandle
            if (handle and handle not in self.existing_windows
                    and popup.ProcessId == self.win.ProcessId
                    and window_owner(handle) == self.win.NativeWindowHandle):
                popups.append(popup)
        if len(popups) == 1:
            return popups[0]
        if popups:
            return None
        inline = [panel for key,panel in self._inline_panels().items() if key not in self.existing_panels]
        return inline[0] if len(inline)==1 else None

    def step(self):
        if not self.chat._can_send(self.win, self.edit):
            self.error = '选择提及前聊天对象或输入焦点变化，未按回车'
            return 'blocked'
        if self.phase.startswith('mention_fallback_'):
            return self._cleanup()
        if self.phase == 'mention_trigger':
            if self.chat._input_text(self.edit) != '':
                self.error = '选择提及前输入框含草稿，未按回车'
                return 'blocked'
            if not self.cfg.get('panel'):
                self.existing_windows = {window.NativeWindowHandle for window in top_level_windows()}
                self.existing_panels = set(self._inline_panels())
            auto.SendKeys('@', waitTime=0)
            self.phase = 'mention_filter'
            return 'typing'
        if self.phase == 'mention_filter':
            if self.chat._input_text(self.edit) != '@':
                self.error = '提及筛选前草稿变化，未按回车'
                return 'blocked'
            auto.SendKeys(literal_keys(self.name), interval=0, waitTime=0)
            self.phase = 'mention_choose'
            self.deadline = self.clock() + 2
            self.filter_ready = self.clock() + .2
            return 'typing'
        if self.phase == 'mention_choose':
            if self.chat._input_text(self.edit) != '@' + self.name:
                self.error = '提及选择前草稿变化，未按回车'
                return 'blocked'
            try:
                panel = self._panel()
            except Exception:
                return self._wait('picker_missing')
            if panel is None:
                return self._wait('picker_missing')
            if self.clock() < self.filter_ready:
                return 'typing'
            try:
                candidates = [item for item in find_all(panel, self.cfg.get('item') or {'control_type': 'ListItemControl'})
                              if not getattr(item,'IsOffscreen',False)]
                eligible = (len(candidates)==1 and candidates[0].Name == self.name
                            and getattr(candidates[0],'IsEnabled',True))
            except Exception:
                return self._wait('picker_missing')
            if len(candidates) > 1:
                return self._wait('multiple_candidates')
            if not eligible:
                return self._wait('member_missing')
            # A click selects the candidate; Enter remains reserved for the
            # final verified body, never for an ambiguous popup selection.
            candidates[0].Click(simulateMove=False)
            self.clicked = True
            self.phase = 'mention_verify'
            self.deadline = self.clock() + 2
            return 'typing'
        self.proof = rich_draft(self.edit, self.name)
        if self.proof is None:
            return self._wait('object_unverified')
        raw, _ = self.proof
        if raw not in tuple(prefix + suffix for prefix in ('\ufffc', '@' + self.name)
                            for suffix in ('', ' ', '\u2005')):
            self.error = '选择提及后存在额外草稿，未按回车'
            return 'blocked'
        return 'selected'

    def _wait(self, reason):
        if self.clock() < self.deadline:
            return 'typing'
        current = self.chat._input_text(self.edit)
        # An unreadable embedded object has no proven owner. Only our exact
        # literal query can be removed when rich-object verification failed.
        prefixes = ('@'+self.name,)
        allowed = tuple(prefix+suffix for prefix in prefixes for suffix in ('',' ','\u2005'))
        if current not in allowed:
            self.error = '放弃提及时输入内容变化或不可读，保留草稿，未按回车'
            return 'blocked'
        self.fallback_reason = reason
        self.fallback_draft = current
        self.phase = 'mention_fallback_cancel'
        return 'typing'

    def _cleanup(self):
        current = self.chat._input_text(self.edit)
        if self.phase == 'mention_fallback_verify':
            if current == '':
                self.proof = None
                return 'plain'
            if self.clock() < self.deadline:
                return 'typing'
            self.error = '放弃提及时未能确认草稿已清空，未粘贴正文、未按回车'
            return 'blocked'
        if current != self.fallback_draft:
            self.error = '放弃提及时草稿变化，保留现有内容，未按回车'
            return 'blocked'
        if self.phase == 'mention_fallback_cancel':
            auto.SendKeys('{Esc}',waitTime=0)
            self.phase = 'mention_fallback_select'
        elif self.phase == 'mention_fallback_select':
            auto.SendKeys('{Ctrl}a',waitTime=0)
            self.phase = 'mention_fallback_delete'
        else:
            auto.SendKeys('{Backspace}',waitTime=0)
            self.phase = 'mention_fallback_verify'
            self.deadline = self.clock()+1
        return 'typing'
