"""开启 DPI 感知，保证控件坐标和截图坐标一致（屏幕缩放 125%/150% 时很重要）。必须最先调用。"""
import ctypes


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
