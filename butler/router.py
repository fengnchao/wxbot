"""决策层（第一半）：进去之前的规则，和出来之后的行动标记解析。

分工：
  · pre_route  —— 别麻烦模型的事（空消息、通道级），在投递前就断掉；
  · parse_actions —— 模型"说出来想干什么"。用户看不到这些块，管家剥掉并执行。
模型不发标记 = 纯文本回复 = 与今天行为一致，所以协议是增量的。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# 模型说"这条不用回"的几种写法（历史实现里就有 [SILENT] 一套，先兼容着）
SILENT_MARKERS = ("[SILENT]", "[silent]", "SILENT", "（不回复）", "(不回复)", "<<butler:silent>>")

# 行动标记：<<butler:action {"skill":"...","args":{...}}>>
ACTION_RE = re.compile(r"<<\s*butler:action\s*(\{.*?\})\s*>>", re.S)

PENDING_HEADER = "📮 这几条刚才没送出去，补给你："


@dataclass
class Decision:
    kind: str                     # "agent" 投给模型 / "reply" 直接回 / "silent" 不回
    reply: str | None = None
    note: str = ""
    actions: list = field(default_factory=list)


def pre_route(contact, text: str) -> Decision:
    """投递 Hermes 之前的规则层。目前只拦两种：空消息、通道级命令。

    `/ping` `/help` `/reset` 这类由 wxbot 自己处理（它已经有一层 Router），
    管家不重复实现；这里只兜住"没有内容"和"管家自己认识的命令"。
    """
    t = (text or "").strip()
    if not t:
        return Decision(kind="silent", note="空消息")
    if t in ("/new", "/重置"):
        return Decision(kind="reset", note="用户要求开新会话")
    return Decision(kind="agent")


def parse_actions(reply: str) -> tuple[str, list[dict]]:
    """剥掉行动标记，返回 (给用户看的文本, 要执行的 action 列表)。"""
    if not reply:
        return "", []
    acts: list[dict] = []
    for m in ACTION_RE.finditer(reply):
        raw = m.group(1)
        try:
            obj = json.loads(raw)
        except Exception:
            continue                      # 标记写坏了就当它不存在（不能让脏输出毁掉回复）
        skill = str((obj or {}).get("skill") or "").strip()
        if not skill:
            continue
        args = obj.get("args") or {}
        acts.append({"skill": skill, "args": args if isinstance(args, dict) else {}})
    clean = ACTION_RE.sub("", reply).strip()
    return clean, acts


def is_silent(text: str | None) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return t.startswith(SILENT_MARKERS) or t in SILENT_MARKERS


def compose(parts, pending: list[dict]) -> str | None:
    """补发内容拼在最前面（认领已经在调模型之前做完了）。"""
    blocks = [p for p in (parts or []) if p]
    if pending:
        pend_text = "\n\n".join((i.get("text") or "").strip() for i in pending if i.get("text"))
        if pend_text:
            blocks.insert(0, f"{PENDING_HEADER}\n{pend_text}")
    if not blocks:
        return None
    return "\n\n".join(blocks)
