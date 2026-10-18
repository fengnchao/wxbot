"""补发队列：Hermes 侧漏发的提醒，由管家**认领**（先标记再拼装）。

为什么在管家这一层：补发是"投递语义"，不是 UI 的事。放在这里之后
  · 认领发生在调模型**之前** → 模型自己再查一次队列看到的是空的，不会把同样内容说两遍；
  · 模型挂了也要把认领的内容发出去 → 内容不丢。
队列本体仍复用 Hermes 侧那份 `pending_delivery.py`（schema 只有一份）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from .concurrency import RuntimeLocks

_OWNER_FIELDS = frozenset({'contact', 'uid', 'user_id'})
_OWNER_WORDS = frozenset({'contact', 'uid', 'user', 'userid', 'username', 'recipient',
                          'recipients', 'receiver', 'receivers', 'target', 'targets',
                          'to', 'owner', 'profile'})


def _unknown_ownership(item, *, root=True):
    # Extra recipient-shaped fields are not evidence of an unowned legacy record.
    # Keep them for manual/schema-aware handling instead of guessing the recipient.
    if isinstance(item, list):
        return any(_unknown_ownership(value, root=False) for value in item if isinstance(value, (dict,list)))
    for key, value in item.items():
        snake = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', key).lower().replace('-', '_')
        tokens = snake.split('_')
        shaped = (_OWNER_WORDS.intersection(tokens) or
                  any(snake.startswith(p) for p in ('recipient','receiver','contact','target','owner')) or
                  snake in {'touserid','touid','toid','wxid','openid'})
        if (not root or key not in _OWNER_FIELDS) and shaped:
            return True
        if isinstance(value, (dict, list)) and _unknown_ownership(value, root=False):
            return True
    return False


class PendingQueue:
    def __init__(self, hermes_root: str, log=None, *, locks=None):
        self.root = (hermes_root or "").rstrip("/\\")
        self.log = log or (lambda *a, **k: None)
        self.locks = locks or RuntimeLocks(self.root)

    def script(self, profile: str) -> str | None:
        if not self.root:
            return None
        p = os.path.join(self.root, "profiles", profile, "skills", "messaging",
                         "wechat-reminder", "scripts", "pending_delivery.py")
        return p if os.path.exists(p) else None

    def _run(self, script: str, *args) -> str | None:
        try:
            r = subprocess.run([sys.executable, script, *args],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                raise RuntimeError(f'exit={r.returncode}: {(r.stderr or "")[:160]}')
            return (r.stdout or "").strip()
        except Exception as e:
            self.log("补发脚本执行失败: %s", e)
            return None

    def take_and_claim(self, contact, *, allow_unowned=False) -> list[dict]:
        claimed = []
        with self.locks.profile(contact.profile):
            script = self.script(contact.profile)
            if not script:
                return []
            for item in self.take(contact.profile):
                key = item.get('key')
                fields = [f for f in _OWNER_FIELDS if f in item]
                owned = all(isinstance(item[f], str) and item[f].strip() and
                            item[f] == (contact.name if f == 'contact' else contact.uid)
                            for f in fields)
                if (not isinstance(key, str) or not key.strip() or not owned or
                        _unknown_ownership(item) or (not fields and not allow_unowned)):
                    self.log('补发归属不明，保留未认领条目 profile=%s key=%r', contact.profile, key)
                    continue
                if self._run(script, 'flush', key) is None:
                    break
                claimed.append(item)
        return claimed

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
            items = []
            for item in d.get('items') or []:
                if isinstance(item, dict) and isinstance(item.get('text'), str) and item['text'].strip():
                    items.append(item)
                else:
                    self.log('补发正文格式无效，保留条目未认领 profile=%s', profile)
            return items
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
