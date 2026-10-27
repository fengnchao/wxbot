"""Short clipboard leases for verified paste; keep all original clipboard formats."""
from contextlib import contextmanager
import ctypes as ct
from ctypes import wintypes as wt
import time


def _clipboard_error(reason,operation,*,fmt=None,native=False):
    """Attach only fixed diagnostic labels and numeric codes, never clipboard data."""
    error=OSError(reason)
    error.clipboard_details={'clipboard_operation':operation,'clipboard_error':reason}
    if fmt is not None:error.clipboard_details['clipboard_format']=int(fmt)
    if native:error.clipboard_details['os_error_code']=ct.get_last_error()
    return error


def failure_details(error):
    details={**getattr(error,'clipboard_details',{}),'exception_type':type(error).__name__}
    code=getattr(error,'winerror',None)
    if type(code) is not int:code=getattr(error,'errno',None)
    if type(code) is int:details.setdefault('os_error_code',code)
    return details


class _Medium(ct.Structure):
    _fields_=[('tymed',wt.DWORD),('handle',ct.c_void_p),('owner',ct.c_void_p)]


def _bind(dll,name,result,*args):
    function=getattr(dll,name)
    function.restype=result
    function.argtypes=list(args)
    return function


class WindowsClipboard:
    def __init__(self):
        user=ct.WinDLL('user32',use_last_error=True)
        kernel=ct.WinDLL('kernel32',use_last_error=True)
        ole=ct.WinDLL('ole32',use_last_error=True)
        gdi=ct.WinDLL('gdi32',use_last_error=True)
        self._open=_bind(user,'OpenClipboard',wt.BOOL,wt.HWND)
        self._close=_bind(user,'CloseClipboard',wt.BOOL)
        self._sequence=_bind(user,'GetClipboardSequenceNumber',wt.DWORD)
        self._owner=_bind(user,'GetClipboardOwner',wt.HWND)
        self._owner_process=_bind(user,'GetWindowThreadProcessId',wt.DWORD,wt.HWND,ct.POINTER(wt.DWORD))
        self._enum=_bind(user,'EnumClipboardFormats',wt.UINT,wt.UINT)
        self._get=_bind(user,'GetClipboardData',wt.HANDLE,wt.UINT)
        self._set=_bind(user,'SetClipboardData',wt.HANDLE,wt.UINT,wt.HANDLE)
        self._empty=_bind(user,'EmptyClipboard',wt.BOOL)
        self._alloc=_bind(kernel,'GlobalAlloc',wt.HGLOBAL,wt.UINT,ct.c_size_t)
        self._lock=_bind(kernel,'GlobalLock',ct.c_void_p,wt.HGLOBAL)
        self._unlock=_bind(kernel,'GlobalUnlock',wt.BOOL,wt.HGLOBAL)
        self._free=_bind(kernel,'GlobalFree',wt.HGLOBAL,wt.HGLOBAL)
        self._size=_bind(kernel,'GlobalSize',ct.c_size_t,wt.HGLOBAL)
        self._duplicate=_bind(ole,'OleDuplicateData',wt.HANDLE,wt.HANDLE,ct.c_ushort,wt.UINT)
        self._release=_bind(ole,'ReleaseStgMedium',None,ct.POINTER(_Medium))
        self._copy_enhanced=_bind(gdi,'CopyEnhMetaFileW',wt.HANDLE,wt.HANDLE,wt.LPCWSTR)
        create=_bind(user,'CreateWindowExW',wt.HWND,wt.DWORD,wt.LPCWSTR,wt.LPCWSTR,
                     wt.DWORD,ct.c_int,ct.c_int,ct.c_int,ct.c_int,wt.HWND,wt.HMENU,wt.HINSTANCE,ct.c_void_p)
        self._destroy=_bind(user,'DestroyWindow',wt.BOOL,wt.HWND)
        # A message-only owner avoids OpenClipboard(NULL) / EmptyClipboard ownership issues.
        self.window=create(0,'STATIC','wxbot clipboard',0,0,0,0,0,ct.c_void_p(-3),None,None,None)
        if not self.window:
            raise _clipboard_error('无法创建剪贴板所有者','create_owner',native=True)

    @contextmanager
    def open(self):
        deadline=time.monotonic()+.2
        while not self._open(self.window):
            if time.monotonic()>=deadline:
                raise _clipboard_error('剪贴板正被其他程序占用','open',native=True)
            time.sleep(.005)
        try:
            yield
        finally:
            self._close()

    def sequence(self):
        return int(self._sequence())

    def owner_process_id(self):
        owner=self._owner()
        if not owner:
            return None
        process=wt.DWORD()
        self._owner_process(owner,ct.byref(process))
        return process.value or None

    def read_text(self):
        handle=self._get(13)
        if not handle:
            raise _clipboard_error('剪贴板没有Unicode文本','read_text',fmt=13)
        size=self._size(handle)
        if not 0<size<=1024*1024 or size%2:
            raise _clipboard_error('剪贴板文本长度无效','read_text_size',fmt=13)
        address=self._lock(handle)
        if not address:
            raise _clipboard_error('剪贴板文本不可读','read_text_lock',fmt=13,native=True)
        try:
            return ct.string_at(address,size).decode('utf-16-le').split('\0',1)[0]
        finally:
            self._unlock(handle)

    def owned_sequence(self):
        # A user's copy transfers ownership. Recheck around the version read so a
        # copy racing CloseClipboard can never become our accepted batch version.
        if not self.window or self._owner()!=self.window:
            return None
        sequence=self.sequence()
        return sequence if self._owner()==self.window else None

    def _copy_format(self,fmt,handle):
        base={0x82:2,0x83:3,0x8E:14}.get(fmt,fmt)
        medium={2:16,9:16,3:32,14:64}.get(base,1)
        copy=self._copy_enhanced(handle,None) if base==14 else self._duplicate(handle,base,2)
        if not copy: raise _clipboard_error('剪贴板数据复制失败','duplicate_format',fmt=fmt,native=True)
        return _Medium(medium,copy,None)

    def snapshot(self):
        saved=[]
        try:
            fmt=0
            total=0
            while True:
                ct.set_last_error(0)
                fmt=self._enum(fmt)
                if not fmt:
                    if ct.get_last_error(): raise _clipboard_error('无法枚举剪贴板格式','enumerate_formats',native=True)
                    return saved
                if len(saved)>=128:
                    raise _clipboard_error('剪贴板格式数量超过安全备份上限','snapshot_limit',fmt=fmt)
                if fmt==0x80:
                    raise _clipboard_error('剪贴板包含无法安全备份的OWNERDISPLAY格式','snapshot_format',fmt=fmt)
                handle=self._get(fmt)
                if not handle: raise _clipboard_error('剪贴板数据无法安全备份','get_format',fmt=fmt,native=True)
                base={0x82:2,0x83:3,0x8E:14}.get(fmt,fmt)
                medium={2:16,9:16,3:32,14:64}.get(base,1)
                if medium==1:
                    size=self._size(handle)
                    total+=size
                    if not size:
                        raise _clipboard_error('剪贴板格式的内存大小不可读取','format_size',fmt=fmt,native=True)
                    if total>64*1024*1024:
                        raise _clipboard_error('剪贴板备份数据超过64MB','snapshot_limit',fmt=fmt)
                saved.append((fmt,self._copy_format(fmt,handle)))
        except BaseException:
            self.free_snapshot(saved)
            raise

    def write_text(self,text):
        # Python len() is not UTF-16 code-unit length: allocate bytes, including emoji pairs.
        encoded=text.encode('utf-16-le')+b'\0\0'
        handle=self._alloc(2,len(encoded))
        if not handle: raise _clipboard_error('剪贴板内存分配失败','allocate_text',native=True)
        try:
            address=self._lock(handle)
            if not address: raise _clipboard_error('剪贴板内存不可写','lock_text',native=True)
            try: ct.memmove(address,encoded,len(encoded))
            finally: self._unlock(handle)
            if not self._empty():
                raise _clipboard_error('清空剪贴板以写入正文失败','empty_for_write',native=True)
            if not self._set(13,handle):
                raise _clipboard_error('剪贴板写入失败','set_text',fmt=13,native=True)
            handle=None  # Ownership moved to Windows.
        finally:
            if handle: self._free(handle)

    def restore(self,saved):
        # Keep the backup immutable: a failed SetClipboardData may transfer only some formats.
        # A retry must still be able to restore every original format.
        copies=[]
        try:
            for fmt,medium in saved:
                copies.append((fmt,self._copy_format(fmt,medium.handle)))
            if not self._empty(): raise _clipboard_error('剪贴板恢复失败','empty_for_restore',native=True)
            for fmt,medium in copies:
                if not self._set(fmt,medium.handle): raise _clipboard_error('剪贴板格式恢复失败','restore_format',fmt=fmt,native=True)
                medium.handle=None  # Transferred handles now belong to Windows.
        finally:
            self.free_snapshot(copies)

    def write_dib(self,data):
        handle=self._alloc(2,len(data))
        if not handle: raise _clipboard_error('图片剪贴板内存分配失败','allocate_image',native=True)
        try:
            address=self._lock(handle)
            if not address: raise _clipboard_error('图片剪贴板内存不可写','lock_image',native=True)
            try: ct.memmove(address,data,len(data))
            finally: self._unlock(handle)
            if not self._empty(): raise _clipboard_error('清空图片剪贴板失败','empty_for_image',native=True)
            if not self._set(8,handle): raise _clipboard_error('图片剪贴板写入失败','set_image',fmt=8,native=True)
            handle=None
        finally:
            if handle: self._free(handle)

    def free_snapshot(self,saved):
        for _,medium in saved:
            if medium.handle:
                self._release(ct.byref(medium))
                medium.handle=None

    def dispose(self):
        if self.window:
            self._destroy(self.window)
            self.window=None


_pending=[]  # UI-thread only: preserve backup handles if another program briefly locks the clipboard.
_retry_at=0


def restore_pending(*,force=False):
    global _retry_at
    if _pending and (force or time.monotonic()>=_retry_at):
        _retry_at=time.monotonic()+1
        for lease in list(_pending):
            lease.close()
    return not _pending


class ClipboardLease:
    def __init__(self,text,*,api=None,_image=False):
        if _image and (not isinstance(text,bytes) or not 0<len(text)<=160*1024*1024):
            raise ValueError('无效 DIB 数据')
        if not _image and (not isinstance(text,str) or '\0' in text):
            raise ValueError('粘贴正文必须是无NUL的Unicode字符串')
        if not restore_pending(force=True):
            error=_clipboard_error('上一批剪贴板尚未恢复，停止继续粘贴','pending_restore')
            if _pending:
                previous=getattr(_pending[-1],'restore_failure',{})
                error.clipboard_details.update({key:value for key,value in previous.items() if key!='exception_type'})
                error.clipboard_details['clipboard_error']='上一批剪贴板尚未恢复；'+previous.get('clipboard_error','恢复原因未确认')
            raise error
        self.api=api if api is not None else WindowsClipboard()
        self.saved,self.seq,self.closed=None,None,False
        self.restore_failure={}
        self.degraded=False   # 备份失败时降级为直接覆盖剪贴板，发送后无法恢复
        self.sequence_at_write,self.sequence_after_close,self.sequence_at_check=None,None,None
        try:
            with self.api.open():
                initial_sequence=self.api.sequence()
                try:
                    self.saved=self.api.snapshot()
                except Exception as backup_exc:
                    if _image:
                        raise
                    # 备份失败：降级为不备份、直接覆盖剪贴板，保证消息仍能发出；
                    # 代价是原剪贴板内容无法恢复。
                    self.saved=None
                    self.degraded=True
                    self.restore_failure={'clipboard_error':'剪贴板备份失败，已降级为直接覆盖发送',
                                          'exception_type':type(backup_exc).__name__}
                # 序号核对失败（序号为 0 但已有内容）仍是安全风险，不降级、直接拒绝。
                if initial_sequence==0 and self.saved:
                    raise _clipboard_error('无法核对已有剪贴板内容的序号','initial_sequence')
                try:
                    if _image: self.api.write_dib(text)
                    else: self.api.write_text(text)
                finally:
                    self.seq=self.api.sequence()
                    self.sequence_at_write=self.seq
            self.sequence_after_close=self.api.sequence()
            self._adopt_owned_sequence()
            if not self.seq:
                raise _clipboard_error('写入后无法核对剪贴板序号','committed_sequence')
        except BaseException:
            try:
                self._adopt_owned_sequence()
            finally:
                self.close()
            raise

    def _adopt_owned_sequence(self):
        if self.seq is None:
            return
        owned_sequence=getattr(self.api,'owned_sequence',None)
        if owned_sequence is not None:
            sequence=owned_sequence()
            if sequence is not None:
                self.seq=sequence

    def is_current(self):
        if self.closed or self.seq is None:
            return False
        self.sequence_at_check=self.api.sequence()
        if self.sequence_at_check!=self.seq:
            return False
        owned_sequence=getattr(self.api,'owned_sequence',None)
        return owned_sequence is None or owned_sequence()==self.seq

    def close(self):
        if self.closed: return True
        restore_attempted=False
        try:
            if self.saved is not None and self.seq is not None:
                with self.api.open():
                    if self.is_current():
                        try:
                            restore_attempted=True
                            self.api.restore(self.saved)
                        finally:
                            # Even an interrupted restore may change the sequence. Track our
                            # own writes while holding the lock, so a retry won't mistake them
                            # for a user's copy. A later user copy still takes precedence.
                            self.seq=self.api.sequence()
            if self.saved is not None: self.api.free_snapshot(self.saved)
            self.api.dispose()
        except BaseException as exc:
            self.restore_failure=failure_details(exc)
            # Keep the owned backup alive for the UI loop's next retry; don't overwrite new copies.
            if self not in _pending: _pending.append(self)
            if restore_attempted:
                self._adopt_owned_sequence()
            if not isinstance(exc,Exception): raise
            return False
        self.closed=True
        if self in _pending: _pending.remove(self)
        return True


class ImageClipboardLease(ClipboardLease):
    """CF_DIB lease: fail closed when any original clipboard format cannot be saved."""
    def __init__(self,data,*,api=None):
        super().__init__(data,api=api,_image=True)


class ClipboardReadLease:
    """Snapshot before a native Copy, then accept only that process's new text."""
    def __init__(self,*,api=None):
        if not restore_pending(force=True):
            raise _clipboard_error('上一批剪贴板尚未恢复','pending_restore')
        self.api=api if api is not None else WindowsClipboard()
        self.saved,self.seq,self.closed=None,None,False
        self.expected_process_id=None
        self.restore_failure={}
        try:
            with self.api.open():
                self.before_sequence=self.api.sequence()
                self.saved=self.api.snapshot()
                if self.before_sequence==0 and self.saved:
                    raise _clipboard_error('无法核对已有剪贴板序号','initial_sequence')
        except BaseException:
            self.close()
            raise

    def read(self,*,expected_process_id):
        if self.closed or type(expected_process_id) is not int or expected_process_id<=0:
            raise _clipboard_error('预期剪贴板进程无效','read_owner')
        with self.api.open():
            seq=self.api.sequence()
            if not seq or seq==self.before_sequence or self.api.owner_process_id()!=expected_process_id:
                raise _clipboard_error('剪贴板没有预期进程的新复制内容','read_owner')
            # The native Copy is ours even when its payload cannot be read as
            # text. Retain ownership proof so close can still restore safely.
            self.seq,self.expected_process_id=seq,expected_process_id
            value=self.api.read_text()
            if self.api.sequence()!=seq or self.api.owner_process_id()!=expected_process_id:
                raise _clipboard_error('读取期间剪贴板所有者变化','read_owner')
            return value

    def close(self):
        if self.closed:
            return True
        try:
            if self.saved is not None and self.seq is not None:
                with self.api.open():
                    if self.api.sequence()==self.seq and self.api.owner_process_id()==self.expected_process_id:
                        try:
                            self.api.restore(self.saved)
                        finally:
                            self.seq=self.api.sequence()
                            self.expected_process_id=self.api.owner_process_id()
            if self.saved is not None:
                self.api.free_snapshot(self.saved)
            self.api.dispose()
        except BaseException as exc:
            self.restore_failure=failure_details(exc)
            if self not in _pending:
                _pending.append(self)
            if not isinstance(exc,Exception):
                raise
            return False
        self.closed=True
        if self in _pending:
            _pending.remove(self)
        return True
