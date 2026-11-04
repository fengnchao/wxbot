import ctypes, ctypes.wintypes as w
from ctypes import byref, sizeof, create_unicode_buffer
kernel32 = ctypes.Windll = ctypes.WinDLL('kernel32', use_last_error=True)
ntdll = ctypes.WinDLL('ntdll', use_last_error=True)
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
pids = [222688, 229380, 220468, 222888]
class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [('Reserved1', ctypes.c_void_p),
                ('PebBaseAddress', ctypes.c_void_p),
                ('Reserved2', ctypes.c_void_p * 2),
                ('UniqueProcessId', ctypes.c_void_p),
                ('Reserved3', ctypes.c_void_p)]
for pid in pids:
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    print('pid', pid, 'handle', h, 'err', ctypes.get_last_error())
    if not h:
        continue
    # try QueryFullProcessImageName
    buf = create_unicode_buffer(1024)
    size = w.DWORD(1024)
    if kernel32.QueryFullProcessImageNameW(h, 0, buf, byref(size)):
        print(' image', buf.value)
    kernel32.CloseHandle(h)
