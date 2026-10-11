"""补发队列：Hermes 侧漏发的提醒，由管家**认领**（先标记再拼装）。

为什么在管家这一层：补发是"投递语义"，不是 UI 的事。放在这里之后
  · 认领发生在调模型**之前** → 模型自己再查一次队列看到的是空的，不会把同样内容说两遍；
  · 模型挂了也要把认领的内容发出去 → 内容不丢。
队列本体仍复用 Hermes 侧那份 `pending_delivery.py`（schema 只有一份）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


class PendingQueue:
    def __init__(self, hermes_root: str, log=None):
        self.root = (hermes_root or "").rstrip("/\\")
        self.log = log or (lambda *a, **k: None)

    def script(self, profile: str) -> str | None:
        if not self.root:
            return None
        p = os.path.join(self.root, "profiles", profile, "skills", "messaging",
                         "wechat-reminder", "scripts", "pending_delivery.py")
        return p if os.path.exists(p) else None

    def _run(self, script: str, *args) -> str:
        try:
            r = subprocess.run([sys.executable, script, *args],
                               capture_output=True, text=True, timeout=60)
            return (r.stdout or "").strip()
        except Exception as e:
            self.log("补发脚本执行失败: %s", e)
            return ""

    def take(self, profile: str) -> list[dict]:
        """只读地取出待补发条目（不标记）。"""
        script = self.script(profile)
        if not script:
            return []
        out = self._run(script, "json")
        if not out:
            return []
        try:
            d = json.loads(out[out.index("{"):])
            return [i for i in (d.get("items") or []) if i.get("text")]
        except Exception:
            return []

    def claim(self, profile: str, keys) -> None:
        """标记为已补发（去重台账，不要删）。"""
        script = self.script(profile)
        if not script:
            return
        keys = [k for k in keys if k]
        for k in keys:
            self._run(script, "flush", str(k))
        if keys:
            self.log("补发 %d 条已认领（profile=%s）", len(keys), profile)
