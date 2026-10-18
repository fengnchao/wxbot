from contextlib import contextmanager
from copy import deepcopy

import pytest


class FakeClipboard:
    def __init__(self):
        self.data={13:'original text',49152:b'<b>rich content</b>',2:b'bitmap'}
        self.seq=1
        self.locked=False
        self.busy=False
        self.disposed=False
        self.fail_write=False
        self.fail_restore=False
    @contextmanager
    def open(self):
        if self.busy: raise OSError('clipboard busy')
        assert not self.locked
        self.locked=True
        try: yield
        finally: self.locked=False
    def sequence(self): return self.seq
    def snapshot(self):
        assert self.locked
        return deepcopy(self.data)
    def write_text(self,text):
        assert self.locked
        self.data={13:text};self.seq+=1
        if self.fail_write: raise OSError('write failed')
    def restore(self,snapshot):
        assert self.locked
        self.data=deepcopy(snapshot);self.seq+=1
        if self.fail_restore:
            self.data={13:'partial restoration'}
            raise OSError('restore interrupted after mutation')
    def free_snapshot(self,snapshot): pass
    def dispose(self): self.disposed=True


class DeferredClipboard(FakeClipboard):
    """Model a native write becoming visible only after CloseClipboard."""
    def __init__(self):
        super().__init__()
        self.owned=False
        self.user_copy_on_close=False

    @contextmanager
    def open(self):
        before=self.seq
        with super().open():
            try:
                yield
            finally:
                if self.seq!=before:
                    self.seq+=3
                    if self.user_copy_on_close:
                        self.data={13:'user copy during close'}
                        self.owned=False
                        self.seq+=1

    def write_text(self,text):
        self.owned=True
        super().write_text(text)

    def owned_sequence(self):
        return self.seq if self.owned else None


def test_clipboard_lease_restores_all_original_formats_after_paste():
    from wxbot.wechat.clipboard import ClipboardLease
    api=FakeClipboard();before=deepcopy(api.data)
    lease=ClipboardLease('中，文。🤖',api=api)
    assert api.data=={13:'中，文。🤖'} and lease.is_current()
    assert lease.close()
    assert api.data==before and api.disposed
    assert lease.close()


def test_copy_by_user_is_preserved_instead_of_restoring_stale_clipboard():
    from wxbot.wechat.clipboard import ClipboardLease
    api=FakeClipboard()
    lease=ClipboardLease('bot batch',api=api)
    api.data={13:'user newly copied'};api.seq+=1
    assert not lease.is_current()
    assert lease.close()
    assert api.data=={13:'user newly copied'}


def test_failed_clipboard_write_restores_backup_without_pasting():
    from wxbot.wechat.clipboard import ClipboardLease
    api=FakeClipboard();before=deepcopy(api.data);api.fail_write=True
    with pytest.raises(OSError): ClipboardLease('batch',api=api)
    assert api.data==before and api.disposed


def test_temporarily_locked_clipboard_keeps_backup_until_it_can_restore():
    from wxbot.wechat.clipboard import ClipboardLease,restore_pending
    api=FakeClipboard();before=deepcopy(api.data)
    lease=ClipboardLease('batch',api=api)
    api.busy=True
    assert not lease.close() and not api.disposed
    api.busy=False
    restore_pending(force=True)
    assert api.data==before and api.disposed


def test_failed_restore_is_retried_without_treating_own_mutation_as_a_user_copy():
    from wxbot.wechat.clipboard import ClipboardLease,restore_pending
    api=FakeClipboard();before=deepcopy(api.data)
    lease=ClipboardLease('batch',api=api)
    api.fail_restore=True
    try:
        assert not lease.close()
    finally:
        api.fail_restore=False
        restore_pending(force=True)
    assert api.data==before and api.disposed


def native_clipboard():
    """Native boundary double; never opens the actual Windows clipboard."""
    import ctypes as ct
    from wxbot.wechat.clipboard import WindowsClipboard
    api=WindowsClipboard.__new__(WindowsClipboard)
    api.handles={};api.released=[];api.next_handle=100
    api.data={};api.fail_format=None
    def allocate(data):
        api.next_handle+=1
        api.handles[api.next_handle]=data
        return api.next_handle
    api.allocate=allocate
    api._duplicate=lambda handle,fmt,flags: allocate(api.handles[handle])
    api._copy_enhanced=lambda handle,name: allocate(api.handles[handle])
    def release(pointer):
        from wxbot.wechat.clipboard import _Medium
        medium=ct.cast(pointer,ct.POINTER(_Medium)).contents
        api.released.append(medium.handle)
        api.handles.pop(medium.handle)
    api._release=release
    def empty():
        api.data={}
        return True
    api._empty=empty
    def set_format(fmt,handle):
        if fmt==api.fail_format: return None
        api.data[fmt]=api.handles[handle]
        return handle
    api._set=set_format
    return api


def test_native_restore_keeps_immutable_backup_handles_after_partial_failure():
    from wxbot.wechat.clipboard import _Medium
    api=native_clipboard()
    handles=[api.allocate(b'text'),api.allocate(b'html')]
    saved=[(13,_Medium(1,handles[0],None)),(49152,_Medium(1,handles[1],None))]
    api.fail_format=49152
    try:
        with pytest.raises(OSError): api.restore(saved)
        assert [medium.handle for _,medium in saved]==handles
        assert all(handle in api.handles for handle in handles)
        api.fail_format=None
        api.restore(saved)
        assert api.data=={13:b'text',49152:b'html'}
        assert [medium.handle for _,medium in saved]==handles
    finally:
        api.free_snapshot(saved)


def test_native_text_allocation_counts_utf16_bytes_including_emoji():
    import ctypes as ct
    api=native_clipboard()
    buffers=[];allocations=[]
    def allocate(flags,size):
        allocations.append(size)
        buffer=ct.create_string_buffer(size)
        buffers.append(buffer)
        return api.allocate(buffer)
    api._alloc=allocate
    api._lock=lambda handle: ct.addressof(api.handles[handle])
    api._unlock=lambda handle: True
    api._free=lambda handle: pytest.fail('success transfers ownership to clipboard')
    text='中，文。🤖'
    api.write_text(text)
    expected=text.encode('utf-16-le')+b'\0\0'
    assert allocations==[len(expected)]
    assert buffers[0].raw==expected


def test_native_snapshot_rejects_unsafe_formats_before_overwriting_clipboard():
    api=native_clipboard()
    original={0x80:b'owner display'}
    api.data=original
    api._enum=lambda previous: 0x80 if previous==0 else 0
    with pytest.raises(OSError): api.snapshot()
    assert api.data==original and api.released==[]


def test_native_snapshot_releases_earlier_backups_if_a_later_format_cannot_copy():
    api=native_clipboard()
    originals={13:api.allocate(b'text'),49152:api.allocate(b'html')}
    formats=list(originals)
    api._enum=lambda previous: formats[0] if previous==0 else formats[1] if previous==13 else 0
    api._get=lambda fmt: originals[fmt]
    api._size=lambda handle: len(api.handles[handle])
    duplicate=api._duplicate
    api._duplicate=lambda handle,fmt,flags: None if fmt==49152 else duplicate(handle,fmt,flags)
    with pytest.raises(OSError): api.snapshot()
    assert len(api.released)==1
    assert set(api.handles)==set(originals.values())


def test_user_copy_during_restore_retry_is_never_replaced_by_old_backup():
    from wxbot.wechat.clipboard import ClipboardLease,restore_pending
    api=FakeClipboard()
    lease=ClipboardLease('batch',api=api)
    api.busy=True
    assert not lease.close()
    api.data={13:'new copy'};api.seq+=1;api.busy=False
    assert restore_pending(force=True)
    assert api.data=={13:'new copy'} and api.disposed


def test_independent_poll_retries_clipboard_cleanup_without_new_messages(monkeypatch):
    from wxbot import main as module
    calls=[]
    monkeypatch.setattr(module,'load_config',lambda: {
        'bot':{},'wechat':{'mode':'independent'},'outbound':{'enabled':False}})
    monkeypatch.setattr(module,'build_processor',lambda cfg: object())
    monkeypatch.setattr(module,'restore_pending',lambda **kwargs: calls.append(kwargs),raising=False)
    def stop(seconds): raise KeyboardInterrupt
    monkeypatch.setattr(module.time,'sleep',stop)
    with pytest.raises(KeyboardInterrupt): module.run()
    assert calls==[{}]


def test_main_exit_attempts_clipboard_cleanup_on_the_ui_thread(monkeypatch):
    from contextlib import nullcontext
    from wxbot import main as module
    calls=[]
    monkeypatch.setattr(module.auto,'UIAutomationInitializerInThread',nullcontext)
    def stop(): raise KeyboardInterrupt
    monkeypatch.setattr(module,'run',stop)
    monkeypatch.setattr(module,'restore_pending',lambda **kwargs: calls.append(kwargs),raising=False)
    module.main()
    assert calls==[{'force':True}]


def test_interrupt_during_clipboard_write_restores_original_before_propagating():
    from wxbot.wechat.clipboard import ClipboardLease
    api=FakeClipboard();before=deepcopy(api.data)
    write=api.write_text
    def interrupt(text):
        write(text)
        raise KeyboardInterrupt
    api.write_text=interrupt
    with pytest.raises(KeyboardInterrupt): ClipboardLease('batch',api=api)
    assert api.data==before and api.disposed


def test_interrupt_during_snapshot_releases_previously_duplicated_handles():
    api=native_clipboard()
    originals={13:api.allocate(b'text'),49152:api.allocate(b'html')}
    api._enum=lambda previous: 13 if previous==0 else 49152
    api._get=lambda fmt: originals[fmt]
    api._size=lambda handle:len(api.handles[handle])
    duplicate=api._duplicate
    def interrupt(handle,fmt,flags):
        if fmt==49152: raise KeyboardInterrupt
        return duplicate(handle,fmt,flags)
    api._duplicate=interrupt
    with pytest.raises(KeyboardInterrupt):api.snapshot()
    assert len(api.released)==1 and set(api.handles)==set(originals.values())


def test_committed_native_sequence_is_captured_after_clipboard_close():
    from wxbot.wechat.clipboard import ClipboardLease
    api=DeferredClipboard();before=deepcopy(api.data)
    lease=ClipboardLease('batch',api=api)
    try:
        assert lease.seq==api.seq
        assert lease.is_current()
    finally:
        lease.close()
    assert api.data==before


def test_user_copy_during_close_is_never_adopted_as_the_batch_version():
    from wxbot.wechat.clipboard import ClipboardLease
    api=DeferredClipboard();api.user_copy_on_close=True
    lease=ClipboardLease('batch',api=api)
    assert not lease.is_current()
    assert lease.close()
    assert api.data=={13:'user copy during close'}


def test_deferred_close_after_interrupted_restore_can_still_retry_all_formats():
    from wxbot.wechat.clipboard import ClipboardLease,restore_pending
    api=DeferredClipboard();before=deepcopy(api.data)
    lease=ClipboardLease('batch',api=api)
    api.fail_restore=True
    try:
        assert not lease.close()
    finally:
        api.fail_restore=False
        restore_pending(force=True)
    assert api.data==before


def test_native_owned_sequence_rejects_owner_change_during_the_query():
    api=native_clipboard()
    api.window=123
    owners=iter((123,999))
    api._owner=lambda:next(owners)
    api._sequence=lambda:5
    assert api.owned_sequence() is None


def test_native_owned_sequence_only_accepts_the_wxbot_owner():
    api=native_clipboard()
    api.window=123;api._owner=lambda:123;api._sequence=lambda:9
    assert api.owned_sequence()==9
    api._owner=lambda:999
    assert api.owned_sequence() is None


def test_deferred_write_failure_restores_original_before_propagating():
    from wxbot.wechat.clipboard import ClipboardLease
    api=DeferredClipboard();before=deepcopy(api.data);api.fail_write=True
    with pytest.raises(OSError): ClipboardLease('batch',api=api)
    assert api.data==before and api.disposed


def test_user_copy_after_deferred_restore_failure_takes_precedence_over_retry():
    from wxbot.wechat.clipboard import ClipboardLease,restore_pending
    api=DeferredClipboard()
    lease=ClipboardLease('batch',api=api);api.fail_restore=True
    try:
        assert not lease.close()
    finally:
        api.fail_restore=False
        api.data={13:'new user copy'};api.owned=False;api.seq+=1
        assert restore_pending(force=True)
    assert api.data=={13:'new user copy'} and api.disposed
