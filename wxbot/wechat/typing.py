"""UI 线程分批粘贴；step 每次最多输入一批，不 sleep 等待下一批。"""
import time

import uiautomation as auto
from ..config import validate_typing_config
from .clipboard import ClipboardLease,failure_details


class TypingSession:
    def __init__(self, chat, win, edit, text, *, mention_name='', clock=time.monotonic):
        self.chunk_size, self.chunk_interval = validate_typing_config(getattr(chat, 'wcfg', {}))
        self.chat, self.win, self.edit, self.text = chat, win, edit, text
        self.clock = clock
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        self.normalized = normalized
        self.chunks = [normalized[i:i + self.chunk_size]
                       for i in range(0, len(normalized), self.chunk_size)]
        self.index = 0
        self.next_due = clock()
        self.state = "typing"
        self.error = ""
        self.enter_attempted = False
        self.submitted_text = None
        self.before_enter = None
        self.on_verified_draft = None
        self._verify_prefix = False
        self._verify_deadline = 0
        self._clipboard = None
        self.failure_details = {}
        self.phase = 'input_guard'
        self.mention_name = mention_name
        self.mention_verified = False
        self._mention_prefix = ''
        self._mention_identity = None
        if mention_name:
            from .mentions import MentionSelection
            self._mention = MentionSelection(chat, win, edit, mention_name, clock=clock)
        else:
            self._mention = None

    def _draft(self):
        if self.mention_verified:
            from .mentions import rich_draft
            proof = rich_draft(self.edit, self.mention_name)
            if proof is None or proof[1] != self._mention_identity:
                return None
            raw = proof[0]
            return raw[len(self._mention_prefix):] if raw.startswith(self._mention_prefix) else None
        value = self.chat._input_text(self.edit)
        return value.replace("\r\n", "\n").replace("\r", "\n") if value is not None else None

    def close(self):
        if self._clipboard is None:
            return True
        if self._clipboard.close():
            self._clipboard = None
            return True
        self.failure_details.update(getattr(self._clipboard,'restore_failure',{}))
        return False

    def _target_or_focus_error(self, prefix):
        probe=getattr(self.chat,'send_diagnostics',None)
        if probe is not None:
            try:self.failure_details.update(probe(self.win,self.edit))
            except Exception:pass
        if not self.chat.target_is_current(self.win):
            data=self.failure_details
            if data.get('actual_contact') is None and probe is not None:
                return prefix+'当前聊天标题无法读取，未按回车'
            if data.get('actual_contact')!=data.get('expected_contact'):
                return prefix+f"聊天对象变化（预期={data.get('expected_contact')}，实际={data.get('actual_contact')}），未按回车"
            if data.get('actual_group') is not None and data.get('actual_group')!=data.get('expected_group'):
                return prefix+'私聊/群聊类型与收件目标不一致，未按回车'
            if data.get('foreground_hwnd')!=data.get('expected_hwnd'):
                return prefix+f"前台窗口变化（预期={data.get('expected_hwnd')}，实际={data.get('foreground_hwnd')}），未按回车"
            return prefix + '聊天对象、类型或前台窗口变化，未按回车'
        return prefix + '输入焦点不在消息输入框，未按回车'

    def step(self):
        if self.state != "typing":
            return self.state
        try:
            self.phase='input_guard'
            if not self.chat._can_send(self.win, self.edit):
                self.state, self.error = "blocked", self._target_or_focus_error('输入前')
                self.close()
                return self.state
            if self._mention is not None:
                self.phase = self._mention.phase
                result = self._mention.step()
                if result == 'blocked':
                    self.state, self.error = 'blocked', self._mention.error
                    self.failure_details['manual_required'] = True
                    return self.state
                if result == 'plain':
                    self.failure_details.update(mention_fallback=self._mention.fallback_reason,mention_verified=False)
                    self.mention_name = ''
                    self._mention = None
                    return self.state
                if result != 'selected':
                    return self.state
                self._mention_prefix, self._mention_identity = self._mention.proof
                self.mention_verified = True
                self.failure_details['mention_verified'] = True
                self._mention = None
                return self.state
            if self._verify_prefix:
                self.phase='verify_prefix'
                expected = self.normalized[:self.index * self.chunk_size]
                if self._draft() == expected:
                    if self.on_verified_draft is not None and not self.mention_name:
                        self.on_verified_draft(expected)
                    if not self.close():
                        self.state,self.error = 'blocked','剪贴板暂时无法恢复，已保留草稿，未按回车'
                        return self.state
                    self._verify_prefix = False
                elif self.clock() < self._verify_deadline:
                    return self.state
                else:
                    self.state = "blocked"
                    self.error = "输入内容不可读或与预期不符（可能丢字/标点变化），未按回车，已保留草稿"
                    self.close()
                    return self.state
            if self.clock() < self.next_due:
                return self.state
            if self.index < len(self.chunks):
                self.phase='paste_guard'
                if self._draft() != self.normalized[:self.index * self.chunk_size]:
                    self.state,self.error='blocked','粘贴前输入内容变化或不可读，已保留草稿，未按回车'
                    return self.state
                self.phase='clipboard_acquire'
                self._clipboard = ClipboardLease(self.chunks[self.index])
                self.phase='paste_guard'
                if not self.chat._can_send(self.win,self.edit):
                    self.state,self.error='blocked',self._target_or_focus_error('粘贴前')
                    self.close()
                    return self.state
                if self._draft() != self.normalized[:self.index * self.chunk_size]:
                    self.state, self.error = 'blocked', '粘贴前草稿或提及对象变化，未粘贴、未按回车'
                    self.close()
                    return self.state
                if not self._clipboard.is_current():
                    self.failure_details.update(clipboard_write=self._clipboard.sequence_at_write,
                        clipboard_committed=self._clipboard.seq,clipboard_checked=self._clipboard.sequence_at_check)
                    self.state,self.error='blocked',(
                        '粘贴前剪贴板所有者或序号变化'
                        f'（写入时={self._clipboard.sequence_at_write}，完成时={self._clipboard.seq}，'
                        f'关闭后={self._clipboard.sequence_after_close}，'
                        f'校验时={self._clipboard.sequence_at_check}），未粘贴、未按回车')
                    self.close()
                    return self.state
                self.phase='paste_key'
                auto.SendKeys('{Ctrl}v',interval=0.01,waitTime=0.05)
                self.index += 1
                self._verify_prefix = True
                self._verify_deadline = self.clock() + 0.75
                self.next_due = self.clock() + (self.chunk_interval if self.index < len(self.chunks) else 0.05)
            else:
                self.phase='before_enter'
                if self._draft() != self.normalized:
                    self.state, self.error = "blocked", "回车前输入内容变化，已保留草稿"
                    return self.state
                visible_prefix = self._mention_prefix
                if self.mention_verified and visible_prefix.startswith('\ufffc'):
                    visible_prefix = '@' + self.mention_name + visible_prefix[1:]
                self.submitted_text = visible_prefix + self.normalized
                if self.before_enter is not None:
                    if self.before_enter() is False:
                        return self.state
                if not self.chat._can_send(self.win, self.edit) or self._draft() != self.normalized:
                    self.state, self.error = "blocked", "回车前对象、焦点或输入内容变化，已保留草稿"
                    return self.state
                self.enter_attempted = True
                self.phase='enter'
                auto.SendKeys("{Enter}", waitTime=0.1)
                self.state = "submitted"
        except Exception as exc:
            self.state = "uncertain" if self.enter_attempted else "blocked"
            self.failure_details.update(failure_details(exc))
            cause=self.failure_details.get('clipboard_error')
            self.error = (type(exc).__name__ if self.enter_attempted else
                          f'分批粘贴失败（{type(exc).__name__}）'+(f'：{cause}' if cause else '')+'，未按回车，已保留草稿')
            self.close()
        finally:
            if self.state in {'blocked','uncertain'}:
                if self.mention_name and not self.enter_attempted:
                    self.failure_details['manual_required'] = True
                self.failure_details.update(phase=self.phase,enter_attempted=self.enter_attempted,
                    characters_entered=min(self.index*self.chunk_size,len(self.normalized)))
        return self.state
