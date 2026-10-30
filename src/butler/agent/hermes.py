"""Hermes 客户端：管家和 Hermes（大模型 + skill 运行时的唯一入口）之间的那一层。

两件事必须同时给：
  X-Hermes-Session-Key → 长期记忆/档案的归属（跨会话）
  X-Hermes-Session-Id  → 会话连续性（同一段对话的历史从 state.db 读回来）
只给 Key 不给 Id 时，服务端按 (system_prompt, 首条用户消息) 派生新会话 —— 表现就是
"每条消息一段新对话"，管家每轮都从零重读档案，又慢又失忆。
"""
from __future__ import annotations

import json
import hashlib
import urllib.error
import urllib.request
import time
from urllib.parse import quote

from common.flow_trace import record, tracing
from butler.agent.hermes_stream import read_complete

from butler.identity.contacts import Contact
from butler.runtime.concurrency import RuntimeLocks


def header_value(value: str) -> str:
    """HTTP 头只接受 latin-1：非 ASCII（群聊兜底联系人的 uid 就是中文群名）必须转义，
    否则 urllib 在发包前就抛 UnicodeEncodeError: 'latin-1' codec ... position 23-27。

    百分号转义是确定性的：同一个群每轮得到同一个 Key，记忆归属不变。
    中文原文照旧走 body（身份提示，UTF-8），不受影响。
    """
    s = str(value or "")
    return s if s.isascii() else quote(s, safe="")


class HermesError(Exception):
    def __init__(self, msg: str, status: int = 0, detail: str = ""):
        super().__init__(msg)
        self.status = status
        self.detail = detail


class HermesClient:
    def __init__(self, cfg, log=None, *, locks=None):
        self.base = cfg.hermes_url
        self.api_key = cfg.hermes_key
        self.model = cfg.hermes_model
        self.timeout = cfg.hermes_timeout
        self.send_identity = cfg.send_identity
        self.profile_in_path = getattr(cfg, "hermes_profile_in_path", False)
        self.log = log or (lambda *a, **k: None)
        self.session_ids: dict[tuple, str] = {}        # canonical identity/policy/kind → SID
        self.locks = locks or RuntimeLocks(self.base)

    # ---------- URL 拼接 ----------
    def _api_base(self, profile: str) -> str:
        """返回接口前缀：带命名 Profile 时为 {base}/p/{profile}，否则为扁平的 {base}。"""
        return f"{self.base}/p/{profile}" if self.profile_in_path else self.base

    # ---------- 会话 ----------
    def _session_scope(self, contact: Contact, skill_policy: dict | None, session_kind: str) -> tuple[tuple, str]:
        identity = (self.base.rstrip('/'), contact.profile, contact.key())
        # Keep the legacy DM session id untouched until a user gets an explicit policy.
        if session_kind == "chat" and not skill_policy:
            return (*identity, 'chat', ''), contact.session_id()
        scoped_policy = ({"role_skill": skill_policy.get("role_skill"),
                         "allowed_skills": sorted(skill_policy.get("allowed_skills") or [])}
                        if skill_policy else {})
        encoded = json.dumps(scoped_policy, ensure_ascii=False, sort_keys=True).encode("utf-8")
        policy_tag = hashlib.sha256(encoded).hexdigest()[:12]
        kind = "heartbeat" if session_kind == "heartbeat" else "chat"
        key = (*identity, kind, policy_tag)
        return key, f"{contact.session_id()}-{kind}-{policy_tag}"

    def session_guard(self, contact, *, skill_policy=None, session_kind='chat'):
        return self.locks.session(contact, session_kind=session_kind)

    def session_id(self, contact: Contact, *, skill_policy: dict | None = None,
                   session_kind: str = "chat") -> str:
        with self.session_guard(contact, session_kind=session_kind):
            key, initial = self._session_scope(contact, skill_policy, session_kind)
            return self.session_ids.get(key) or initial

    def reset(self, contact: Contact, *, skill_policy: dict | None = None,
              session_kind: str = "chat") -> None:
        import uuid
        with self.session_guard(contact, session_kind=session_kind):
            key, initial = self._session_scope(contact, skill_policy, session_kind)
            self.session_ids[key] = f"{initial}-{uuid.uuid4().hex[:12]}"

    # ---------- 探活（不跑 agent、不污染会话）----------
    def alive(self, profile: str) -> bool:
        req = urllib.request.Request(f"{self._api_base(profile)}/v1/models",
                                     headers=self._headers(profile, None))
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status == 200
        except urllib.error.HTTPError as e:
            # 401 说明它在监听但 key 不对 —— 一样是"不通"
            self.log("models %s HTTP %s", profile, e.code)
            return False
        except Exception as e:
            self.log("models %s 异常: %s", profile, e)
            return False

    # ---------- 主调用 ----------
    def _headers(self, profile: str, session_key: str | None) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if session_key:
            h["X-Hermes-Session-Key"] = header_value(session_key)
        return h

    def chat(self, contact: Contact, text: str, *, extra_system: str = "",
             timeout: int | None = None, skill_policy: dict | None = None,
             session_kind: str = "chat") -> str:
        with self.session_guard(contact, session_kind=session_kind):
            return self._chat(contact, text, extra_system=extra_system, timeout=timeout,
                              skill_policy=skill_policy, session_kind=session_kind)

    def _chat(self, contact: Contact, text: str, *, extra_system: str = "",
              timeout: int | None = None, skill_policy: dict | None = None,
              session_kind: str = "chat") -> str:
        """把一条用户消息交给 Hermes，返回最终文本。失败抛 HermesError。"""
        messages = []
        if extra_system:
            messages.append({"role": "system", "content": extra_system})
        if self.send_identity:
            messages.append({"role": "system", "content": contact.identity()})
        messages.append({"role": "user", "content": text})

        url = f"{self._api_base(contact.profile)}/v1/chat/completions"
        headers = self._headers(contact.profile, contact.key())
        session_key, sid = self._session_scope(contact, skill_policy, session_kind)
        sid = self.session_ids.get(session_key) or sid
        headers["X-Hermes-Session-Id"] = header_value(sid)
        body = {"model": self.model, "messages": messages, "stream": tracing()}
        if body['stream']:
            body['hermes_final_response'] = True
        if skill_policy:
            body["skill_policy"] = {
                "role_skill": skill_policy["role_skill"],
                "allowed_skills": list(skill_policy["allowed_skills"]),
                "read_only": session_kind == "heartbeat",
            }

        started = time.monotonic()
        record('hermes_request','started',profile=contact.profile,session_id=sid)
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                record('hermes_request','accepted',http_status=getattr(r,'status',200),
                       profile=contact.profile,session_id=sid)
                echoed = (r.headers.get("X-Hermes-Session-Id") or "").strip()
                if echoed:
                    self.session_ids[session_key] = echoed   # 服务端改写 id 也不丢连续性
                if 'text/event-stream' in (r.headers.get('Content-Type') or '').lower():
                    reply = read_complete(r,timeout or self.timeout)
                    record('hermes_result','ok',characters=len(reply),progress_available=True,
                           elapsed_ms=round((time.monotonic()-started)*1000))
                    return reply
                data = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            record('hermes_result','error',http_status=e.code,error_type=type(e).__name__,
                   elapsed_ms=round((time.monotonic()-started)*1000))
            detail = e.read().decode("utf-8", "replace")[:300]
            raise HermesError(f"Hermes API HTTP {e.code}", e.code, detail) from None
        except Exception as e:
            record('hermes_result','error',error_type=type(e).__name__,
                   error_code=getattr(e,'code',''),
                   elapsed_ms=round((time.monotonic()-started)*1000))
            raise HermesError(f"Hermes API 调用失败: {type(e).__name__}: {e}") from None

        try:
            choice = data['choices'][0]
            flags = data.get('hermes') or {}
            if (data.get('error') or choice.get('finish_reason') not in (None,'stop') or
                    flags.get('completed') is False or flags.get('partial') or flags.get('failed')):
                raise ValueError('Hermes did not finish normally')
            reply = (choice['message'].get('content') or '').strip()
        except Exception:
            record('hermes_result','error',error_type='InvalidResponse')
            raise HermesError("Hermes 返回体无效或回复不完整") from None
        record('hermes_result','ok',characters=len(reply),progress_available=False,
               elapsed_ms=round((time.monotonic()-started)*1000))
        return reply
