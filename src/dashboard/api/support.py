#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Butler 配置、联系人、技能目录与心跳策略的读写（非 HTTP 层）。

只读配置文件、只向 loopback 的 Butler/Hermes 发请求，不启动也不重启任何服务。
原样搬自 server.py，供 api 处理器与测试直接调用。
"""
import json
import os
import re
import threading
import time
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from common.paths import REPO_ROOT
from dashboard import services
from dashboard.settings import load_settings

_LOG_SETTINGS = load_settings()
_home_env = os.environ.get("HERMES_HOME") or _LOG_SETTINGS['sources']['home']
HERMES_HOME = _home_env if os.path.isabs(_home_env) else os.path.join(str(REPO_ROOT), _home_env)
EXPORT_DIR = os.path.join(HERMES_HOME, "logs", "wechat-inbox")


def _default_wxbot_config():
    """按仓库自定位找 wxbot 配置：repo/config.wxbot.toml → repo/config.toml → 旧部署路径。"""
    repo = str(REPO_ROOT)
    for name in ("config.wxbot.toml", "config.toml"):
        cand = os.path.join(repo, name)
        if os.path.exists(cand):
            return cand
    return os.path.join(repo,'config.wxbot.toml')


def wxbot_config_path():
    return os.environ.get("WXBOT_CONFIG") or _LOG_SETTINGS['sources']['wxbot_config'] or _default_wxbot_config()


WXBOT_CHANNEL = os.path.join(HERMES_HOME, "scripts", "wxbot_channel.json")
_HEARTBEAT_CONFIG_LOCK = threading.Lock()


def butler_config_path():
    """Butler's Hermes credentials/profile mapping; never returned to the browser."""
    configured = os.environ.get("BUTLER_CONFIG")
    if configured:
        return configured
    if _LOG_SETTINGS['sources']['butler_config']:
        return _LOG_SETTINGS['sources']['butler_config']
    repo = str(REPO_ROOT)
    candidate = os.path.join(repo, "config.butler.toml")
    if os.path.exists(candidate):
        return candidate
    return candidate


def _load_butler_config():
    bp = services.get('butler_config_path', butler_config_path)
    try:
        with open(bp(), "rb") as fh:
            config=tomllib.load(fh)
        from butler.identity.directory import DirectoryStore,directory_path,directory_enabled
        if directory_enabled(bp(),config):
            config['contacts']=DirectoryStore(directory_path(bp(),config)).contact_rows()
        config['_connection']={'mode':services.get('dashboard_mode',dashboard_mode)()}
        return config
    except Exception as exc:
        raise RuntimeError(f"无法读取 Butler 配置（{type(exc).__name__}）") from None


def dashboard_mode():
    path=Path(services.get('wxbot_config_path',wxbot_config_path)())
    wx=tomllib.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    return (wx.get('installation') or {}).get('mode','local')


def load_butler_contacts():
    """Direct-message contacts from Butler's configured identity map."""
    config = services.get('_load_butler_config',_load_butler_config)()
    contacts = []
    for item in config.get("contacts") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        contacts.append({"name": name, "uid": str(item.get("uid") or name).strip(),
                         "profile": str(item.get("profile") or "default").strip(),
                         "label": str(item.get("label") or "").strip()})
    return contacts, config


def unified_contact_store():
    from butler.identity.contact_admin import configured_store
    return configured_store(services.get('butler_config_path',butler_config_path)())


def effective_heartbeat_policies(path):
    store = services.get('unified_contact_store',unified_contact_store)()
    return store.policies() if store else services.get('load_heartbeat_config',load_heartbeat_config)(path)


def _heartbeat_path(home, config, key, filename):
    path = str((config.get("heartbeat") or {}).get(key) or "").strip()
    if not path:
        return os.path.join(home, "cache", filename)
    # Legacy Hermes resolves these paths in its process working directory.
    if (config.get('agent') or {}).get('provider') != 'codex':
        return path
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path(services.get('butler_config_path',butler_config_path)()).resolve().parent / target
    return str(target.resolve())


def heartbeat_config_path(home, config=None):
    config = config if config is not None else services.get('_load_butler_config',_load_butler_config)()
    return _heartbeat_path(home, config, "config_file", "butler_heartbeat.json")


def heartbeat_state_path(home, config):
    return _heartbeat_path(home, config, "state_file", "butler_heartbeat_state.json")


def heartbeat_audit_path(home, config):
    return _heartbeat_path(home, config, "audit_file", "butler_heartbeat_audit.jsonl")


def trigger_butler_heartbeat(contact, config):
    """Use Butler's server token locally; its credential never reaches the browser."""
    if (config.get('_connection') or {}).get('mode','local')!='local':
        raise ValueError('当前模式的心跳由对端管理台维护')
    server = config.get("server") or {}
    host = "127.0.0.1"  # The bearer token is sent only over the local loopback interface.
    port = int(server.get("port") or 8770)
    token = str(server.get("token") or "").strip()
    if not token:
        raise RuntimeError("Butler API token 未配置")
    request = Request(
        f"http://{host}:{port}/v1/heartbeat/trigger",
        data=json.dumps({"contact": contact}, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8", "replace"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:
            payload = {"error": f"Butler 返回 HTTP {exc.code}"}
        return exc.code, payload
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"无法连接 Butler（{type(exc).__name__}）") from None
    except Exception as exc:
        raise RuntimeError(f"Butler 触发请求失败（{type(exc).__name__}）") from None


def load_heartbeat_events(path, limit=30):
    """Read recent JSONL audit rows without loading an unbounded file into memory."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            start = max(0, size - 1_048_576)
            fh.seek(start)
            if start:
                fh.readline()  # discard a possible partial first row
            lines = fh.readlines()[-limit:]
    except FileNotFoundError:
        return []
    events = []
    for line in reversed(lines):
        try:
            row = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue
        if isinstance(row, dict):
            events.append(row)
    return events


def load_heartbeat_status(home, config, limit=30):
    state = {}
    state_error = ""
    try:
        with open(heartbeat_state_path(home, config), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if isinstance(raw, dict):
            state = raw
    except FileNotFoundError:
        pass
    except Exception as exc:
        state_error = type(exc).__name__
    try:
        events = load_heartbeat_events(heartbeat_audit_path(home, config), limit)
    except Exception as exc:
        events = []
        audit_error = type(exc).__name__
    else:
        audit_error = ""
    return {"next_run_at": state.get("next_run_at"), "state_error": state_error,
            "audit_error": audit_error, "events": events}


def load_heartbeat_config(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        raise RuntimeError(f"心跳配置文件不可读取（{type(exc).__name__}）") from None
    users = raw.get("users") if isinstance(raw, dict) else None
    if not isinstance(users, dict):
        raise RuntimeError("心跳配置格式无效")
    for name, policy in users.items():
        if (not isinstance(name, str) or not isinstance(policy, dict)
                or not isinstance(policy.get("role_skill"), str)
                or not policy.get("role_skill", "").strip()
                or not isinstance(policy.get("allowed_skills"), list)
                or any(not isinstance(skill, str) for skill in policy.get("allowed_skills", []))
                or not isinstance(policy.get("heartbeat_enabled"), bool)):
            raise RuntimeError("心跳配置包含格式无效的联系人策略")
    return users


def validate_policy_skills(users,changed,config):
    contacts={c.get('name'):c for c in config.get('contacts',[]) if isinstance(c,dict)}
    for name in changed:
        contact=contacts.get(name)
        if contact is None:raise ValueError('联系人不在Butler配置中')
        try:skills=fetch_hermes_skills(contact,config)
        except Exception as exc:raise RuntimeError('Hermes技能目录验证失败（'+type(exc).__name__+'）') from None
        roles={s['name'] for s in skills if is_butler_role_skill(s)}
        tools={s['name'] for s in skills if not is_butler_role_skill(s)}
        policy=users[name]
        if policy['role_skill'] not in roles:raise ValueError('角色Skill不存在或缺少butler-role标签')
        if not set(policy['allowed_skills'])<=tools:raise ValueError('工具白名单包含不存在的技能或角色技能')


def save_heartbeat_config(path, users):
    payload = {"version": 1, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "users": users}
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def fetch_hermes_skills(contact, config):
    if (config.get('agent') or {}).get('provider')=='codex':
        payload=services.get('fetch_butler_data',fetch_butler_data)(config,'/v1/skills')
        rows=payload.get('data')
        if not isinstance(rows,list):raise RuntimeError('Butler 技能目录格式无效')
        return rows
    hermes = config.get("hermes") or {}
    base = str(hermes.get("url") or "http://127.0.0.1:8642").rstrip("/")
    profile = str(contact.get("profile") or "default")
    if hermes.get("profile_in_path", False):
        url = f"{base}/p/{quote(profile, safe='')}/v1/skills"
    else:
        url = f"{base}/v1/skills"
    headers = {"Accept": "application/json"}
    api_key = str(hermes.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = services.get('Request',Request)(url, headers=headers)
    open_url = services.get('urlopen',urlopen)
    try:
        with open_url(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except HTTPError as exc:
        raise RuntimeError(f"Hermes 技能目录请求失败（HTTP {exc.code}）") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"无法连接 Hermes（{type(exc).__name__}）") from None
    except Exception as exc:
        raise RuntimeError(f"Hermes 技能目录响应无效（{type(exc).__name__}）") from None
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("Hermes 技能目录格式无效")
    skills = []
    for item in rows:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        raw_tags = item.get("tags")
        tags = sorted({tag.strip() for tag in raw_tags
                       if isinstance(tag, str) and tag.strip()}, key=str.casefold) \
            if isinstance(raw_tags, list) else []
        skills.append({"name": item["name"], "description": str(item.get("description") or ""),
                       "category": str(item.get("category") or ""), "tags": tags})
    return skills


def fetch_butler_data(config,path):
    if (config.get('_connection') or {}).get('mode','local')!='local':
        raise ValueError('当前接入方式不提供本地 Butler 业务管理，请使用对端管理台')
    server=config.get('server') or {}
    request=services.get('Request',Request)(f"http://127.0.0.1:{int(server.get('port') or 8770)}"+path,
        headers={'Authorization':'Bearer '+str(server.get('token') or ''),'Accept':'application/json'})
    try:
        with services.get('urlopen',urlopen)(request,timeout=15) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as exc:
        raise RuntimeError('Butler 数据请求失败（'+type(exc).__name__+'）') from None


def is_butler_role_skill(skill):
    return any(str(tag).strip().casefold() == "butler-role"
               for tag in skill.get("tags", []))
