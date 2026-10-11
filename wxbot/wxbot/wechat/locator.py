"""按配置里的条件查找控件。条件来自 config.toml 的 [wechat.*] 段。"""
import re
from collections import deque

import uiautomation as auto


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
