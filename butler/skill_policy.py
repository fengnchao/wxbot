"""Reloadable per-contact Hermes role, skill, and heartbeat settings."""
from __future__ import annotations

import json
from pathlib import Path


class SkillPolicyStore:
    def __init__(self, path: str, log=None):
        self.path = Path(path) if path else None
        self.log = log or (lambda *a, **k: None)

    def load(self) -> dict[str, dict]:
        if self.path is None:
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            return {}
        except Exception as exc:
            self.log("读取角色技能配置失败: %s: %s", type(exc).__name__, exc)
            raise RuntimeError("角色技能配置不可读取，已停止处理以避免绕过技能白名单") from exc
        users = raw.get("users") if isinstance(raw, dict) else None
        if not isinstance(users, dict):
            raise RuntimeError("角色技能配置格式无效，已停止处理以避免绕过技能白名单")
        out = {}
        for name, item in users.items():
            if not isinstance(name, str) or not isinstance(item, dict):
                continue
            role = item.get("role_skill")
            allowed = item.get("allowed_skills")
            if not isinstance(role, str) or not role.strip() or not isinstance(allowed, list):
                raise RuntimeError(f"联系人 {name!r} 的角色技能配置无效")
            if any(not isinstance(value, str) for value in allowed):
                raise RuntimeError(f"联系人 {name!r} 的技能白名单无效")
            names = sorted({str(v).strip() for v in allowed if isinstance(v, str) and v.strip()})
            # The role skill is configured separately; Hermes adds it to the effective
            # runtime allowlist after validating its butler-role tag.
            names = [skill for skill in names if skill != role.strip()]
            out[name] = {
                "role_skill": role.strip(),
                "allowed_skills": names,
                "heartbeat_enabled": item.get("heartbeat_enabled") is True,
            }
        return out

    def for_contact(self, name: str) -> dict | None:
        return self.load().get(name)

    def heartbeat_contacts(self) -> list[tuple[str, dict]]:
        return [(name, policy) for name, policy in self.load().items()
                if policy.get("heartbeat_enabled")]
