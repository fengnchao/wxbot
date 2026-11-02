"""按配置里的条件查找控件。条件来自 config.toml 的 [wechat.*] 段。"""
import re
import time
from collections import deque

import uiautomation as auto


def wait_until(predicate, *, timeout, interval=0.02, clock=time.monotonic, sleep=time.sleep):
    """等界面到达预期状态，返回是否在时限内满足；用来代替固定 sleep。"""
    deadline = clock() + max(0.0, float(timeout))
    delay = max(0.005, float(interval))
    while True:
        if predicate():
            return True
        if clock() >= deadline:
            return False
        sleep(delay)


def _match_text(expected: str, actual: str) -> bool:
    if expected.startswith("re:"):
        return re.search(expected[3:], actual or "") is not None
    return expected == (actual or "")


def matches(ctrl: auto.Control, spec: dict) -> bool:
    if "control_type" in spec and ctrl.ControlTypeName != spec["control_type"]:
        return False
    if "name" in spec and not _match_text(spec["name"], ctrl.Name):
        return False
    if "class_name" in spec and not _match_text(spec["class_name"], ctrl.ClassName):
        return False
    if "automation_id" in spec and not _match_text(spec["automation_id"], ctrl.AutomationId):
        return False
    return True


def find(root: auto.Control, spec: dict, max_depth: int = 15) -> auto.Control | None:
    """广度优先查找第一个满足条件的后代控件。"""
    queue = deque([(root, 0)])
    while queue:
        ctrl, depth = queue.popleft()
        if depth > 0 and matches(ctrl, spec):
            return ctrl
        if depth < max_depth:
            try:
                for child in ctrl.GetChildren():
                    queue.append((child, depth + 1))
            except Exception:
                continue
    return None


def find_all(root: auto.Control, spec: dict, max_depth: int = 15, limit: int = 200) -> list:
    """广度优先收集所有满足条件的后代控件（用于表情面板条目等）。"""
    found = []
    queue = deque([(root, 0)])
    while queue:
        ctrl, depth = queue.popleft()
        if depth > 0 and matches(ctrl, spec):
            found.append(ctrl)
            if len(found) >= limit:
                break
        if depth < max_depth:
            try:
                for child in ctrl.GetChildren():
                    queue.append((child, depth + 1))
            except Exception:
                continue
    return found
