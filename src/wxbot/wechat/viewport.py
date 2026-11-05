"""Physical monitor geometry and bounded recovery before screenshot capture."""
import ctypes
from ctypes import wintypes

import uiautomation as auto

from ..log import log
from .locator import wait_until


def rect_bounds(rect):
    return rect.left, rect.top, rect.right, rect.bottom


def rect_is_visible(bounds, areas):
    """Require coverage by the monitor union, including gaps and negative origins."""
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        return False
    remaining = [bounds]
    for area in areas:
        uncovered = []
        for left, top, right, bottom in remaining:
            x1, y1 = max(left, area[0]), max(top, area[1])
            x2, y2 = min(right, area[2]), min(bottom, area[3])
            if x1 >= x2 or y1 >= y2:
                uncovered.append((left, top, right, bottom))
                continue
            for piece in ((left, top, right, y1), (left, y2, right, bottom),
                          (left, y1, x1, y2), (x2, y1, right, y2)):
                if piece[0] < piece[2] and piece[1] < piece[3]:
                    uncovered.append(piece)
        remaining = uncovered
        if not remaining:
            return True
    return False


def fit_window_rect(bounds, areas):
    """Preserve visible windows; otherwise fit into the nearest usable monitor."""
    areas = [area for area in areas if area[0] < area[2] and area[1] < area[3]]
    left, top, right, bottom = bounds
    if not areas or left >= right or top >= bottom:
        return None
    if rect_is_visible(bounds, areas):
        return bounds

    def priority(area):
        overlap = (max(0, min(right, area[2]) - max(left, area[0]))
                   * max(0, min(bottom, area[3]) - max(top, area[1])))
        dx = max(area[0] - right, left - area[2], 0)
        dy = max(area[1] - bottom, top - area[3], 0)
        return overlap, -(dx * dx + dy * dy)

    area = max(areas, key=priority)
    width, height = min(right - left, area[2] - area[0]), min(bottom - top, area[3] - area[1])
    left = max(area[0], min(left, area[2] - width))
    top = max(area[1], min(top, area[3] - height))
    return left, top, left + width, top + height


def monitor_work_areas():
    """Read each monitor's work area rather than assuming the primary screen."""
    class MonitorInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                    ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]

    user32 = ctypes.windll.user32
    monitor_from_rect = user32.MonitorFromRect
    monitor_from_rect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
    monitor_from_rect.restype = wintypes.HANDLE
    get_monitor_info = user32.GetMonitorInfoW
    get_monitor_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    get_monitor_info.restype = wintypes.BOOL
    areas = []
    for monitor in auto.GetMonitorsRect():
        bounds = wintypes.RECT(*rect_bounds(monitor))
        handle = monitor_from_rect(ctypes.byref(bounds), 2)
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if not handle or not get_monitor_info(handle, ctypes.byref(info)):
            raise OSError('monitor_work_area_unavailable')
        areas.append(rect_bounds(info.rcWork))
    return areas


def ensure_window_visible(window):
    """Move only off-screen windows; verify the result before UI capture proceeds."""
    try:
        areas = monitor_work_areas()
        before = rect_bounds(window.BoundingRectangle)
        target = fit_window_rect(before, areas)
        if target is None:
            return False
        if before == target:
            return True
        left, top, right, bottom = target
        if not window.MoveWindow(left, top, right - left, bottom - top):
            log.warning('微信窗口可见区域恢复失败：window_move_failed')
            return False
        ready = wait_until(lambda: rect_is_visible(rect_bounds(window.BoundingRectangle), areas),
                           timeout=0.5)
        log.log(20 if ready else 30, '微信窗口可见区域恢复：before=%s target=%s ready=%s',
                before, target, ready)
        return ready
    except Exception as exc:
        log.warning('微信窗口可见区域不可确认：%s', type(exc).__name__)
        return False
