"""Short clipboard leases for verified paste; keep all original clipboard formats."""
from contextlib import contextmanager
import ctypes as ct
from ctypes import wintypes as wt
import time


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
            raise OSError('无法创建剪贴板所有者')

    @contextmanager
    def open(self):
        deadline=time.monotonic()+.2
        while not self._open(self.window):
            if time.monotonic()>=deadline:
                raise OSError('剪贴板正被其他程序占用')
            time.sleep(.005)
        try:
            yield
        finally:
            self._close()

    def sequence(self):
        return int(self._sequence())

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
        if not copy: raise OSError('剪贴板数据复制失败')
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
                    if ct.get_last_error(): raise OSError('无法枚举剪贴板格式')
                    return saved
                if len(saved)>=128 or fmt==0x80:
                    raise OSError('剪贴板格式无法安全备份')
                handle=self._get(fmt)
                if not handle: raise OSError('剪贴板数据无法安全备份')
                base={0x82:2,0x83:3,0x8E:14}.get(fmt,fmt)
                medium={2:16,9:16,3:32,14:64}.get(base,1)
                if medium==1:
                    size=self._size(handle)
                    total+=size
                    if not size or total>64*1024*1024:
                        raise OSError('剪贴板数据无法安全备份或超过64MB')
                saved.append((fmt,self._copy_format(fmt,handle)))
        except BaseException:
            self.free_snapshot(saved)
            raise

    def write_text(self,text):
        # Python len() is not UTF-16 code-unit length: allocate bytes, including emoji pairs.
        encoded=text.encode('utf-16-le')+b'\0\0'
        handle=self._alloc(2,len(encoded))
        if not handle: raise OSError('剪贴板内存分配失败')
        try:
            address=self._lock(handle)
            if not address: raise OSError('剪贴板内存不可写')
            try: ct.memmove(address,encoded,len(encoded))
            finally: self._unlock(handle)
            if not self._empty() or not self._set(13,handle):
                raise OSError('剪贴板写入失败')
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
            if not self._empty(): raise OSError('剪贴板恢复失败')
            for fmt,medium in copies:
                if not self._set(fmt,medium.handle): raise OSError('剪贴板格式恢复失败')
                medium.handle=None  # Transferred handles now belong to Windows.
        finally:
            self.free_snapshot(copies)

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
    def __init__(self,text,*,api=None):
        if not isinstance(text,str) or '\0' in text:
            raise ValueError('粘贴正文必须是无NUL的Unicode字符串')
        if not restore_pending(force=True):
            raise OSError('上一批剪贴板尚未恢复，停止继续粘贴')
        self.api=api if api is not None else WindowsClipboard()
        self.saved,self.seq,self.closed=None,None,False
        self.sequence_at_write,self.sequence_after_close,self.sequence_at_check=None,None,None
        try:
            with self.api.open():
                if self.api.sequence()==0: raise OSError('无法核对剪贴板序号')
                self.saved=self.api.snapshot()
                try:
                    self.api.write_text(text)
                finally:
                    self.seq=self.api.sequence()
                    self.sequence_at_write=self.seq
            self.sequence_after_close=self.api.sequence()
            self._adopt_owned_sequence()
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
            # Keep the owned backup alive for the UI loop's next retry; don't overwrite new copies.
            if self not in _pending: _pending.append(self)
            if restore_attempted:
                self._adopt_owned_sequence()
            if not isinstance(exc,Exception): raise
            return False
        self.closed=True
        if self in _pending: _pending.remove(self)
        return True
