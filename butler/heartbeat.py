"""In-process randomized heartbeat: ask Hermes for a suggestion and DM it to its owner."""
from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from datetime import datetime


_HEARTBEAT_PROMPT = (
    "这是一次定期心跳。请结合你的角色和允许使用的技能，检查是否有值得提醒用户的事情，"
    "例如可完善的资料或值得用户决定的下一步。你只能检查并提出建议；不要创建、修改、删除文件，"
    "不要执行外部操作，也不要替用户采取行动。若有具体建议，优先给出简短建议；若没有，"
    "也不要沉默或返回 none，请结合你的角色口吻，给用户一句自然、轻松的问候、随想或问题，"
    "最多两句且不超过 60 个汉字。不要编造用户相关事实，也尽量避免重复套话。"
    '始终返回 JSON：{"action":"suggestion","text":"给用户看的简短建议或角色化短句"}。'
    "只返回 JSON，不要 Markdown。"
)

_SECRET_PATTERNS = (
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+=*"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(api[_ -]?key|token|password|authorization)(\s*[:=]\s*)[^\s,;]+"),
     r"\1\2[REDACTED]"),
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]{16,})\b"),
     "[REDACTED]"),
)


def _redact(value: object, limit: int = 3000) -> str:
    text = str(value or "")
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text[:limit]


def _parse_response(text: str) -> tuple[bool, str | None]:
    """Accept only the explicit no-action/suggestion JSON response contract."""
    try:
        payload = json.loads(text.strip())
    except Exception:
        return False, None
    if not isinstance(payload, dict):
        return False, None
    if payload.get("action") == "none":
        return (True, None) if payload.get("text", "") == "" else (False, None)
    if payload.get("action") != "suggestion":
        return False, None
    value = payload.get("text")
    if not isinstance(value, str):
        return False, None
    value = value.strip()
    return (True, value[:3000]) if value else (False, None)


class HeartbeatScheduler:
    def __init__(self, butler, cfg, log=None):
        self.butler = butler
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)
        self.path = cfg.heartbeat_state_path()
        self.audit_path = cfg.heartbeat_audit_path()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._audit_lock = threading.Lock()

    def _audit(self, event: str, **fields) -> None:
        if not self.audit_path:
            return
        row = {"at": datetime.now().astimezone().isoformat(timespec="seconds"),
               "event": event, **fields}
        try:
            directory = os.path.dirname(self.audit_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            with self._audit_lock, open(self.audit_path, "a", encoding="utf-8") as fh:
                fh.write(encoded)
        except Exception as exc:
            self.log("写入心跳审计日志失败: %s", type(exc).__name__)

    def _random_interval(self) -> float:
        low = max(1, int(self.cfg.heartbeat_min_interval_minutes))
        high = max(low, int(self.cfg.heartbeat_max_interval_minutes))
        return random.uniform(low, high) * 60

    def _load_next_run(self) -> float | None:
        if not self.path:
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                value = json.load(fh).get("next_run_at")
            return float(value) if value is not None else None
        except Exception:
            return None

    def _save_next_run(self, due: float) -> None:
        if not self.path:
            return
        try:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "next_run_at": due}, fh, indent=2)
            os.replace(tmp, self.path)
        except Exception as exc:
            detail = _redact(exc, 1000)
            self._audit("error", phase="state_write", error_type=type(exc).__name__, detail=detail)
            self.log("保存下一次心跳时间失败: %s: %s", type(exc).__name__, detail)

    def _enabled_contacts(self) -> list[tuple[str, dict]]:
        configured = set(self.cfg.contacts.names())
        return [(name, policy) for name, policy in self.butler.skill_policies.heartbeat_contacts()
                if name in configured]

    def _run_contact(self, contact_name: str, policy: dict, source: str) -> None:
        self._audit("trigger_started", source=source, contact=contact_name)
        role_skill = str(policy.get("role_skill") or "")
        allowed_skills = sorted(str(item) for item in policy.get("allowed_skills", []))
        self._audit("contact_selected", source=source, contact=contact_name, role_skill=role_skill,
                    allowed_skills=allowed_skills)
        started = time.monotonic()
        try:
            contact = self.butler.contact_of(contact_name)
            self._audit("hermes_call_started", source=source, contact=contact_name,
                        role_skill=role_skill)
            raw = self.butler.hermes.chat(
                contact, "请现在进行一次心跳检查。",
                extra_system=_HEARTBEAT_PROMPT,
                skill_policy=policy, session_kind="heartbeat")
        except Exception as exc:
            detail = _redact(exc, 1000)
            self._audit("error", source=source, phase="hermes", contact=contact_name,
                        error_type=type(exc).__name__, detail=detail)
            self.log("心跳执行失败 [%s]: %s: %s", contact_name, type(exc).__name__, detail)
            return

        elapsed_ms = round((time.monotonic() - started) * 1000)
        valid, message = _parse_response(raw)
        if not valid:
            self._audit("hermes_result", source=source, contact=contact_name, result="invalid",
                        elapsed_ms=elapsed_ms)
            self.log("心跳结果未通过 JSON 契约校验 [%s]，已忽略", contact_name)
            return
        if not message:
            self._audit("hermes_result", source=source, contact=contact_name, result="none",
                        elapsed_ms=elapsed_ms)
            self.log("心跳检查完成 [%s]：Hermes 没有建议", contact_name)
            return

        self._audit("hermes_result", source=source, contact=contact_name, result="suggestion",
                    text=_redact(message), elapsed_ms=elapsed_ms)
        try:
            result = self.butler.push(contact_name, message)
            meta = getattr(result, "meta", {}) or {}
            if meta.get("ok"):
                self._audit("push_succeeded", source=source, contact=contact_name)
                self.log("心跳建议已发送给 %s", contact_name)
            else:
                detail = _redact(meta.get("detail", "unknown"), 1000)
                self._audit("push_failed", source=source, contact=contact_name, detail=detail)
                self.log("心跳建议发送失败 [%s]: %s", contact_name, detail)
        except Exception as exc:
            detail = _redact(exc, 1000)
            self._audit("error", source=source, phase="push", contact=contact_name,
                        error_type=type(exc).__name__, detail=detail)
            self.log("心跳建议发送失败 [%s]: %s: %s", contact_name, type(exc).__name__, detail)

    def _run_once(self) -> None:
        candidates = self._enabled_contacts()
        if not candidates:
            self._audit("trigger_started", source="scheduled")
            self._audit("trigger_skipped", source="scheduled", reason="no_enabled_contacts")
            self.log("心跳跳过：当前没有开启心跳的已配置联系人")
            return
        contact_name, policy = random.choice(candidates)
        self._run_contact(contact_name, policy, source="scheduled")

    def _run_manual(self, contact_name: str, policy: dict, ready: threading.Event) -> None:
        try:
            ready.wait()
            self._run_contact(contact_name, policy, source="manual")
        finally:
            self._lock.release()

    def trigger_contact(self, contact_name: str) -> tuple[bool, str]:
        """Queue an immediate run for one configured contact, even if auto heartbeat is off."""
        contact_name = str(contact_name or "").strip()
        self._audit("manual_trigger_requested", source="manual", contact=contact_name)
        if contact_name not in set(self.cfg.contacts.names()):
            self._audit("manual_trigger_rejected", source="manual", contact=contact_name,
                        reason="contact_not_configured")
            return False, "contact_not_configured"
        try:
            policy = self.butler.skill_policies.for_contact(contact_name)
        except Exception as exc:
            self._audit("error", source="manual", phase="policy", contact=contact_name,
                        error_type=type(exc).__name__, detail=_redact(exc, 1000))
            return False, "policy_unavailable"
        if not policy:
            self._audit("manual_trigger_rejected", source="manual", contact=contact_name,
                        reason="policy_missing")
            return False, "policy_missing"
        if not self._lock.acquire(blocking=False):
            self._audit("manual_trigger_rejected", source="manual", contact=contact_name,
                        reason="busy")
            return False, "busy"
        ready = threading.Event()
        try:
            worker = threading.Thread(target=self._run_manual,
                                      args=(contact_name, policy, ready),
                                      name="butler-heartbeat-manual", daemon=True)
            worker.start()
        except Exception as exc:
            self._lock.release()
            self._audit("error", source="manual", phase="start", contact=contact_name,
                        error_type=type(exc).__name__, detail=_redact(exc, 1000))
            return False, "start_failed"
        self._audit("manual_trigger_accepted", source="manual", contact=contact_name)
        ready.set()
        return True, "started"

    def _loop(self) -> None:
        due = self._load_next_run()
        if due is None or due <= time.time():
            due = time.time() + self._random_interval()
            self._save_next_run(due)
        self._audit("scheduler_started", next_run_at=due)
        self._audit("scheduled", next_run_at=due)
        self.log("心跳已启用，下一次检查约在 %s", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due)))
        while not self._stop.is_set():
            if self._stop.wait(max(0.0, due - time.time())):
                break
            with self._lock:
                if self._stop.is_set():
                    break
                try:
                    self._run_once()
                except Exception as exc:
                    detail = _redact(exc, 1000)
                    self._audit("error", phase="scheduler", error_type=type(exc).__name__, detail=detail)
                    self.log("心跳调度轮次异常: %s: %s", type(exc).__name__, detail)
                due = time.time() + self._random_interval()
                self._save_next_run(due)
                self._audit("scheduled", next_run_at=due)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not self.path:
            self.log("心跳未启动：hermes.root 未配置，无法保存调度状态")
            self._audit("scheduler_not_started", reason="missing_state_path")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="butler-heartbeat", daemon=True)
        self._audit("scheduler_start_requested")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._audit("scheduler_stopping")
            self._thread.join(timeout=2)
        self._audit("scheduler_stopped" if not self._thread or not self._thread.is_alive()
                    else "scheduler_stop_wait_timeout")
