"""Telegram Desktop state machines run exclusively in wxbot's UI thread."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import time

import uiautomation as auto

from butler.telegram_relay.settings import load
from butler.telegram_relay.store import RelayStore
from .wechat.locator import find_all
from .wechat.mentions import literal_keys, window_owner


def _plain(value):
    return str(value or '').replace('\u200e','').replace('\u200f','').strip()


def _value(control):
    try:return control.GetValuePattern().Value or ''
    except Exception:return None


def _pid_executable(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_uint,ctypes.c_bool,ctypes.c_uint]
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint)]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return ''
    try:
        output=ctypes.create_unicode_buffer(32768);size=ctypes.c_uint(len(output))
        return output.value if kernel.QueryFullProcessImageNameW(handle,0,output,ctypes.byref(size)) else ''
    finally:kernel.CloseHandle(handle)


class TelegramUI:
    """Calibratable UIA adapter. No OCR identity guessing or clipboard logging."""
    def __init__(self):
        self.window=None
        self._window_route=None

    def user_desktop_available(self):
        try:
            control=auto.ControlFromHandle(auto.GetForegroundWindow())
            return Path(_pid_executable(control.ProcessId)).name.lower() in {'telegram.exe','weixin.exe','wechat.exe'}
        except Exception:return False

    def dialog(self,win,settings):
        name=settings.desktop.get('forward_dialog','转发消息')
        matches=[]
        for root in self.roots(win):
            if _plain(root.Name)==name:matches.append(root)
            matches.extend(find_all(root,{'name':name},max_depth=40))
        if len(matches)!=1:raise ValueError('Telegram转发弹层缺失或重名，请校准forward_dialog')
        return matches[0]

    def locate(self,settings):
        route=(settings.window_title,settings.desktop.get('window_class'))
        if self.window is not None and self._window_route==route and self.window.Exists(0):return self.window
        candidates=[]
        for control in auto.GetRootControl().GetChildren():
            try:
                if Path(_pid_executable(control.ProcessId)).name.lower()!='telegram.exe':continue
                if settings.desktop.get('window_class') and control.ClassName!=settings.desktop['window_class']:continue
                if settings.window_title not in ('Telegram','') and _plain(control.Name)!=_plain(settings.window_title):continue
                candidates.append(control)
            except Exception:continue
        if len(candidates)!=1:raise ValueError('Telegram窗口不唯一或不可访问，请核对监听窗口')
        self.window=candidates[0];self._window_route=route;return self.window

    def roots(self,win):
        result=[win]
        for control in auto.GetRootControl().GetChildren():
            try:
                if (control.NativeWindowHandle!=win.NativeWindowHandle and control.ProcessId==win.ProcessId
                        and window_owner(control.NativeWindowHandle)==win.NativeWindowHandle):result.append(control)
            except Exception:continue
        return result

    def guard(self,win):
        foreground=auto.GetForegroundWindow()
        if foreground==win.NativeWindowHandle:return True
        return any(root.NativeWindowHandle==foreground for root in self.roots(win)[1:])

    def one(self,win,kind,name,*,scoped=True):
        matches=[]
        for root in self.roots(win) if scoped else [win]:
            matches.extend(find_all(root,{'control_type':kind,'name':name},max_depth=40,limit=100))
        if len(matches)!=1:raise ValueError('Telegram控件缺失或重名：'+name)
        return matches[0]

    def scan(self,channel,settings):return _Scan(self,channel,settings)

    def selected_recipients(self,dialog):
        rows=find_all(dialog,{'control_type':'ListItemControl'},max_depth=40,limit=200)
        selected=[]
        for row in rows:
            try:is_selected=bool(row.GetSelectionItemPattern().IsSelected)
            except Exception:
                try:is_selected=row.GetTogglePattern().ToggleState==1
                except Exception:raise ValueError('转发收件人未暴露选中状态，需校准，未点击发送')
            if is_selected:selected.append(row)
        return selected

    def recipient_username(self,row,settings):
        # A display name can imitate @username. Only a calibrated metadata field
        # with a readable value proves the bot's actual username.
        field=settings.desktop.get('recipient_username_field','用户名')
        controls=find_all(row,{'name':field},max_depth=8,limit=3)
        if len(controls)!=1:return ''
        return _plain(_value(controls[0])).lstrip('@').casefold()

    def forward(self,channel,payload,settings,on_source,on_submit):
        return _Forward(self,channel,payload,settings,on_source,on_submit)

    def describe(self,win,settings):
        listing=self.one(win,'ListControl',settings.desktop.get('message_list','消息'),scoped=False)
        result=[]
        for row in listing.GetChildren():
            if row.ControlTypeName!='ListItemControl':continue
            fields={}
            for child in row.GetChildren():
                value=_value(child)
                if value is not None:fields[child.Name]=value
            if not fields.get('消息') and not fields.get('媒体类型'):continue
            facts={key:fields.get(key,'') for key in ('消息','时间','媒体类型','尺寸','收件人')}
            key=hashlib.sha256(json.dumps(facts,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            result.append({'key':key,'text':facts['消息'],'time':facts['时间'],'media_type':facts['媒体类型'],
                'runtime_id':list(row.GetRuntimeId()),'source_url':''})
            if len(result)>500:raise ValueError('加载消息过多，无法可靠建立边界')
        return result

    def message_row(self,win,settings,payload):
        listing=self.one(win,'ListControl',settings.desktop.get('message_list','消息'),scoped=False)
        matches=[row for row in listing.GetChildren() if list(row.GetRuntimeId())==payload['runtime_id']]
        if len(matches)!=1:raise ValueError('原消息控件已变化，需核对来源，不按同文猜测')
        # Re-read semantic payload, not mutable view/reaction counters.
        descriptions=self.describe(win,settings)
        if not any(item['runtime_id']==payload['runtime_id'] and item['key']==payload['key'] for item in descriptions):
            raise ValueError('原消息内容已变化，停止转发')
        return matches[0]


class _Scan:
    submitted=False
    requires_review=False
    def __init__(self,driver,channel,settings):
        self.driver,self.channel,self.settings=driver,channel,settings
        self.phase='activate';self.win=None;self.search=None;self.deadline=time.monotonic()+8
        self.query_written=False

    def step(self):
        if time.monotonic()>self.deadline:raise ValueError('频道选择或控件校准超时')
        if self.phase=='activate':
            self.win=self.driver.locate(self.settings);self.win.SetActive();self.phase='channel';return None
        if not self.driver.guard(self.win):raise ValueError('Telegram前台窗口变化，暂停桌面操作')
        if self.phase=='channel':
            if _plain(self.win.Name)==_plain(self.channel.name):self.phase='read';return None
            self.search=self.driver.one(self.win,'EditControl',self.settings.desktop.get('chat_search','搜索'))
            if _value(self.search)!='':raise ValueError('Telegram搜索框已有用户内容，未覆盖')
            self.search.Click(simulateMove=False);self.phase='query';return None
        if self.phase=='query':
            if not self.search.HasKeyboardFocus or _value(self.search)!='':raise ValueError('频道搜索焦点或草稿变化')
            self.query_written=True
            auto.SendKeys(literal_keys('@'+self.channel.username if self.channel.username else self.channel.name),interval=0,waitTime=0)
            self.phase='pick';return None
        if self.phase=='pick':
            query='@'+self.channel.username if self.channel.username else self.channel.name
            if not self.search.HasKeyboardFocus or _value(self.search)!=query:raise ValueError('频道搜索内容变化')
            # Exact named row, never Enter/first-result selection.
            row=self.driver.one(self.win,'ListItemControl',self.settings.desktop.get('channel_row',self.channel.name))
            row.Click(simulateMove=False);self.phase='verify';return None
        if self.phase=='verify':
            if _plain(self.win.Name)!=_plain(self.channel.name):raise ValueError('选中频道标题不匹配')
            self.phase='read';return None
        if _plain(self.win.Name)!=_plain(self.channel.name):raise ValueError('读取前频道对象变化')
        return {'state':'scanned','observations':self.driver.describe(self.win,self.settings)}

    def close(self):
        if self.search is not None:
            if not self.query_written:return True
            value=_value(self.search)
            if value is None:
                try:return not self.search.Exists(0)
                except Exception:return False
            query='@'+self.channel.username if self.channel.username else self.channel.name
            if value==query and self.driver.guard(self.win) and self.search.HasKeyboardFocus:
                auto.SendKeys('{Ctrl}a',waitTime=0)
                if not self.driver.guard(self.win) or _value(self.search)!=query or not self.search.HasKeyboardFocus:return False
                auto.SendKeys('{Backspace}',waitTime=0)
                return _value(self.search)==''
            if _value(self.search):return False
        return True


class _Forward:
    def __init__(self,driver,channel,payload,settings,on_source,on_submit):
        self.driver,self.channel,self.payload,self.settings=driver,channel,payload,settings
        self.on_source,self.on_submit=on_source,on_submit
        self.scan=_Scan(driver,channel,settings);self.phase='navigate';self.win=None
        self.clipboard=None;self.submitted=False;self.requires_review=False;self.deadline=0
        self.dialog=None
        self.target=None

    def step(self):
        if self.phase=='navigate':
            result=self.scan.step()
            if result is None:return None
            self.win=self.scan.win;self.phase='context_link';self.deadline=time.monotonic()+20;return None
        if not self.driver.guard(self.win):raise ValueError('Telegram转发对象或前台窗口变化')
        if self.phase not in {'send','verify'} and _plain(self.win.Name)!=_plain(self.channel.name):
            raise ValueError('Telegram当前频道已变化，停止转发')
        if time.monotonic()>self.deadline:raise ValueError('Telegram转发控件等待超时，请校准')
        if self.phase=='context_link':
            from .wechat.clipboard import ClipboardReadLease
            self.clipboard=ClipboardReadLease()
            self.requires_review=True
            self.driver.message_row(self.win,self.settings,self.payload).RightClick(simulateMove=False)
            self.phase='copy_link';return None
        if self.phase=='copy_link':
            self.driver.one(self.win,'MenuItemControl',self.settings.desktop.get('copy_link_menu','复制消息链接')).Click(simulateMove=False)
            self.phase='read_link';return None
        if self.phase=='read_link':
            url=self.clipboard.read(expected_process_id=self.win.ProcessId)
            if not self.clipboard.close():raise ValueError('Telegram复制链接后剪贴板未能恢复')
            self.clipboard=None
            self.requires_review=False
            match=re.fullmatch(r'https://t\.me/(?:([A-Za-z0-9_]+)/|c/(\d+)/)(\d+)',url.strip())
            if not match:raise ValueError('无法取得可靠来源消息链接')
            if self.channel.username and (not match[1] or match[1].casefold()!=self.channel.username.casefold()):
                raise ValueError('来源频道用户名与复制链接不符')
            if not self.channel.username and (not match[2] or str(self.channel.chat_id)!='-100'+match[2]):
                raise ValueError('私有频道数字身份不符')
            if not self.on_source(match[3]):return {'state':'duplicate'}
            self.phase='context_forward';return None
        if self.phase=='context_forward':
            self.requires_review=True
            self.driver.message_row(self.win,self.settings,self.payload).RightClick(simulateMove=False)
            self.phase='forward_menu';return None
        if self.phase=='forward_menu':
            self.driver.one(self.win,'MenuItemControl',self.settings.desktop.get('forward_menu','转发')).Click(simulateMove=False)
            self.phase='recipient_focus';return None
        if self.phase=='recipient_focus':
            self.dialog=self.driver.dialog(self.win,self.settings)
            self.search=self.driver.one(self.dialog,'EditControl',self.settings.desktop.get('recipient_search','搜索'),scoped=False)
            if _value(self.search)!='':raise ValueError('转发选择器已有内容，未覆盖')
            self.search.Click(simulateMove=False);self.phase='recipient_query';return None
        if self.phase=='recipient_query':
            if not self.search.HasKeyboardFocus or _value(self.search)!='':raise ValueError('机器人搜索焦点或草稿变化')
            auto.SendKeys(literal_keys('@'+self.settings.bot_username),interval=0,waitTime=0)
            self.phase='recipient_pick';return None
        if self.phase=='recipient_pick':
            if not self.search.HasKeyboardFocus or _value(self.search)!='@'+self.settings.bot_username:
                raise ValueError('机器人搜索内容变化')
            row=self.driver.one(self.dialog,'ListItemControl',self.settings.desktop.get('recipient_row','@'+self.settings.bot_username),scoped=False)
            if self.driver.recipient_username(row,self.settings)!=self.settings.bot_username.casefold():
                raise ValueError('机器人结果未暴露匹配用户名字段，需校准')
            if self.driver.selected_recipients(self.dialog):raise ValueError('转发框已有选中收件人，未继续发送')
            # Some Telegram versions submit immediately when selecting one recipient.
            # Persist before the first potentially submitting native action.
            self.on_submit();self.submitted=True;self.target=list(row.GetRuntimeId())
            row.Click(simulateMove=False);self.phase='send';return None
        if self.phase=='send':
            if not self.dialog.Exists(0):
                self.requires_review=False
                return {'state':'awaiting_bot'}
            if _plain(self.win.Name)!=_plain(self.channel.name):raise ValueError('提交前频道已变化')
            selected=self.driver.selected_recipients(self.dialog)
            if len(selected)!=1 or list(selected[0].GetRuntimeId())!=self.target:
                raise ValueError('转发收件人不是唯一已验证机器人，未点击发送')
            if self.driver.recipient_username(selected[0],self.settings)!=self.settings.bot_username.casefold():
                raise ValueError('提交前机器人用户名字段已变化')
            button=self.driver.one(self.dialog,'ButtonControl',self.settings.desktop.get('send_button','发送'),scoped=False)
            button.Click(simulateMove=False);self.phase='verify';self.deadline=time.monotonic()+3;return None
        try:still_open=self.dialog.Exists(0)
        except Exception:still_open=False
        if not still_open:
            self.requires_review=False
            return {'state':'awaiting_bot'}
        if time.monotonic()>self.deadline:return {'state':'uncertain','error':'Telegram提交后未能确认转发窗口关闭'}
        return None

    def close(self):
        clipboard_ok=self.clipboard.close() if self.clipboard is not None else True
        return self.scan.close() and clipboard_ok


class DesktopRelay:
    def __init__(self,settings_path,state_dir,driver=None,*,clock=time.time):
        self.settings_path=Path(settings_path);self.state_dir=Path(state_dir);self.driver=driver or TelegramUI()
        self.clock=clock;self.active=None;self.task=None;self.busy=False;self.next_scan={};self.last_channel=''
        self.store=None;self.error='';self._last_status=0;self._route=None
        self._prefer_scan=True
        # Recover persisted UI ownership before MainInbox considers either app.
        if (self.state_dir/'desktop.sqlite3').is_file():
            self.store=RelayStore(self.state_dir/'desktop.sqlite3');self.store.recover()

    @property
    def requires_ui_review(self):return bool(self.store and self.store.has_hold())

    def _settings(self):return load(self.settings_path,missing_ok=True)

    def _receipts(self,settings):
        try:
            path=self.state_dir.parent/'telegram-bot'/'forward-receipts.json'
            if path.stat().st_size>1048576:return []
            data=json.loads(path.read_text(encoding='utf-8'))
            if data.get('bot_id')!=settings.bot_id:return []
            rows=data.get('receipts',[])
            return [row for row in rows if isinstance(row,dict)] if isinstance(rows,list) and len(rows)<=2000 else []
        except (OSError,ValueError,TypeError):return []

    def _release(self,error=''):
        try:clean=self.active.close()
        except Exception:clean=False
        if not clean or getattr(self.active,'requires_review',False):
            if self.task:self.store.finish(self.task['id'],'uncertain' if getattr(self.active,'submitted',False) else 'blocked',
                                           error or 'Telegram界面或剪贴板尚未恢复，需先核对')
            self.store.hold(self.task['id'] if self.task else 'desktop',self.task['channel'] if self.task else self.last_channel,
                            error or 'Telegram界面或剪贴板尚未恢复，需先核对')
        self.store.end_ui()
        self.active=None;self.task=None;self.busy=False

    def close(self):
        if self.active is not None:
            if self.task:self.store.finish(self.task['id'],'uncertain' if getattr(self.active,'submitted',False) else 'blocked','桌面任务已停止，需核对')
            self._release('桌面任务已停止，需核对')

    def _publish(self,settings):
        now=self.clock()
        if now-self._last_status<1:return
        self._last_status=now
        status=self.store.status() if self.store else {'counts':{},'channels':[]}
        status.update(enabled=settings.enabled,at=now,current=self.task['id'] if self.task else '',
                      phase=getattr(self.active,'phase','idle'),error=self.error)
        self.state_dir.mkdir(parents=True,exist_ok=True)
        temp=self.state_dir/'desktop-status.tmp'
        temp.write_text(json.dumps(status,ensure_ascii=False),encoding='utf-8')
        os.replace(temp,self.state_dir/'desktop-status.json')

    def tick(self):
        try:
            settings=self._settings()
            if self.store:self.store.reconcile_receipts(self._receipts(settings),now=self.clock())
            if not settings.enabled and not self.busy:return False
            if self.requires_ui_review:return False
            if self.store is None:
                self.store=RelayStore(self.state_dir/'desktop.sqlite3');self.store.recover()
            channels=[c for c in settings.channels if c.enabled]
            self.store.sync_channels(channels)
            route=(settings.window_title,settings.bot_id,settings.bot_username,tuple(channels))
            if self.active is not None and (not settings.enabled or route!=self._route):
                state='uncertain' if getattr(self.active,'submitted',False) else 'cancelled'
                if self.task:self.store.finish(self.task['id'],state,'转发配置已改变')
                self._release('配置改变，需先清理Telegram界面')
                return True
            if self.active is None:
                if hasattr(self.driver,'user_desktop_available') and not self.driver.user_desktop_available():return False
                identity_path=self.state_dir.parent/'telegram-bot'/'bot-identity.json'
                identity=json.loads(identity_path.read_text(encoding='utf-8'))
                if identity.get('bot_id')!=settings.bot_id or str(identity.get('username','')).casefold()!=settings.bot_username.casefold():
                    raise ValueError('配置机器人与接收器 getMe 身份不符，请核对机器人配置')
                due=[c for c in channels if self.next_scan.get(c.key,0)<=self.clock()]
                self.task=None if due and self._prefer_scan else self.store.claim([c.key for c in channels])
                if self.task:
                    channel=next(c for c in channels if c.key==self.task['channel'])
                    self.store.begin_ui(self.task['id'],channel.key)
                    self._prefer_scan=True
                    self.active=self.driver.forward(channel,self.task['payload'],settings,
                        lambda source:self.store.bind_source(self.task['id'],source,source_chat_id=channel.chat_id,source_username=channel.username),
                        lambda:self.store.mark_submitted(self.task['id']))
                else:
                    if not due:return False
                    if self.last_channel in [c.key for c in due]:
                        index=[c.key for c in due].index(self.last_channel)+1;due=due[index:]+due[:index]
                    channel=due[0];self.last_channel=channel.key
                    self.next_scan[channel.key]=self.clock()+settings.poll_interval
                    self.store.begin_ui('desktop',channel.key)
                    self._prefer_scan=False
                    self.active=self.driver.scan(channel,settings)
                self._route=route;self.busy=True;self.error=''
            result=self.active.step()
            if result is None:return True
            if result['state']=='scanned':self.store.capture(self.last_channel,result['observations'])
            elif self.task:self.store.finish(self.task['id'],result['state'],result.get('error',''))
            self._release(result.get('error',''))
            return True
        except Exception as exc:
            self.error=str(exc)[:300] if isinstance(exc,(ValueError,FileNotFoundError)) else type(exc).__name__
            if self.active:
                if self.task:self.store.finish(self.task['id'],'uncertain' if getattr(self.active,'submitted',False) else 'blocked',self.error)
                self._release(self.error)
            self.busy=False
            return False
        finally:
            try:self._publish(self._settings())
            except Exception:pass
