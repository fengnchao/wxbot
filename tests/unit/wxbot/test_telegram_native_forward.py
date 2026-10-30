"""Native forwarding safety with an in-memory control tree; never desktop/clipboard."""
from itertools import count
import time
from types import SimpleNamespace

import pytest

from wxbot.telegram_desktop import TelegramUI, _Forward


class Control:
    ids = count(1)

    def __init__(self, name, kind='PaneControl', *, children=(), events=None):
        self.Name, self.ControlTypeName = name, kind
        self.children, self.events = list(children), events if events is not None else []
        self.runtime_id = next(self.ids)
        self.NativeWindowHandle, self.ProcessId = self.runtime_id, 123
        self.HasKeyboardFocus = False
        self.value, self.selected, self.exists = '', False, True
        self.after_click = None

    def GetChildren(self): return self.children
    def GetRuntimeId(self): return [self.runtime_id]
    def GetValuePattern(self): return SimpleNamespace(Value=self.value)
    def GetSelectionItemPattern(self): return SimpleNamespace(IsSelected=self.selected)
    def Exists(self, timeout): return self.exists

    def Click(self, **kwargs):
        self.events.append('click:'+self.Name)
        self.HasKeyboardFocus = True
        if self.ControlTypeName == 'ListItemControl':
            self.selected = True
        if self.after_click:
            self.after_click()

    def RightClick(self, **kwargs): self.events.append('rightclick:'+self.Name)


def scenario(monkeypatch, *, auto_send=False):
    import wxbot.telegram_desktop as module
    events = []
    search = Control('搜索', 'EditControl', events=events)
    row = Control('@CurrentBot', 'ListItemControl', events=events)
    metadata=Control('用户名','TextControl');metadata.value='@CurrentBot';row.children=[metadata]
    button = Control('发送', 'ButtonControl', events=events)
    dialog = Control('转发消息', children=[search,row,button], events=events)
    menu = Control('转发', 'MenuItemControl', events=events)
    copy = Control('复制消息链接', 'MenuItemControl', events=events)
    message = Control('source message', 'ListItemControl', events=events)
    win = Control('Source', children=[dialog,menu,copy], events=events)

    class Driver(TelegramUI):
        def guard(self, win): return True
        def roots(self, win): return [win]
        def message_row(self, win, settings, payload): return message

    def send_keys(keys, **kwargs):
        events.append('keys:'+keys)
        search.value = keys
    monkeypatch.setattr(module.auto, 'SendKeys', send_keys)
    channel = SimpleNamespace(name='Source', username='source', chat_id=-100123)
    settings = SimpleNamespace(bot_username='CurrentBot', desktop={})
    operation = _Forward(Driver(), channel, {}, settings,
        lambda source: events.append('source:'+source) or True, lambda: events.append('submitted'))
    operation.phase, operation.win = 'forward_menu', win
    operation.deadline = time.monotonic()+20
    if auto_send:
        row.after_click = lambda: setattr(dialog, 'exists', False)
    return operation, events, dialog, search, row, button, win


def pick(operation):
    for phase in ('forward_menu','recipient_focus','recipient_query','recipient_pick'):
        assert operation.phase == phase
        assert operation.step() is None


def test_unique_verified_bot_is_marked_submitting_before_native_recipient_click(monkeypatch):
    operation, events, dialog, search, row, button, win = scenario(monkeypatch)
    pick(operation)
    assert operation.submitted
    assert events.index('submitted') < events.index('click:@CurrentBot')
    assert operation.step() is None  # Unique selected recipient allows the explicit send.
    assert 'click:发送' in events
    dialog.exists = False
    assert operation.step() == {'state':'awaiting_bot'}
    assert not operation.requires_review


def test_recipient_click_that_closes_dialog_waits_for_real_bot_receipt(monkeypatch):
    operation, events, dialog, search, row, button, win = scenario(monkeypatch, auto_send=True)
    pick(operation)
    assert operation.step() == {'state':'awaiting_bot'}
    assert 'click:发送' not in events
    assert events.index('submitted') < events.index('click:@CurrentBot')


@pytest.mark.parametrize('username', ['', '@WrongBot'])
def test_missing_or_wrong_exposed_bot_username_cannot_select_or_submit(monkeypatch, username):
    operation, events, dialog, search, row, button, win = scenario(monkeypatch)
    row.Name = 'Display name'
    row.children = [Control(username, 'TextControl')] if username else []
    operation.settings.desktop['recipient_row'] = 'Display name'
    for _ in range(3): operation.step()
    with pytest.raises(ValueError, match='用户名'):
        operation.step()
    assert 'submitted' not in events and 'click:Display name' not in events and 'click:发送' not in events


def test_ambiguous_bot_results_fail_closed_before_any_recipient_click(monkeypatch):
    operation, events, dialog, search, row, button, win = scenario(monkeypatch)
    dialog.children.append(Control('@CurrentBot','ListItemControl',events=events))
    for _ in range(3): operation.step()
    with pytest.raises(ValueError, match='重名'):
        operation.step()
    assert 'submitted' not in events and 'click:@CurrentBot' not in events


@pytest.mark.parametrize('before_pick', [True,False])
def test_extra_selected_recipient_never_reaches_send_button(monkeypatch, before_pick):
    operation, events, dialog, search, row, button, win = scenario(monkeypatch)
    extra = Control('@OtherRecipient','ListItemControl',events=events)
    dialog.children.append(extra)
    if before_pick:
        extra.selected = True
        for _ in range(3): operation.step()
        with pytest.raises(ValueError, match='已有选中'):
            operation.step()
        assert 'submitted' not in events and 'click:@CurrentBot' not in events
    else:
        pick(operation)
        extra.selected = True
        with pytest.raises(ValueError, match='不是唯一'):
            operation.step()
    assert 'click:发送' not in events


def test_copied_link_from_wrong_channel_is_rejected_and_fake_clipboard_restored(monkeypatch):
    operation, events, dialog, search, row, button, win = scenario(monkeypatch)
    class Lease:
        def __init__(self): events.append('clipboard-acquired')
        def read(self, **kwargs):
            assert kwargs['expected_process_id'] == 123
            return 'https://t.me/wrong_channel/42'
        def close(self): events.append('clipboard-restored'); return True
    monkeypatch.setattr('wxbot.wechat.clipboard.ClipboardReadLease', Lease)
    operation.phase = 'context_link'
    assert operation.step() is None
    assert operation.step() is None
    with pytest.raises(ValueError, match='来源频道'):
        operation.step()
    assert 'clipboard-restored' in events
    assert not any(item.startswith('source:') for item in events)
    assert 'submitted' not in events and 'click:转发' not in events


@pytest.mark.parametrize('phase', ['forward_menu','recipient_focus'])
def test_missing_calibrated_control_requests_calibration_without_guess_click(monkeypatch, phase):
    operation, events, dialog, search, row, button, win = scenario(monkeypatch)
    operation.phase = phase
    if phase == 'forward_menu':
        win.children = [dialog]
    else:
        dialog.children.remove(search)
    with pytest.raises(ValueError, match='控件缺失'):
        operation.step()
    assert events == [] and not operation.submitted


def test_display_name_spoof_is_not_bot_identity(monkeypatch):
    operation,events,dialog,search,row,button,win=scenario(monkeypatch)
    row.children[0].value='@different_user'
    for _ in range(3):operation.step()
    with pytest.raises(ValueError,match='用户名'):operation.step()
    assert 'submitted' not in events and 'click:@CurrentBot' not in events


def test_channel_switch_inside_same_window_stops_before_native_actions(monkeypatch):
    operation,events,dialog,search,row,button,win=scenario(monkeypatch)
    operation.phase='context_forward';win.Name='Other channel'
    with pytest.raises(ValueError,match='频道已变化'):operation.step()
    assert events==[]
