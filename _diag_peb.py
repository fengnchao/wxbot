import ctypes
from ctypes import wintypes, byref, sizeof, create_string_buffer, c_size_t, c_void_p, c_ulong, c_ulonglong
import struct, sys

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Reserved1", c_void_p),
        ("PebBaseAddress", c_void_p),
        ("Reserved2", c_void_p * 2),
        ("UniqueProcessId", c_void_p),
        ("Reserved3", c_void_p),
    ]

def read_mem(h, addr, size):
    buf = create_string_buffer(size)
    read = c_size_t(0)
    ok = kernel32.ReadProcessMemory(h, c_void_p(addr), buf, size, byref(read))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    return buf.raw[:read.value]

def read_unicode(h, addr, max_chars=1024):
    # addr points to UNICODE_STRING {Length, MaxLength, Buffer}
    raw = read_mem(h, addr, 16 if struct.calcsize("P")==8 else 8)
    if struct.calcsize("P")==8:
        length, maxlen, bufptr = struct.unpack("<HHI", raw[:8] + b"\x00\x00") if False else None
        # Actually UNICODE_STRING is USHORT Length, USHORT MaximumLength, PWSTR Buffer
        length, maximum = struct.unpack("<HH", raw[:4])
        bufptr = struct.unpack("<Q", raw[8:16])[0]
    else:
        length, maximum = struct.unpack("<HH", raw[:4])
        bufptr = struct.unpack("<I", raw[4:8])[0]
    if not bufptr or length == 0:
        return ""
    data = read_mem(h, bufptr, length)
    return data.decode("utf-16-le", errors="replace")

pid = 222688
h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
if not h:
    raise SystemExit("open failed %s" % ctypes.get_last_error())
pbi = PROCESS_BASIC_INFORMATION()
status = ntdll.NtQueryInformationProcess(h, 0, byref(pbi), sizeof(pbi), None)
print("ntstatus", status, "peb", hex(pbi.PebBaseAddress or 0))
peb = pbi.PebBaseAddress
# PEB offsets x64: ProcessParameters at 0x20
ptr_size = struct.calcsize("P")
proc_params = struct.unpack("<Q" if ptr_size==8 else "<I", read_mem(h, peb + (0x20 if ptr_size==8 else 0x10), ptr_size))[0]
print("ProcessParameters", hex(proc_params))
# RTL_USER_PROCESS_PARAMETERS x64:
# CurrentDirectory.DosPath UNICODE_STRING at 0x38
# ImagePathName at 0x60, CommandLine at 0x70
if ptr_size == 8:
    cwd = read_unicode(h, proc_params + 0x38)
    # Also try reading Environment briefly - skip
    image = read_unicode(h, proc_params + 0x60)
    cmdline = read_unicode(h, proc_params + 0x70)
else:
    cwd = read_unicode(h, proc_params + 0x24)
    image = read_unicode(h, proc_params + 0x38)
    cmdline = read_unicode(h, proc_params + 0x40)
print("CWD:", cwd)
print("Image:", image)
print("Cmd:", cmdline[:300])
kernel32.CloseHandle(h)
