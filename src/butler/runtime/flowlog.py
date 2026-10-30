"""管家流水日志：把每轮「收到 / 回复 / 调用失败」写成 log 看板能解析的格式。

看板 log/server.py 逐行解析 {HERMES_HOME}/cache/wxbot.log，认这几种行：
    [YYYY-MM-DD HH:MM:SS] INFO  [uid] 收到: <正文>
    [YYYY-MM-DD HH:MM:SS] INFO  [uid] 回复: <正文>
    [YYYY-MM-DD HH:MM:SS] ERROR [uid] Hermes API 调用失败: <详情>
无时间戳前缀的续行会被看板接到上一条事件，所以多行正文原样写即可（UTF-8）。

为什么放管家侧：一轮的「收到 → 调 Hermes → 回复」全经过 butler.handle，
它是唯一同时握有 contact、原文、耗时、最终文案的中枢；wxbot 只做 UI 收发。
uid 用联系人窗口标题（与看板 [[contacts]].name / config.wxbot.toml 对齐）。
"""
from __future__ import annotations

import os
import threading
import time

_ERR_PREFIX = "Hermes API 调用失败:"


class FlowLog:
    """线程安全的追加式流水日志。path 为空则整体禁用（不报错、不写盘）。"""

    def __init__(self, path: str, log=None):
        self.log = log or (lambda *a, **k: None)
        self._lock = threading.Lock()
        self.path = (path or "").strip()
        if self.path:
            d = os.path.dirname(self.path)
            try:
                if d:
                    os.makedirs(d, exist_ok=True)
            except Exception as e:                       # 目录建不了就禁用，绝不拖垮主流程
                self.log("流水日志目录创建失败，已禁用: %s", e)
                self.path = ""

    # ---------- 底层写入 ----------
    def _write(self, level: str, body: str) -> None:
        if not self.path:
            return
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {level} {body}\n"
        try:
            with self._lock, open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception as e:
            self.log("流水日志写入失败: %s", e)

    # ---------- 三种事件 ----------
    def received(self, uid: str, text: str) -> None:
        self._write("INFO", f"[{uid}] 收到: {text or ''}")

    def reply(self, uid: str, text: str | None) -> None:
        if text:                                          # 静默（reply=None）不记「回复」
            self._write("INFO", f"[{uid}] 回复: {text}")

    def api_error(self, uid: str, detail: str) -> None:
        d = (detail or "").strip()
        if d.startswith(_ERR_PREFIX):                     # HermesError 本身可能已带前缀，去重
            d = d[len(_ERR_PREFIX):].strip()
        self._write("ERROR", f"[{uid}] {_ERR_PREFIX} {d}")

    # ---------- 外发（主动推送）：格式须匹配看板 _OUTQ_RE/_OUTS_RE ----------
    # uid 用窗口标题（不含冒号，匹配正则的 ([^:]+)）；看板 merge_outbound 会把两条合成一轮。
    def outbound_queued(self, uid: str, text: str) -> None:
        self._write("INFO", f"[外发] 入队 → {uid}: {text or ''}")

    def outbound_sent(self, uid: str, text: str) -> None:
        self._write("INFO", f"[外发] 已发出 → {uid}: {text or ''}")
