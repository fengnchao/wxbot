"""向指定 WaveOut 设备播放 PCM WAV（默认匹配 CABLE Input）。"""
from __future__ import annotations

import ctypes
import threading
import wave
from ctypes import wintypes
from io import BytesIO


winmm = ctypes.WinDLL("winmm")


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.POINTER(ctypes.c_ulong)),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_void_p),
    ]


class WAVEOUTCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", ctypes.c_wchar * 32),
        ("dwFormats", wintypes.DWORD),
        ("wChannels", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
        ("dwSupport", wintypes.DWORD),
    ]


WHDR_DONE = 0x00000001
WAVE_MAPPER = 0xFFFFFFFF
CALLBACK_NULL = 0


def list_wave_out_devices() -> list[tuple[int, str]]:
    count = int(winmm.waveOutGetNumDevs())
    devices = []
    for index in range(count):
        caps = WAVEOUTCAPSW()
        result = winmm.waveOutGetDevCapsW(index, ctypes.byref(caps), ctypes.sizeof(caps))
        if result != 0:
            continue
        devices.append((index, caps.szPname))
    return devices


def find_wave_out_device(name_substr: str) -> int:
    needle = (name_substr or "").strip().lower()
    if not needle:
        raise ValueError("播放设备名为空")
    matches = [(index, name) for index, name in list_wave_out_devices() if needle in name.lower()]
    if not matches:
        known = ", ".join(name for _, name in list_wave_out_devices()) or "(无)"
        raise ValueError(f"找不到播放设备含 {name_substr!r}；本机 WaveOut: {known}")
    return matches[0][0]


def _load_pcm(data: bytes) -> tuple[WAVEFORMATEX, bytes, float]:
    with wave.open(BytesIO(data), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
        duration = handle.getnframes() / float(rate)
    if channels != 1 or width != 2:
        raise ValueError("播放仅支持 16-bit mono PCM")
    fmt = WAVEFORMATEX(
        1,
        channels,
        rate,
        rate * channels * width,
        channels * width,
        width * 8,
        0,
    )
    return fmt, frames, duration


class WaveOutPlayer:
    """同步打开设备并异步写出缓冲区；close/wait 结束播放。"""

    def __init__(self, data: bytes, *, device_name: str = "CABLE Input"):
        self.device_name = device_name
        self._fmt, self._pcm, self.duration_seconds = _load_pcm(data)
        self._handle = wintypes.HANDLE()
        self._header = WAVEHDR()
        self._buffer = ctypes.create_string_buffer(self._pcm)
        self._opened = False
        self._prepared = False
        self._error = ""
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._opened:
                return
            device = find_wave_out_device(self.device_name)
            result = winmm.waveOutOpen(
                ctypes.byref(self._handle),
                device,
                ctypes.byref(self._fmt),
                0,
                0,
                CALLBACK_NULL,
            )
            if result != 0:
                raise RuntimeError(f"waveOutOpen 失败: {result}")
            self._opened = True
            self._header.lpData = ctypes.cast(self._buffer, ctypes.c_void_p)
            self._header.dwBufferLength = len(self._pcm)
            self._header.dwFlags = 0
            self._header.dwLoops = 0
            result = winmm.waveOutPrepareHeader(
                self._handle, ctypes.byref(self._header), ctypes.sizeof(self._header)
            )
            if result != 0:
                self.close()
                raise RuntimeError(f"waveOutPrepareHeader 失败: {result}")
            self._prepared = True
            result = winmm.waveOutWrite(
                self._handle, ctypes.byref(self._header), ctypes.sizeof(self._header)
            )
            if result != 0:
                self.close()
                raise RuntimeError(f"waveOutWrite 失败: {result}")

    def done(self) -> bool:
        with self._lock:
            if not self._opened:
                return True
            return bool(self._header.dwFlags & WHDR_DONE)

    def wait(self, timeout: float | None = None) -> None:
        import time

        deadline = None if timeout is None else time.monotonic() + timeout
        while not self.done():
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("音频播放超时")
            time.sleep(0.02)

    def close(self) -> None:
        with self._lock:
            if not self._opened:
                return
            try:
                winmm.waveOutReset(self._handle)
            except Exception:
                pass
            if self._prepared:
                try:
                    winmm.waveOutUnprepareHeader(
                        self._handle, ctypes.byref(self._header), ctypes.sizeof(self._header)
                    )
                except Exception:
                    pass
                self._prepared = False
            try:
                winmm.waveOutClose(self._handle)
            except Exception:
                pass
            self._opened = False
