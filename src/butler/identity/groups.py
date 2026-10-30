"""用户分组（订阅字典）：messageType → 绑定的联系人（微信窗口标题）。

用途：Hermes 侧推送带 messageType 时，butler 按本字典把消息群发（type=2）
给所有绑定该类型的联系人；单个指定用户（type=1）不受字典限制。

字典文件是 JSON（UTF-8，原子替换写），butler 与 log 看板（8788「用户分组」页）
读写同一份（看板是独立进程，只认文件，不 import 本模块）：
    {"version": 1, "updated_at": "2026-10-12 10:00:00",
     "groups": {"1": ["101", "z"], "2": ["101"], "3": []}}
默认路径 {hermes.root}/cache/butler_groups.json（见 Config.group_file_path）。
读=每次现读（看板改完文件，管家下一条推送就该看到），写=tmp + os.replace。
"""
from __future__ import annotations

import json
import os
import threading
import time

# 与 Hermes 侧约定的两个枚举（解析入口在 server.py /v1/push）
PUSH_TYPES = {1: "指定用户发送", 2: "群发"}
MESSAGE_TYPES = {1: "新闻消息", 2: "问候消息", 3: "其他"}


def parse_int(value):
    """把 1 / "1" / " 1 " / 1.0 解析成 int；解析不出来返回 None（bool 不算数）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def label_of(message_type) -> str:
    n = parse_int(message_type)
    if n is None:
        return ""
    return MESSAGE_TYPES.get(n, f"类型{n}")


def clean_users(users) -> list[str]:
    """去空、去重（保序）。"""
    out, seen = [], set()
    for u in users or []:
        s = str(u or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


class GroupStore:
    """分组字典的读写。path 为空则整体禁用（推送时按"没有绑定用户"处理）。"""

    VERSION = 1

    def __init__(self, path: str, log=None, *, database=None):
        self.database = database
        self.log = log or (lambda *a, **k: None)
        self._lock = threading.Lock()
        self.path = (path or "").strip()
        from butler.identity.contact_store import is_unified
        if self.path and not (self.database and is_unified(self.database)):
            d = os.path.dirname(self.path)
            try:
                if d:
                    os.makedirs(d, exist_ok=True)
            except Exception as e:                       # 建不了目录就禁用，绝不拖垮主流程
                self.log("分组字典目录创建失败，已禁用: %s", e)
                self.path = ""

    # ---------- 读 ----------
    def load(self) -> dict[str, list[str]]:
        """完整字典 {messageType(str): [user,...]}；文件缺失/坏掉时按空处理。"""
        from butler.identity.contact_store import ContactStore,is_unified
        if self.database and is_unified(self.database):
            return ContactStore(self.database).groups()
        groups: dict[str, list[str]] = {}
        if not self.path or not os.path.exists(self.path):
            return groups
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception as e:
            self.log("分组字典读取失败（按空处理）: %s", e)
            return groups
        g = raw.get("groups") if isinstance(raw, dict) else None
        if not isinstance(g, dict):                      # 兼容裸 {type: [users]} 的写法
            g = raw if isinstance(raw, dict) else {}
        for k, v in g.items():
            n = parse_int(k)
            if n is None or n <= 0 or not isinstance(v, list):
                continue
            users = clean_users(v)
            if users:
                groups[str(n)] = users
        return groups

    def snapshot(self) -> dict[str, list[str]]:
        """接口/页面外形：1/2/3 三个已知类型总在（哪怕空列表），未知类型原样带上。"""
        groups = self.load()
        out = {str(t): list(groups.get(str(t)) or []) for t in sorted(MESSAGE_TYPES)}
        for k, v in groups.items():
            out.setdefault(k, v)
        return out

    def users_of(self, message_type) -> list[str]:
        n = parse_int(message_type)
        if n is None:
            return []
        return list(self.load().get(str(n), []))

    # ---------- 写 ----------
    def _save(self, groups: dict[str, list[str]]) -> None:
        from butler.identity.contact_store import ContactStore,is_unified
        if self.database and is_unified(self.database):
            ContactStore(self.database).set_groups(groups)
            return
        if not self.path:
            raise RuntimeError("分组字典未配置（[groups].file 与 hermes.root 都为空）")
        payload = {"version": self.VERSION,
                   "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "groups": groups}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def set_users(self, message_type, users) -> list[str]:
        n = parse_int(message_type)
        if n is None or n <= 0:
            raise ValueError(f"messageType 非法: {message_type!r}")
        clean = clean_users(users)
        with self._lock:
            groups = self.load()
            groups[str(n)] = clean
            self._save(groups)
        return clean

    def bind(self, message_type, user) -> list[str]:
        u = str(user or "").strip()
        if not u:
            raise ValueError("user 为空")
        cur = self.users_of(message_type)
        if u not in cur:
            cur.append(u)
        return self.set_users(message_type, cur)

    def unbind(self, message_type, user) -> list[str]:
        u = str(user or "").strip()
        cur = [x for x in self.users_of(message_type) if x != u]
        return self.set_users(message_type, cur)
