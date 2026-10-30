#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""角色心跳：策略读写、执行状态、技能目录与立即触发。"""


def read_config(ctx):
    """每个联系人当前生效的角色 skill、工具白名单与心跳开关。"""
    contacts, config = ctx.load_butler_contacts()
    path = ctx.heartbeat_config_path(ctx.home, config)
    with ctx._HEARTBEAT_CONFIG_LOCK:
        users = ctx.effective_heartbeat_policies(path)
    names = {item["name"] for item in contacts}
    policies = {name: users[name] for name in names if name in users}
    heartbeat = config.get("heartbeat") or {}
    interval_min = max(1, int(heartbeat.get("min_interval_minutes") or 180))
    interval_max = max(interval_min, int(heartbeat.get("max_interval_minutes") or 360))
    store = ctx.unified_contact_store()
    return 200, {
        "version": store.snapshot()['version'] if store else None,
        "contacts": contacts,
        "policies": policies,
        "interval_minutes": {"min": interval_min, "max": interval_max},
    }


def status(ctx):
    """下次计划时间 + 最近执行记录。"""
    contacts, config = ctx.load_butler_contacts()
    path = ctx.heartbeat_config_path(ctx.home, config)
    with ctx._HEARTBEAT_CONFIG_LOCK:
        users = ctx.effective_heartbeat_policies(path)
    payload = ctx.load_heartbeat_status(ctx.home, config,
                                        max(1, min(100, ctx.num("limit", 30))))
    names = {item["name"] for item in contacts}
    payload["enabled_contacts"] = sum(
        1 for name, policy in users.items()
        if name in names and policy.get("heartbeat_enabled") is True)
    return 200, payload


def skills(ctx):
    """服务端读取该联系人 Profile 的 Hermes 技能目录。"""
    contacts, config = ctx.load_butler_contacts()
    contact = next((item for item in contacts if item["name"] == ctx.one("contact")), None)
    if ctx.one('id'):
        row = ctx.contact_admin().read(id=ctx.one('id'))['row']
        contact = next(iter(row['conversations']), {'name': row['name'], 'profile': 'default'})
    if contact is None:
        return 400, {"error": "未知的 Butler 联系人"}
    return 200, {"contact": contact["name"], "profile": contact["profile"],
                 "skills": ctx.fetch_hermes_skills(contact, config)}


def trigger(ctx):
    """立即触发一次心跳（凭证只在本机 loopback 使用）。"""
    body = ctx.body()
    contact_name = str(body.get("contact") or "").strip()
    contacts, config = ctx.load_butler_contacts()
    if not any(item["name"] == contact_name for item in contacts):
        return 400, {"ok": False, "error": "未知的 Butler 联系人"}
    code, result = ctx.trigger_butler_heartbeat(contact_name, config)
    if code >= 400:
        return code, {"ok": False, "code": result.get("code"),
                      "error": result.get("error") or f"Butler 返回 HTTP {code}"}
    return 202, {"ok": True, "status": "started", "contact": contact_name}


def save_config(ctx):
    """原子保存角色 skill 与心跳策略（只写配置文件，不动任何库）。"""
    body = ctx.body()
    store = ctx.unified_contact_store()
    if store:
        if not ctx.confirm('X-Wxbot-Contact-Action'):
            return 403, {'error': '请从联系人页面确认角色修改'}
        try:
            conversation = next((c for c in store.snapshot()['conversations']
                                 if c['name'] == body.get('contact')), None)
            if conversation is None:
                raise ValueError('联系人会话不存在')
            policy = {k: body.get(k) for k in ('role_skill', 'allowed_skills', 'heartbeat_enabled')}
            saved = ctx.contact_admin().save({'action': 'conversation',
                                              'version': body.get('version'),
                                              'id': conversation['id'], 'policy': policy})
            return 200, {'ok': True, 'version': saved['version'],
                         'contact': conversation['name'], 'policy': policy}
        except ValueError as exc:
            return (409 if 'version conflict' in str(exc) else 400), {'error': str(exc)}
    contact_name = str(body.get("contact") or "").strip()
    contacts, config = ctx.load_butler_contacts()
    contact = next((item for item in contacts if item["name"] == contact_name), None)
    if contact is None:
        return 400, {"ok": False, "error": "未知的 Butler 联系人"}
    role = str(body.get("role_skill") or "").strip()
    allowed = body.get("allowed_skills")
    enabled = body.get("heartbeat_enabled")
    if not role or len(role) > 128:
        return 400, {"ok": False, "error": "必须选择有效的角色 skill"}
    if not isinstance(allowed, list) or any(not isinstance(x, str) for x in allowed):
        return 400, {"ok": False, "error": "allowed_skills 必须是字符串列表"}
    if not isinstance(enabled, bool):
        return 400, {"ok": False, "error": "heartbeat_enabled 必须是布尔值"}
    skills = ctx.fetch_hermes_skills(contact, config)
    skill_by_name = {item["name"]: item for item in skills}
    role_skill = skill_by_name.get(role)
    if role_skill is None or not ctx.is_butler_role_skill(role_skill):
        return 400, {"ok": False, "error": "角色 skill 必须存在且带有 butler-role 标签"}
    role_names = {item["name"] for item in skills if ctx.is_butler_role_skill(item)}
    requested = {x.strip() for x in allowed if x.strip()}
    # Accept the role in an older browser draft, but never persist it as a tool.
    requested.discard(role)
    if requested & role_names:
        return 400, {"ok": False, "error": "角色 skill 不能放入允许调用的工具列表"}
    tool_names = set(skill_by_name) - role_names
    if not requested <= tool_names:
        return 400, {"ok": False, "error": "技能已不在 Hermes 可用目录中，请刷新后重试"}
    path = ctx.heartbeat_config_path(ctx.home, config)
    with ctx._HEARTBEAT_CONFIG_LOCK, ctx.config_lock(path):
        users = ctx.load_heartbeat_config(path)
        valid_contacts = {item["name"] for item in contacts}
        users = {name: value for name, value in users.items() if name in valid_contacts}
        users[contact_name] = {
            "role_skill": role,
            "allowed_skills": sorted(requested),
            "heartbeat_enabled": enabled,
        }
        ctx.save_heartbeat_config(path, users)
    return 200, {"ok": True, "contact": contact_name, "policy": users[contact_name]}
