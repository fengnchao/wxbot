#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信日志、收发队列和配置总览

只做一件事：把微信机器人（wechat-butler）**收到的消息**按发送人分组记下来。
展示消息与请求流转、工具执行状态；不记录模型内部推理或工具参数/结果。

数据源：$HERMES_HOME/state.db 及 $HERMES_HOME/profiles/*/state.db 里
        role=user 且 source=weixin 的消息，跨库按发送人 uid 合并。
称呼：$HERMES_HOME/butler_profiles/{uid}.json 的 answers["0"]（管家档案里的用户称呼）

用法:
    python server.py                 # http://127.0.0.1:8788
    python server.py --port 9000

接口:
    GET /                        按用户分组的收件日志页面（含「wxbot 通道」标签页）
    GET /api/users               用户列表（含称呼、消息数、首末时间）
    GET /api/messages?uid=&q=&limit=&with_reply=1
    GET /api/stats
    GET /api/jobs                定时任务（按归属分组：用户 / 全局任务 / 无归属）
    GET /api/wxbot               wxbot 通道流水（收到/回复/外发 + agent 耗时 + 任务归属）
    GET /api/flow                消息流转：队列事实 + 按 contact/msg_id 关联的服务阶段
    GET /api/groups              用户分组字典（messageType → 绑定用户，看板可展开维护）
    POST /api/groups             {type, action: bind|unbind, user} 增删绑定
    GET /api/heartbeat-config    联系人角色、skill 和心跳策略
    GET /api/heartbeat-status    心跳下次计划时间和最近执行记录
    POST /api/heartbeat-trigger  立即触发指定联系人的一次心跳
    GET /api/skills?contact=     服务端读取该联系人 Profile 的 Hermes 技能目录
    GET /api/queue              SQLite 收发队列、逐用户阻塞原因与恢复命令（只读）
    POST /api/queue-action      显式确认后重试、确认已发或丢弃指定异常任务
    GET /api/configuration      wxbot/Butler/角色心跳/分组配置及默认值（服务端脱敏）
    POST /api/heartbeat-config   原子保存角色技能与心跳策略
                                 （只写配置文件，不动任何库）
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
# Direct `python log/server.py` and file-based test imports use the same modules.
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))
from log.config_view import ConfigView
from log.config_editor import ConfigEditor,ConfigConflict,config_lock
from log.settings import load_settings,config_path as log_config_path
from log.queue_view import QueueView
from log.queue_actions import QueueActions
from log.user_admin import request_user_admin
from log.flow_view import FlowView
from log.workflow_view import WorkflowView
from log.telegram_view import TelegramView, ISSUES as TELEGRAM_ISSUES, TERMINAL as TELEGRAM_TERMINAL
from log.telegram_relay_admin import TelegramRelayAdmin, request_resolution as request_relay_resolution
from butler.telegram_relay.settings import SettingsConflict
from common import news_config
_LOG_SETTINGS=load_settings()
HERMES_HOME = os.environ.get("HERMES_HOME") or _LOG_SETTINGS['sources']['home']
EXPORT_DIR = os.path.join(HERMES_HOME, "logs", "wechat-inbox")


# wxbot 侧的绑定关系（联系人 ↔ Profile ↔ uid）唯一事实来源
def _default_wxbot_config():
    """按仓库自定位找 wxbot 配置：repo/config.wxbot.toml → repo/config.toml → 旧部署路径。"""
    repo = os.path.dirname(HERE)
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
    repo = os.path.dirname(HERE)
    candidate = os.path.join(repo, "config.butler.toml")
    if os.path.exists(candidate):
        return candidate
    return candidate


def _load_butler_config():
    try:
        with open(butler_config_path(), "rb") as fh:
            return tomllib.load(fh)
    except Exception as exc:
        raise RuntimeError(f"无法读取 Butler 配置（{type(exc).__name__}）") from None


def load_butler_contacts():
    """Direct-message contacts from Butler's configured identity map."""
    config = _load_butler_config()
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


def heartbeat_config_path(home, config=None):
    config = config if config is not None else _load_butler_config()
    path = str((config.get("heartbeat") or {}).get("config_file") or "").strip()
    return path or os.path.join(home, "cache", "butler_heartbeat.json")


def heartbeat_state_path(home, config):
    path = str((config.get("heartbeat") or {}).get("state_file") or "").strip()
    return path or os.path.join(home, "cache", "butler_heartbeat_state.json")


def heartbeat_audit_path(home, config):
    path = str((config.get("heartbeat") or {}).get("audit_file") or "").strip()
    return path or os.path.join(home, "cache", "butler_heartbeat_audit.jsonl")


def trigger_butler_heartbeat(contact, config):
    """Use Butler's server token locally; its credential never reaches the browser."""
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
        payload=fetch_butler_data(config,'/v1/skills')
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
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
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
    server=config.get('server') or {}
    request=Request(f"http://127.0.0.1:{int(server.get('port') or 8770)}"+path,
        headers={'Authorization':'Bearer '+str(server.get('token') or ''),'Accept':'application/json'})
    try:
        with urlopen(request,timeout=15) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as exc:
        raise RuntimeError('Butler 数据请求失败（'+type(exc).__name__+'）') from None


def is_butler_role_skill(skill):
    return any(str(tag).strip().casefold() == "butler-role"
               for tag in skill.get("tags", []))


# ---------------------------------------------------------------- 库

def discover_dbs(home):
    out = []
    root = os.path.join(home, "state.db")
    if os.path.exists(root):
        out.append(("default", root))
    pdir = os.path.join(home, "profiles")
    if os.path.isdir(pdir):
        for name in sorted(os.listdir(pdir)):
            f = os.path.join(pdir, name, "state.db")
            if os.path.exists(f):
                out.append((name, f))
    return out


def connect(path):
    conn = sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro",
                           uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def safe_query(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []


# ---------------------------------------------------------------- 发送人

_BARE_RE = re.compile(r"^(o?[A-Za-z0-9_\-]+?)(@.*)?$")


def bare_uid(raw):
    """o9cq80yV5TxiLotH1TCijgCVcCOI@im.wechat -> o9cq80yV5TxiLotH1TCijgCVcCOI"""
    if not raw:
        return ""
    return str(raw).split("@")[0].strip()


def load_directory(home):
    """
    返回 {bare_uid: {name, source_file, kind}}
    优先用 butler_profiles 里的称呼，其次 {uid}_user.json 的 name。
    """
    out = {}
    roots = [os.path.join(home, "butler_profiles")]
    pdir = os.path.join(home, "profiles")
    if os.path.isdir(pdir):
        for p in os.listdir(pdir):
            roots.append(os.path.join(pdir, p, "butler_profiles"))
    for root in roots:
        if not os.path.isdir(root):
            continue
        for fn in os.listdir(root):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(root, fn)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            uid = bare_uid(d.get("user_id") or fn.replace(".json", ""))
            if not uid or uid.startswith("test_user") or uid.startswith("_"):
                continue
            name = ""
            if fn.endswith("_user.json"):
                name = (d.get("name") or "").strip()
            else:
                ans = d.get("answers") or {}
                name = (ans.get("0") or "").strip()
                # 兼容 answers 为 list 的旧结构
                if not name and isinstance(ans, list) and ans:
                    name = str(ans[0]).strip()
            rec = out.setdefault(uid, {"uid": uid, "name": "", "files": []})
            rec["files"].append(os.path.basename(path))
            if name and not rec["name"]:
                rec["name"] = name
    return out


def display_of(uid, directory):
    rec = directory.get(uid) or {}
    return rec.get("name") or uid


def display_of_ci(uid_bare, directory):
    """按 uid 全小写匹配目录（Profile 名是小写的 uid）。"""
    if not uid_bare:
        return ""
    low = uid_bare.lower()
    for k, v in directory.items():
        if k.lower() == low:
            return v.get("name") or k
    return ""


# ---------------------------------------------------------------- 定时任务

def _parse_deliver_uid(deliver):
    """'weixin:o9cq80...@im.wechat' -> 'o9cq80...@im.wechat'；其它（origin/local/all）-> ''"""
    if not deliver:
        return ""
    d = str(deliver)
    if not d.startswith("weixin:"):
        return ""
    rest = d.split(":", 1)[1]
    rest = rest.split(":")[0]          # 去掉 thread_id
    return rest if "@" in rest else ""


_JOB_TEXT_MAX = 65536       # 扫脚本源码最多读 64KB

_SCRIPT_TARGET_RE = re.compile(r"""(?m)^\s*TARGET\s*=\s*["']([^"']{1,64})["']""")
_SCRIPT_PROFILE_RE = re.compile(r"""["'](?:wxbot|wechat)-([A-Za-z0-9_\-]{1,64})["']""")
_PROMPT_CONTACT_RE = re.compile(
    r"--(?:contact|to)[=\s]+[\"']?([A-Za-z0-9_\-\.@\u4e00-\u9fff]{1,64})")


def _job_scripts_dir(home, prof):
    """任务脚本目录：default → {home}/scripts；其它 profile → {home}/profiles/<p>/scripts
    （对齐 Hermes 规则：profile 的脚本互不共享）。"""
    if prof and prof != "default":
        return os.path.join(home, "profiles", str(prof), "scripts")
    return os.path.join(home, "scripts")


def _read_job_sidecar(home, prof, script):
    """脚本同名 sidecar json（morning_report.py → morning_report.json）。

    Hermes 侧 no_agent 脚本的约定：{"type": 1|2, "messageType": 1|2|3, "contact": "<窗口标题>"}。
    type=1 单发给 contact；type=2 群发（收件人由「用户分组」字典按 messageType 决定）。
    无 sidecar / 读不出 → {}。
    """
    if not script:
        return {}
    stem = os.path.splitext(os.path.basename(str(script)))[0]
    if not stem:
        return {}
    path = os.path.join(_job_scripts_dir(home, prof), stem + ".json")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _scan_script_owner(home, prof, script):
    """扫脚本文本里的收件人线索 → (uid, source)：
    1) TARGET = "101"（Hermes 生成的提醒 wrapper → script-target）
    2) "wxbot-101" / "wechat-101" 字面量（butler_reminder_* wrapper 的 profile 参数 → script-profile）
    """
    if not script:
        return "", ""
    path = os.path.join(_job_scripts_dir(home, prof), os.path.basename(str(script)))
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(_JOB_TEXT_MAX)
    except Exception:
        return "", ""
    m = _SCRIPT_TARGET_RE.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip(), "script-target"
    m = _SCRIPT_PROFILE_RE.search(text)
    if m:
        return m.group(1), "script-profile"
    return "", ""


def _scan_prompt_owner(prompt):
    """agent 任务的归属线索：prompt 里实际执行的 --contact X / --to X（如自检任务）。"""
    m = _PROMPT_CONTACT_RE.search(str(prompt or ""))
    return m.group(1) if m else ""


def collect_jobs(home):
    """读所有 Profile 的 cron/jobs.json，按发送人归属。

    归属优先级：deliver 里的 weixin uid > Profile 名反推 > script 同名 json
    （type=1→contact / type=2→全局群发）> 脚本文本内置目标（TARGET="x" / "wxbot-x" 字面量）
    > prompt 里的 --contact/--to。都推不出来 → 无归属。
    """
    out = []
    root = os.path.join(home, "cron", "jobs.json")
    targets = [("default", root)]
    pdir = os.path.join(home, "profiles")
    if os.path.isdir(pdir):
        for p in sorted(os.listdir(pdir)):
            f = os.path.join(pdir, p, "cron", "jobs.json")
            if os.path.exists(f):
                targets.append((p, f))

    for prof, path in targets:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
        except Exception:
            continue
        jobs = data if isinstance(data, list) else (data.get("jobs") or [])
        for j in jobs:
            if not isinstance(j, dict):
                continue
            deliver = j.get("deliver") or ""
            uid = _parse_deliver_uid(deliver)
            owner = uid
            owner_src = "deliver"
            if not owner and prof.startswith("wxbot-"):
                _wm = load_wxbot_profile_map()
                if _wm.get(prof):
                    owner = _wm[prof]
                    owner_src = "profile"
            if not owner and prof.startswith("wechat-"):
                owner = prof[len("wechat-"):]     # Profile 名 = uid 小写
                owner_src = "profile"
            # —— no_agent 脚本线索（deliver=local 时靠这两条兜底）——
            script = str(j.get("script") or "")
            side = _read_job_sidecar(home, prof, script)
            ptype = _as_pos_int(side.get("type"))
            mtype = _as_pos_int(side.get("messageType"))
            is_global = False
            if not owner:
                if ptype == 2:                          # 群发：收件人由「用户分组」字典定
                    is_global = True
                    owner_src = "script"
                elif ptype == 1 and str(side.get("contact") or "").strip():
                    owner = str(side["contact"]).strip()
                    owner_src = "script"
                else:
                    cand, cand_src = _scan_script_owner(home, prof, script)
                    if cand:
                        owner, owner_src = cand, cand_src
                    else:
                        cand = _scan_prompt_owner(j.get("prompt"))
                        if cand:
                            owner, owner_src = cand, "prompt"
            sched = j.get("schedule")
            if isinstance(sched, dict):
                sched = sched.get("display") or json.dumps(sched, ensure_ascii=False)
            rep = j.get("repeat")
            if isinstance(rep, dict):
                times = rep.get("times")
                done = rep.get("completed")
                rep = "forever" if times is None else f"{done or 0}/{times}"
            out.append({
                "profile": prof,
                "job_id": j.get("id"),
                "name": j.get("name") or "(未命名)",
                "schedule": sched or "",
                "deliver": deliver,
                "uid": owner,
                "uid_key": (owner or "").split("@")[0].lower(),
                "uid_source": owner_src,
                "scope": "global" if is_global else ("user" if owner else ""),
                "push_type": ptype,          # sidecar 的 type：1 单发 / 2 群发
                "message_type": mtype,       # sidecar 的 messageType
                "enabled": bool(j.get("enabled")),
                "state": j.get("state") or ("scheduled" if j.get("enabled") else "paused"),
                "script": script,
                "no_agent": bool(j.get("no_agent")),
                "repeat": rep or "",
                "next_run_at": j.get("next_run_at"),
                "last_run_at": j.get("last_run_at"),
                "last_status": j.get("last_status"),
                "last_error": j.get("last_error"),
                "last_delivery_error": j.get("last_delivery_error"),
                "paused_at": j.get("paused_at"),
                "created_at": j.get("created_at"),
                "prompt": (j.get("prompt") or "")[:600],
            })
    return out


def jobs_ui_state(job):
    """把 Hermes 内部状态映射成卡片上显示的四种。"""
    st = (job.get("state") or "").lower()
    if job.get("last_delivery_error") or (job.get("last_status") or "").lower() == "error":
        return "error"
    if st == "completed":
        return "done"
    if st in ("paused", "disabled") or not job.get("enabled"):
        return "paused"
    return "active"


# ---------------------------------------------------------------- 收件消息

def _msg_key(uid, ts, content):
    h = hashlib.md5((str(content)[:200]).encode("utf-8", "ignore")).hexdigest()[:10]
    return f"{uid}|{int(ts or 0)}|{h}"


def collect_inbound(home):
    """
    返回 (rows, stats)
    rows: 每条收到的消息 {uid, name, ts, content, session_id, profile, session_key}
    跨库合并 + 按 (uid, 时间, 内容) 去重。
    """
    seen = set()
    rows = []
    per_db = []
    for prof, path in discover_dbs(home):
        conn = connect(path)
        try:
            sql = ("SELECT m.id, m.session_id, m.content, m.timestamp, "
                   "       s.user_id, s.session_key, s.chat_id, s.source "
                   "FROM messages m JOIN sessions s ON s.id = m.session_id "
                   "WHERE m.role = 'user' AND s.source LIKE '%eixin%' "
                   "ORDER BY m.timestamp ASC")
            n = 0
            for r in safe_query(conn, sql):
                uid = bare_uid(r["user_id"])
                if not uid and r["session_key"]:
                    uid = bare_uid(str(r["session_key"]).rsplit(":", 1)[-1])
                if not uid:
                    continue
                content = r["content"] or ""
                if not content.strip():
                    continue
                # 跳过系统注入的伪 user 消息
                if content.lstrip().startswith("[IMPORTANT: You are running as"):
                    continue
                key = _msg_key(uid, r["timestamp"], content)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "uid": uid,
                    "ts": r["timestamp"],
                    "content": content,
                    "session_id": r["session_id"],
                    "profile": prof,
                    "session_key": r["session_key"],
                    "chat_id": r["chat_id"],
                })
                n += 1
            per_db.append({"profile": prof, "path": path, "inbound": n})
        finally:
            conn.close()
    rows.sort(key=lambda x: x["ts"] or 0)
    return rows, per_db


def collect_outbound(home):
    """
    取机器人**真实发出去**的消息 —— 来自 delivery_obligations（网关外发队列，
    state='delivered' 才是真送到用户手里的），按发送人 uid 归组。
    返回 {uid: [(ts, content, state), ...]}，已按时间排序。
    """
    out = {}
    for prof, path in discover_dbs(home):
        conn = connect(path)
        try:
            sql = ("SELECT chat_id, session_key, platform, content, state, created_at "
                   "FROM delivery_obligations WHERE content IS NOT NULL "
                   "AND TRIM(content) != '' ORDER BY created_at ASC")
            for r in safe_query(conn, sql):
                uid = bare_uid(r["chat_id"])
                if not uid and r["session_key"]:
                    uid = bare_uid(str(r["session_key"]).rsplit(":", 1)[-1])
                if not uid:
                    continue
                out.setdefault(uid, []).append(
                    (r["created_at"] or 0, r["content"], r["state"] or ""))
        finally:
            conn.close()
    for k in out:
        out[k].sort(key=lambda x: x[0])
    return out


def build_users(home, directory):
    rows, per_db = collect_inbound(home)
    now = time.time()
    users = {}
    for m in rows:
        u = users.setdefault(m["uid"], {
            "uid": m["uid"],
            "name": display_of(m["uid"], directory),
            "has_profile": m["uid"] in directory,
            "count": 0,
            "first_at": m["ts"],
            "last_at": m["ts"],
            "chars": 0,
            "last_message": "",
            "days_7": 0,
            "sessions": set(),
        })
        u["count"] += 1
        u["chars"] += len(m["content"])
        u["first_at"] = min(u["first_at"], m["ts"] or now)
        u["last_at"] = max(u["last_at"], m["ts"] or 0)
        if (now - (m["ts"] or 0)) <= 7 * 86400:
            u["days_7"] += 1
        u["sessions"].add((m["profile"], m["session_id"]))
    out = []
    for u in users.values():
        u["session_count"] = len(u["sessions"])
        u.pop("sessions", None)
        u["last_message"] = next(
            (m["content"] for m in reversed(rows) if m["uid"] == u["uid"]), "")[:120]
        out.append(u)
    out.sort(key=lambda x: x["last_at"] or 0, reverse=True)
    return out, rows, per_db


# ---------------------------------------------------------------- wxbot 通道

def _decode_line(raw):
    """
    wxbot.log 历史上混有 UTF-8 与 GBK 行 —— 必须逐行先按 utf-8 解、失败再按 gbk 解。
    （整文件一次性解码会炸。）
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("gbk")
        except UnicodeDecodeError:
            return raw.decode("utf-8", "replace")


_TS_LINE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(\w+)\s?(.*)$")
_RECV_RE = re.compile(r"^\[([^\]]+)\]\s*收到:\s?(.*)$")
_REPLY_RE = re.compile(r"^\[([^\]]+)\]\s*回复:\s?(.*)$")
_APIERR_RE = re.compile(r"^\[([^\]]+)\]\s*Hermes API 调用失败:\s?(.*)$")
_OUTQ_RE = re.compile(r"^\[外发\]\s*入队\s*→\s*([^:]+):\s?(.*)$")
_OUTS_RE = re.compile(r"^\[外发\]\s*已发出\s*→\s*([^:]+):\s?(.*)$")

# traceback / logging error 噪音块的起始行（这类后续行不属于上一条消息正文）
_NOISE_START_RE = re.compile(
    r"^(--- Logging error ---|Traceback \(most recent call last\):|Call stack:)")


def _ts_to_epoch(s):
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return None


def _iso_to_epoch(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


_WINDOW_RE = re.compile(r"\[(?P<uid>[^\]]+)\]\s*(?P<state>已连接|没找到独立聊天窗口)")


def load_wxbot_contacts():
    """wxbot 绑定的联系人：[{name, uid, profile, label}]。

    为什么不能只看日志：日志里只有"已经说过话"的人 —— 新加的联系人在开口前不出现，
    看板就少人（2026-10-10 加 刘璇/z 时实测）。config.toml 的 [[contacts]] 才是绑定关系的
    唯一事实来源；没有 [[contacts]] 时退回 [bot].bound_users。
    """
    out, cfg = [], {}
    try:
        import tomllib
        with open(wxbot_config_path(), "rb") as fh:
            cfg = tomllib.load(fh)
    except Exception:
        cfg = {}
    for c in (cfg.get("contacts") or []):
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        out.append({"name": name, "uid": str(c.get("uid") or name).strip(),
                    "profile": str(c.get("profile") or "default").strip(),
                    "label": str(c.get("label") or "").strip()})
    if not out:
        for n in (cfg.get("bot", {}).get("bound_users") or []):
            n = str(n).strip()
            if n:
                out.append({"name": n, "uid": n, "profile": "default", "label": ""})
    return out


def load_wxbot_profile_map():
    """Profile → 联系人窗口标题（投递映射，用于给定时任务标归属）。"""
    try:
        import json as _json
        return _json.loads(open(WXBOT_CHANNEL, encoding="utf-8").read()).get("profile_to_contact") or {}
    except Exception:
        return {}


# ---------------------------------------------------------------- 用户分组（订阅字典）

# 与 butler/groups.py 保持同步（看板是独立进程，不 import butler 包，只认同一份文件）
GROUP_MESSAGE_TYPES = {1: "新闻消息", 2: "问候消息", 3: "其他"}


def _as_pos_int(v):
    """1 / "1" / 1.0 → int；bool 与非法值 → None。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        n = v
    elif isinstance(v, float):
        n = int(v) if v.is_integer() else 0
    else:
        try:
            n = int(str(v).strip())
        except (TypeError, ValueError):
            return None
    return n if n > 0 else None


def group_file_path(home):
    """分组字典文件：env BUTLER_GROUP_FILE 优先，默认 {HERMES_HOME}/cache/butler_groups.json
    （与 butler 侧 Config.group_file_path 的默认一致）。"""
    return os.environ.get("BUTLER_GROUP_FILE") or _LOG_SETTINGS['sources']['groups_file'] or os.path.join(home, "cache", "butler_groups.json")


def load_groups_file(path):
    """读分组字典 → (groups {type(str): [user]}, updated_at)。文件缺失/坏掉 → ({}, "")。"""
    groups, updated = {}, ""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        return groups, updated
    if not isinstance(raw, dict):
        return groups, updated
    updated = str(raw.get("updated_at") or "")
    g = raw.get("groups")
    if not isinstance(g, dict):
        g = raw                        # 兼容裸 {type: [users]} 的写法
    for k, v in g.items():
        n = _as_pos_int(k)
        if n is None or not isinstance(v, list):
            continue
        users, seen = [], set()
        for u in v:
            s = str(u or "").strip()
            if s and s not in seen:
                seen.add(s)
                users.append(s)
        if users:
            groups[str(n)] = users
    return groups, updated


def save_groups_file(path, groups):
    """原子写（tmp + replace）：与 butler 侧 GroupStore._save 同一格式。"""
    payload = {"version": 1, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "groups": groups}
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def build_groups_payload(home):
    """「用户分组」页数据：字典 + 可绑定的联系人（config.wxbot.toml 的绑定关系）。

    1/2/3 三个已知类型总在列表里（哪怕空），文件里多出来的未知类型原样带上。
    """
    path = group_file_path(home)
    groups, updated = load_groups_file(path)
    contacts = load_wxbot_contacts()
    known = {c["name"]: c for c in contacts}

    def member(u):
        c = known.get(u) or {}
        return {"name": u, "label": c.get("label") or "",
                "profile": c.get("profile") or "", "known": bool(c)}

    keys = [str(t) for t in sorted(GROUP_MESSAGE_TYPES)]
    keys += sorted(k for k in groups if k not in keys)
    types = []
    for k in keys:
        n = _as_pos_int(k)
        if n is None:
            continue
        users = list(groups.get(k) or [])
        types.append({"type": n, "label": GROUP_MESSAGE_TYPES.get(n, f"类型{n}"),
                      "users": users, "count": len(users),
                      "members": [member(u) for u in users]})
    return {
        "ok": True, "file": path, "exists": os.path.exists(path),
        "updated_at": updated, "message_types": types,
        "news": news_config.payload(path),
        "contacts": [{"name": c["name"], "label": c.get("label") or "",
                      "profile": c.get("profile") or ""} for c in contacts],
    }


def parse_wxbot_log(home):
    """
    解析 wxbot 主循环日志（只读），返回 (事件列表, 日志路径)。
    - 逐行 utf-8 → gbk 解码
    - 无时间戳前缀的后续行紧接上一条事件的正文（多行消息不丢）
    - traceback / logging error 块整体跳过（不污染正文）
    """
    path = os.path.join(home, "cache", "wxbot.log")
    events = []
    if not os.path.exists(path):
        return events, path
    with open(path, "rb") as fh:
        raw = fh.read()
    cur = None        # 当前正在累积正文的事件
    noisy = False     # 处于噪音块中
    for rawline in raw.split(b"\n"):
        line = _decode_line(rawline.rstrip(b"\r"))
        m = _TS_LINE_RE.match(line)
        if m:
            noisy = False
            ts_s, level, body = m.group(1), m.group(2), (m.group(3) or "")
            ev = {
                "ts": _ts_to_epoch(ts_s), "time": ts_s, "level": level,
                "direction": "system", "uid": "", "content": "", "phase": "",
            }
            mm = _RECV_RE.match(body)
            if mm:
                ev.update(direction="received", uid=mm.group(1), content=mm.group(2))
            else:
                mm = _REPLY_RE.match(body)
                if mm:
                    ev.update(direction="reply", uid=mm.group(1), content=mm.group(2))
                else:
                    mm = _APIERR_RE.match(body)
                    if mm:
                        ev.update(direction="api_error", uid=mm.group(1), content=mm.group(2))
                    else:
                        mm = _OUTQ_RE.match(body)
                        if mm:
                            ev.update(direction="outbound", phase="queued",
                                      uid=mm.group(1), content=mm.group(2))
                        else:
                            mm = _OUTS_RE.match(body)
                            if mm:
                                ev.update(direction="outbound", phase="sent",
                                          uid=mm.group(1), content=mm.group(2))
            if ev["direction"] == "system":
                mw = _WINDOW_RE.match(body)
                if mw:
                    ev.update(direction="window",
                              phase=("connected" if mw.group("state") == "已连接" else "missing"),
                              uid=mw.group("uid"), content=mw.group("state"))
            events.append(ev)
            cur = ev if ev["direction"] in ("received", "reply", "outbound") else None
            continue
        # —— 非时间戳行 ——
        if _NOISE_START_RE.match(line):
            noisy = True
            cur = None
            continue
        if noisy:
            continue
        if cur is not None and line.strip() != "":
            cur["content"] += ("\n" + line if cur["content"] else line)
        elif cur is not None and cur["content"]:
            cur["content"] += "\n"        # 保留正文中间的空白行
    for ev in events:
        if ev["content"]:
            ev["content"] = ev["content"].rstrip("\n").rstrip()
    return events, path


def merge_outbound(events):
    """把 [外发] 入队 + 已发出 合成一条记录（以入队时间为主，附 sent_ts）。"""
    merged = []
    for ev in events:
        if ev["direction"] == "outbound" and ev.get("phase") == "sent":
            tgt = None
            for prev in reversed(merged):
                if (prev["direction"] == "outbound" and prev.get("phase") == "queued"
                        and prev["uid"] == ev["uid"] and prev["content"] == ev["content"]
                        and not prev.get("sent_ts")):
                    tgt = prev
                    break
            if tgt is not None:
                tgt["sent_ts"] = ev["ts"]
                tgt["sent_time"] = ev["time"]
                continue
        merged.append(ev)
    return merged


def load_wxbot_sessions(home):
    """读 wxbot-* profile 的 state.db（只读 URI），给出每个会话的耗时/工具数。"""
    out = []
    pdir = os.path.join(home, "profiles")
    if not os.path.isdir(pdir):
        return out
    for prof in sorted(os.listdir(pdir)):
        if not prof.startswith("wxbot-"):
            continue
        db = os.path.join(pdir, prof, "state.db")
        if not os.path.exists(db):
            continue
        conn = connect(db)          # connect() 已用 mode=ro
        try:
            for r in safe_query(conn,
                    "SELECT id, started_at, message_count, tool_call_count, api_call_count "
                    "FROM sessions ORDER BY started_at"):
                span = safe_query(conn,
                    "SELECT MIN(timestamp) AS a, MAX(timestamp) AS b "
                    "FROM messages WHERE session_id = ?", (r["id"],))
                a = span[0]["a"] if span and span[0]["a"] is not None else None
                b = span[0]["b"] if span and span[0]["b"] is not None else None
                out.append({
                    "profile": prof,
                    "session_id": r["id"],
                    "started_at": r["started_at"],
                    "first_msg_at": a,
                    "last_msg_at": b,
                    "duration_s": round(b - a, 1) if (a is not None and b is not None) else None,
                    "message_count": r["message_count"],
                    "tool_call_count": r["tool_call_count"],
                    "api_call_count": r["api_call_count"],
                })
        finally:
            conn.close()
    return out


def load_job_names(home):
    """
    job_id -> 任务名。
    来源一：各 cron/jobs.json（现役任务）
    来源二：cron/output/<job_id>/*.md 标题「# Cron Job: xxx」（含已跑完/已删除的一次性提醒）
    """
    idx = {}
    targets = [os.path.join(home, "cron", "jobs.json")]
    pdir = os.path.join(home, "profiles")
    if os.path.isdir(pdir):
        for p in sorted(os.listdir(pdir)):
            f = os.path.join(pdir, p, "cron", "jobs.json")
            if os.path.exists(f):
                targets.append(f)
    for path in targets:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
        except Exception:
            continue
        jobs = data if isinstance(data, list) else (data.get("jobs") or [])
        for j in jobs:
            if isinstance(j, dict) and j.get("id"):
                idx.setdefault(j["id"], j.get("name") or "(未命名)")

    outdirs = [os.path.join(home, "cron", "output")]
    if os.path.isdir(pdir):
        for p in sorted(os.listdir(pdir)):
            outdirs.append(os.path.join(pdir, p, "cron", "output"))
    head_re = re.compile(r"^#\s*Cron Job:\s*(.+?)\s*$")
    for od in outdirs:
        if not os.path.isdir(od):
            continue
        for jid in sorted(os.listdir(od)):
            if jid in idx:
                continue
            jd = os.path.join(od, jid)
            if not os.path.isdir(jd):
                continue
            for fn in sorted(os.listdir(jd)):
                if not fn.endswith(".md"):
                    continue
                try:
                    with open(os.path.join(jd, fn), "r",
                              encoding="utf-8", errors="replace") as fh:
                        for _ in range(5):
                            ln = fh.readline()
                            if not ln:
                                break
                            mm = head_re.match(ln.strip())
                            if mm:
                                idx[jid] = mm.group(1)
                                break
                except Exception:
                    pass
                if jid in idx:
                    break
    return idx


def load_executions(home):
    """所有 executions.db 的执行记录 -> [{job_id, status, started, finished}]（epoch）。"""
    out = []
    dbs = [os.path.join(home, "cron", "executions.db")]
    pdir = os.path.join(home, "profiles")
    if os.path.isdir(pdir):
        for p in sorted(os.listdir(pdir)):
            f = os.path.join(pdir, p, "cron", "executions.db")
            if os.path.exists(f):
                dbs.append(f)
    for db in dbs:
        if not os.path.exists(db):
            continue
        conn = connect(db)
        try:
            for r in safe_query(conn,
                    "SELECT job_id, status, started_at, finished_at FROM executions"):
                out.append({
                    "job_id": r["job_id"],
                    "status": r["status"],
                    "started": _iso_to_epoch(r["started_at"]),
                    "finished": _iso_to_epoch(r["finished_at"]),
                })
        finally:
            conn.close()
    return out


def attribute_task(ts, execs, names, window=90):
    """
    一条外发事件 ts(±window 秒) 内若有某个 cron 执行记录 → 归属该任务（标「推断」）。
    没有 → 「管家 / 手动推送」。绝不把推断说成确定事实。
    """
    best = None
    for e in execs:
        st = e["started"]
        if st is None:
            continue
        fi = e["finished"] if e["finished"] is not None else st
        if (st - window) <= ts <= (fi + window):
            d = min(abs(ts - st), abs(ts - fi))
            if best is None or d < best[0]:
                best = (d, e)
    if best is None:
        return {"name": "管家 / 手动推送", "job_id": None,
                "attribution": "manual", "source": "manual", "status": None}
    e = best[1]
    return {"name": names.get(e["job_id"]) or ("job " + str(e["job_id"])),
            "job_id": e["job_id"], "attribution": "inferred",
            "source": "cron", "status": e["status"]}


def read_message_flow(home, *, contact='', limit=50, offset=0, order='desc'):
    view = ConfigView(wxbot_config_path(),butler_config_path(),home)
    view.read()
    try:
        return view.scrub(FlowView(**view.flow_options()).read(contact=contact,limit=limit,offset=offset,order=order))
    except Exception as exc:
        return {'read_only':True,'status':'error','flows':[],'contacts':[],
                'error':'无法读取流转配置（'+type(exc).__name__+'）'}


def collect_wxbot(home, directory, *, flow_contact='', flow_offset=0, flow_order='desc'):
    """组装 wxbot 通道流水（收到 / 回复 / 外发 + 这一轮 agent 耗时 + 任务归属）。"""
    raw_events, log_path = parse_wxbot_log(home)
    events = merge_outbound(raw_events)
    sessions = load_wxbot_sessions(home)
    names = load_job_names(home)
    execs = load_executions(home)

    def match_session(ts):
        """收到的时刻 ±15s 内的会话即那一轮。"""
        if ts is None:
            return None
        best = None
        for s in sessions:
            if s["started_at"] is None:
                continue
            d = abs(ts - s["started_at"])
            if d <= 15 and (best is None or d < best[0]):
                best = (d, s)
        return best[1] if best else None

    # 按 uid 把「收到」和它后面第一个「回复」串成一轮
    pend = {}
    for ev in events:
        if ev["direction"] == "received":
            pend[ev["uid"]] = ev
        elif ev["direction"] == "reply":
            r = pend.pop(ev["uid"], None)
            if r is not None:
                r["_reply"] = ev
                ev["_recv"] = r

    win = {}                      # 窗口标题 → 最新窗口状态
    for ev in events:
        if ev["direction"] == "window" and ev.get("uid"):
            win[ev["uid"]] = {"state": ev.get("phase"), "time": ev.get("time")}

    rows = []
    for ev in events:
        d = ev["direction"]
        if d == "window":
            continue
        row = {
            "time": ev["time"], "ts": ev["ts"], "level": ev["level"],
            "direction": d, "phase": ev.get("phase", ""),
            "uid": ev["uid"], "name": display_of(ev["uid"], directory) if ev["uid"] else "",
            "content": ev["content"], "status": "",
            "elapsed_s": None, "reply_wait_s": None, "elapsed_kind": None,
            "sent_time": ev.get("sent_time"), "sent_ts": ev.get("sent_ts"),
            "agent": None, "task": None,
        }
        if d in ("received", "reply"):
            recv = ev if d == "received" else ev.get("_recv")
            rep = ev.get("_reply") if d == "received" else ev
            if isinstance(recv, dict) and recv.get("time"):
                sess = match_session(recv["ts"])
                wait = (round(rep["ts"] - recv["ts"], 1)
                        if (isinstance(rep, dict) and rep.get("ts") and recv.get("ts")) else None)
                kind = None
                dur = sess["duration_s"] if sess else None
                if dur is not None:
                    row["elapsed_s"] = dur
                    # 会话是跨轮累积的。判据用"会话跨度 vs 本轮 收到→回复"的差，不依赖时钟：
                    # 差值 >30s ⇒ 这个数已经包含别的轮次，直接叫"调用 agent 耗时"会骗人
                    # （实测 z 12:16 那轮显示 171.3s，而该轮实际只用了 13.0s）。
                    kind = "session" if (wait is None or dur > wait + 30) else "turn"
                else:
                    row["elapsed_s"] = wait
                    kind = "turn" if wait is not None else None
                row["elapsed_kind"] = kind
                row["reply_wait_s"] = wait
                if sess:
                    row["agent"] = {
                        "session_id": sess["session_id"], "profile": sess["profile"],
                        "api_call_count": sess["api_call_count"],
                        "tool_call_count": sess["tool_call_count"],
                        "message_count": sess["message_count"],
                        "duration_s": sess["duration_s"],
                    }
                # 这一轮的状态：窗口内有没有 Hermes API 调用失败
                lo = recv["ts"] or 0
                hi = rep["ts"] if (isinstance(rep, dict) and rep.get("ts")) else lo + 3600
                st = "ok"
                for e2 in events:
                    if e2["direction"] != "api_error" or not e2.get("ts"):
                        continue
                    if lo <= e2["ts"] <= hi:
                        txt = (e2["content"] or "").lower()
                        if "timed out" in txt or "timeout" in txt:
                            st = "timeout"
                        elif st == "ok":
                            st = "error"
                row["status"] = st
        elif d == "outbound":
            row["task"] = attribute_task(ev["ts"], execs, names) if ev["ts"] else None
        rows.append(row)

    rows.sort(key=lambda x: x["ts"] or 0, reverse=True)      # 倒序（新→旧）默认

    # 联系人汇总
    contacts = {}
    for bc in load_wxbot_contacts():       # 先按绑定关系铺满（新用户开口前也列出）
        w = win.get(bc["name"]) or {}
        contacts[bc["name"]] = {"uid": bc["name"], "name": display_of_ci(bc["name"], directory) or bc["label"] or bc["name"],
                                "user_id": bc["uid"], "profile": bc["profile"],
                                "count": 0, "out": 0, "slow": 0,
                                "window": w.get("state") or "", "window_time": w.get("time") or ""}
    for r in rows:
        if r["direction"] not in ("received", "reply", "outbound") or not r["uid"]:
            continue
        c = contacts.setdefault(r["uid"], {"uid": r["uid"], "name": r["name"],
                                           "user_id": "", "profile": "",
                                           "count": 0, "out": 0, "slow": 0,
                                           "window": "", "window_time": ""})
        c["count"] += 1
        if r["direction"] == "outbound":
            c["out"] += 1
        if r["elapsed_s"] and r["elapsed_s"] > 300:
            c["slow"] += 1
    contacts = sorted(contacts.values(), key=lambda x: (-x["count"], x["name"]))

    slow = [r for r in rows if r["elapsed_s"] and r["elapsed_s"] > 300]
    stats = {
        "events": len(rows),
        "received": sum(1 for r in rows if r["direction"] == "received"),
        "reply": sum(1 for r in rows if r["direction"] == "reply"),
        "outbound": sum(1 for r in rows if r["direction"] == "outbound"),
        "api_error": sum(1 for r in rows if r["direction"] == "api_error"),
        "system": sum(1 for r in rows if r["direction"] == "system"),
        "contacts": len(contacts),
        "slow_rounds": len(slow),
        "timeouts": sum(1 for r in rows if r["status"] == "timeout"),
        "inferred_tasks": sum(1 for r in rows if r.get("task")
                              and r["task"].get("attribution") == "inferred"),
        "sessions": len(sessions),
        "execs": len(execs),
        "jobs_known": len(names),
    }
    flow = read_message_flow(home,contact=flow_contact,offset=flow_offset,order=flow_order)
    known = {c['uid']:c for c in contacts}
    for item in flow.get('contacts',[]):
        uid = item['contact']
        if uid not in known:
            c = {'uid':uid,'name':display_of_ci(uid,directory) or uid,'user_id':'','profile':'',
                 'count':0,'out':0,'slow':0,'window':'','window_time':''}
            contacts.append(c)
            known[uid] = c
        known[uid]['flow_reason'] = item['reason']['code']
    for c in contacts:
        c['flow_count'] = sum(f['contact']==c['uid'] for f in flow.get('flows',[]))
    return {
        "ok": True,
        "log": log_path,
        "log_exists": os.path.exists(log_path),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "window_s": 90,
        "stats": stats,
        "contacts": contacts,
        "events": rows,
        "flow": flow,
    }


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "WeChatInbox/1.0"
    home = HERMES_HOME

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str))

    def _body(self):
        """读 JSON 请求体（POST 用）；读不出就回空 dict（校验层再拒）。"""
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > (1 << 20):
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8", "replace"))
        except Exception:
            return {}

    def _confirmed_origin(self,header):
        host=self.headers.get('Host','').lower()
        try:
            target=urlparse('//'+host)
            local={'localhost','127.0.0.1','::1',self.connection.getsockname()[0].lower()}
            port=target.port if target.port is not None else 80
            origin=self.headers.get('Origin')
            valid_origin=(not origin or (urlparse(origin).scheme in {'http','https'} and urlparse(origin).netloc.lower()==host))
            return (target.hostname in local and port==self.server.server_port and valid_origin and
                    self.headers.get(header)=='1' and self.headers.get('Content-Type','').split(';')[0].strip().lower()=='application/json')
        except ValueError:return False

    def _config_view(self):
        return ConfigView(wxbot_config_path(),butler_config_path(),self.home,
            groups_override=group_file_path(self.home),log_config_path=log_config_path(),
            log_runtime={'host':self.server.server_address[0],'port':self.server.server_address[1],
                         'overrides':{k:os.environ[k] for k in ('HERMES_HOME','WXBOT_CONFIG','BUTLER_CONFIG','BUTLER_GROUP_FILE') if os.environ.get(k)}})

    def _relay_admin(self):
        from butler.config import load as load_butler
        cfg = load_butler(butler_config_path())
        return TelegramRelayAdmin(cfg.resolve_path('config.telegram-relay.toml'),
                                  cfg.data_path()/'telegram-relay'/'desktop-status.json')

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        p = u.path.rstrip("/") or "/"

        def one(k, d=""):
            v = qs.get(k)
            return v[0] if v else d

        def num(k, d):
            try:
                return int(one(k, str(d)))
            except Exception:
                return d

        def flag(k):
            return one(k, "") in ("1", "true", "yes", "on")

        try:
            if p == "/":
                with open(os.path.join(HERE, "index.html"), "r", encoding="utf-8") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
                return

            if p.startswith('/assets/'):
                name=p.removeprefix('/assets/')
                allowed={'dashboard.css','common.js','messages.js','jobs.js','groups.js',
                         'heartbeat.js','queue.js','configuration.js','runtime.js','workflow.js','workflow.css','users.js','telegram_relay.js','app.js'}
                if name not in allowed:
                    self._send(404,'Not found','text/plain; charset=utf-8')
                    return
                with open(os.path.join(HERE,'assets',name),encoding='utf-8') as fh:
                    self._send(200,fh.read(),('text/css' if name.endswith('.css') else 'text/javascript')+'; charset=utf-8')
                return

            if p == '/api/telegram-relay':
                try:
                    self._json(self._relay_admin().read())
                except (OSError, ValueError, RuntimeError):
                    self._json({'error': 'Telegram 转发配置暂不可读，请检查本机配置'}, 503)
                return
            if p in ('/api/users', '/api/users/memory', '/api/users/audit'):
                status, payload = request_user_admin(_load_butler_config(), '/v1' + p.removeprefix('/api') + ('?' + u.query if u.query else ''))
                self._json(payload, status)
                return
            if p == '/api/workflow-content':
                try:
                    from log.workflow_content import read_content
                    view = self._config_view()
                    view.read()
                    detail = read_content(view.queue_options()['path'], view.root/'config.telegram-bot.toml', one('id'))
                    if detail is None:
                        self._json({'status':'missing','error':'消息已删除或记录不存在'},404)
                    else:
                        for field in ('text','reply_text'):
                            detail[field] = view.scrub_message_text(detail[field])
                        self._json({'status':'ok',**detail})
                except ValueError:
                    self._json({'status':'error','error':'消息标识或配置无效'},400)
                except (OSError,sqlite3.Error,KeyError,TypeError):
                    self._json({'status':'error','error':'消息全文暂时不可读取'},503)
                return
            if p == '/api/workflow':
                try:
                    view = self._config_view()
                    view.read()
                    config = _load_butler_config()
                    payload = WorkflowView(**view.flow_options(), contacts=config.get('contacts', []),
                                           backend=(config.get('agent') or {}).get('provider','hermes')).read()
                    telegram = TelegramView(view.root/'config.telegram-bot.toml', view.butler_path).workflow()
                    payload['sources'].append(telegram['source'])
                    payload['nodes'].append(dict(id=8,key='telegram',label='Telegram',description='机器人收件与新闻提交'))
                    payload['nodes'].append(dict(id=9,key='news',label='Butler · 新闻投递',description='按新闻分组逐人投递'))
                    payload['messages'].extend(telegram['messages'])
                    counts=telegram['counts']
                    payload['counts']['telegram']=sum(counts.values())
                    payload['counts']['active']=payload['counts'].get('active',0)+sum(v for k,v in counts.items() if k not in TELEGRAM_TERMINAL)
                    payload['counts']['issues']=payload['counts'].get('issues',0)+sum(v for k,v in counts.items() if k in TELEGRAM_ISSUES)
                    if payload['status']!='ok':
                        payload['sources'].append(dict(name='wxbot 队列',status=payload['status'],error=payload['error'],truncated=False))
                        if telegram['messages']:payload['status']='ok'
                    self._json(view.scrub(payload))
                except Exception as exc:
                    self._json({'status':'error','error':'工作流配置不可读取（'+type(exc).__name__+'）'},500)
                return
            if p == '/api/flow':
                self._json(read_message_flow(self.home,contact=one('contact'),limit=num('limit',50),offset=num('offset',0),order=one('order','desc')))
                return
            if p == '/api/runtime':
                config=_load_butler_config()
                payload=fetch_butler_data(config,'/v1/runtime')
                view=self._config_view();view.read()
                self._json(view.scrub(payload))
                return

            if p in ("/api/queue", "/api/configuration"):
                view = self._config_view()
                configuration = view.read()
                if p == '/api/configuration':
                    self._json(configuration)
                else:
                    try:
                        payload = QueueView(**view.queue_options()).read(
                            contact=one('contact'), state=one('state','all'),
                            limit=num('limit',50), offset=num('offset',0),scope=one('scope'),order=one('order'),
                            offsets={t:num(t+'_offset',num('offset',0)) for t in ('inbox','batches','outbox','rounds')})
                        payload['telegram']=TelegramView(view.root/'config.telegram-bot.toml',view.butler_path).read(
                            scope=one('scope','all'),state=one('state','all'),contact=one('contact'),
                            limit=num('limit',50),offset=num('telegram_offset',0))
                        self._json(view.scrub(payload))
                    except Exception as exc:
                        self._json({'read_only':True,'status':'error',
                                    'error':'无法读取队列配置（'+type(exc).__name__+'）'},500)
                return

            directory = load_directory(self.home)

            if p == "/api/health":
                self._json({"ok": True, "home": self.home,
                            "dbs": [{"profile": a, "path": b} for a, b in discover_dbs(self.home)]})
                return

            if p == "/api/jobs":
                config=_load_butler_config()
                if (config.get('agent') or {}).get('provider')=='codex':
                    from log.runtime_view import reminder_jobs
                    self._json(reminder_jobs(fetch_butler_data(config,'/v1/runtime')))
                    return
                uid_filter = one("uid", "all")
                flt = (uid_filter or "all").split("@")[0].lower()
                jobs = collect_jobs(self.home)
                # 原始大小写 uid 的来源：收到的消息 > deliver 里的写法 > Profile 名
                msg_users, _, _ = build_users(self.home, directory)
                orig = {u["uid"].lower(): u["uid"] for u in msg_users}
                for j in jobs:
                    k = j.get("uid_key") or ""
                    if k and k in orig:
                        j["uid"] = orig[k]
                by_uid = {}
                for j in jobs:
                    k = j.get("uid_key") or ""
                    if not k and j.get("scope") == "global":
                        k = "global"                # 全局任务单独一组（群发，收件人按字典）
                    if flt != "all" and k != flt:
                        continue
                    by_uid.setdefault(k or "(no-owner)", []).append(j)
                users_out = []
                for key, js in by_uid.items():
                    nm = ""
                    disp = ""
                    if key == "global":
                        nm = "全局任务"
                    elif key != "(no-owner)":
                        nm = display_of_ci(key, directory)
                        disp = orig.get(key) or next(
                            (x.get("uid") for x in js if x.get("uid")), key)
                        if not nm and disp:
                            nm = disp
                    for x in js:
                        x["ui_state"] = jobs_ui_state(x)
                    js.sort(key=lambda x: (x["ui_state"] != "active", _iso_to_epoch(x.get('next_run_at')) or float('inf'),x.get('job_id') or ''))
                    users_out.append({
                        "uid": "global" if key == "global" else ("" if key == "(no-owner)" else key),
                        "uid_display": "" if key in ("(no-owner)", "global") else (disp or key),
                        "name": nm or "系统 / 无归属",
                        "count": len(js),
                        "active": sum(1 for x in js if x["ui_state"] == "active"),
                        "paused": sum(1 for x in js if x["ui_state"] == "paused"),
                        "error": sum(1 for x in js if x["ui_state"] == "error"),
                        "jobs": js,
                    })
                _rank = {"global": 1, "": 2}    # 用户在前，全局次之，无归属最后
                users_out.sort(key=lambda u: (_rank.get(u["uid"], 0),
                                              -u["active"], -u["count"], u["name"]))
                self._json({
                    "count": len(jobs),
                    "active": sum(1 for j in jobs if jobs_ui_state(j) == "active"),
                    "paused": sum(1 for j in jobs if jobs_ui_state(j) == "paused"),
                    "error": sum(1 for j in jobs if jobs_ui_state(j) == "error"),
                    "done": sum(1 for j in jobs if jobs_ui_state(j) == "done"),
                    "users": users_out,
                })
                return

            if p == "/api/wxbot":
                self._json(collect_wxbot(self.home, directory,
                                        flow_contact=one('flow_contact'),flow_offset=num('flow_offset',0),flow_order=one('flow_order','desc')))
                return

            if p == "/api/groups":
                self._json(build_groups_payload(self.home))
                return

            if p == "/api/heartbeat-config":
                contacts, config = load_butler_contacts()
                path = heartbeat_config_path(self.home, config)
                with _HEARTBEAT_CONFIG_LOCK:
                    users = load_heartbeat_config(path)
                names = {item["name"] for item in contacts}
                policies = {name: users[name] for name in names if name in users}
                heartbeat = config.get("heartbeat") or {}
                interval_min = max(1, int(heartbeat.get("min_interval_minutes") or 180))
                interval_max = max(interval_min, int(heartbeat.get("max_interval_minutes") or 360))
                self._json({
                    "contacts": contacts,
                    "policies": policies,
                    "interval_minutes": {
                        "min": interval_min,
                        "max": interval_max,
                    },
                })
                return

            if p == "/api/heartbeat-status":
                contacts, config = load_butler_contacts()
                path = heartbeat_config_path(self.home, config)
                with _HEARTBEAT_CONFIG_LOCK:
                    users = load_heartbeat_config(path)
                status = load_heartbeat_status(self.home, config, max(1, min(100, num("limit", 30))))
                names = {item["name"] for item in contacts}
                status["enabled_contacts"] = sum(
                    1 for name, policy in users.items()
                    if name in names and policy.get("heartbeat_enabled") is True)
                self._json(status)
                return

            if p == "/api/skills":
                contact_name = one("contact")
                contacts, config = load_butler_contacts()
                contact = next((item for item in contacts if item["name"] == contact_name), None)
                if contact is None:
                    self._json({"error": "未知的 Butler 联系人"}, 400)
                    return
                self._json({"contact": contact["name"], "profile": contact["profile"],
                            "skills": fetch_hermes_skills(contact, config)})
                return

            self._json({"error": "not found", "path": p}, 404)
        except Exception as exc:
            self._json({"error": type(exc).__name__, "detail": str(exc)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        p = u.path.rstrip("/") or "/"
        try:
            if p == '/api/telegram-relay/resolve':
                if not self._confirmed_origin('X-Wxbot-Relay-Action'):
                    self._json({'error': '任务核对仅接受当前页面的确认请求'}, 403)
                    return
                try:
                    status, payload = request_relay_resolution(_load_butler_config(), self._body())
                    self._json(payload, status)
                except (OSError, ValueError, RuntimeError):
                    self._json({'error': 'Telegram 转发任务核对暂不可用'}, 503)
                return
            if p == '/api/telegram-relay':
                if not self._confirmed_origin('X-Wxbot-Relay-Action'):
                    self._json({'error': '转发设置仅接受当前页面的保存请求'}, 403)
                    return
                try:
                    self._json(self._relay_admin().update(self._body()))
                except SettingsConflict:
                    self._json({'error': '配置已被修改，草稿已保留；请刷新后重新编辑'}, 409)
                except ValueError as exc:
                    self._json({'error': str(exc)}, 400)
                except (OSError, RuntimeError):
                    self._json({'error': 'Telegram 转发设置保存失败，请检查本机配置'}, 503)
                return
            if p == '/api/users':
                if not self._confirmed_origin('X-Wxbot-User-Action'):
                    self._json({'error': '用户操作仅接受当前页面发出的确认请求'}, 403)
                    return
                status, payload = request_user_admin(_load_butler_config(), '/v1/users', self._body())
                self._json(payload, status)
                return
            if p == '/api/news-config':
                if not self._confirmed_origin('X-Wxbot-Config-Action'):
                    self._json({'ok': False, 'error': '新闻设置仅接受当前页面的保存请求'}, 403)
                    return
                body = self._body()
                path = group_file_path(self.home)
                try:
                    if not isinstance(body, dict):
                        raise ValueError('新闻设置格式无效')
                    with config_lock(news_config.settings_path(path)):
                        news_config.save_settings(path, body.get('settings'), body.get('version'))
                    self._json({'ok': True, 'news': news_config.payload(path)})
                except news_config.NewsConflict as exc:
                    self._json({'ok': False, 'error': str(exc)}, 409)
                except ValueError as exc:
                    self._json({'ok': False, 'error': str(exc)}, 400)
                except OSError as exc:
                    self._json({'ok': False, 'error': '新闻设置保存失败（' + type(exc).__name__ + '）'}, 503)
                return
            if p == '/api/configuration':
                if not self._confirmed_origin('X-Wxbot-Config-Action'):
                    self._json({'ok':False,'error':'配置修改只接受当前页面的确认请求'},403)
                    return
                view=self._config_view()
                try:
                    result=ConfigEditor(view,policy_validator=validate_policy_skills).save(self._body())
                    self._json(view.scrub(result))
                except ConfigConflict as exc:self._json({'ok':False,'error':view.scrub(str(exc))},409)
                except ValueError as exc:self._json({'ok':False,'error':view.scrub(str(exc))},400)
                except (OSError,RuntimeError) as exc:self._json({'ok':False,'error':'配置保存失败（'+type(exc).__name__+'）'},503)
                except Exception as exc:self._json({'ok':False,'error':'配置保存失败（'+type(exc).__name__+'）'},500)
                return
            if p == '/api/queue-delete-unsent':
                if not self._confirmed_origin('X-Wxbot-Queue-Action'):
                    self._json({'ok':False,'error':'队列删除仅接受当前页面发出的确认请求'},403)
                    return
                try:
                    view=self._config_view()
                    result=QueueActions(view.queue_options()['path']).delete_unsent(
                        self._body(),telegram_config=view.root/'config.telegram-bot.toml')
                    self._json(result)
                except ValueError as exc:
                    self._json({'ok':False,'error':str(exc)},409)
                except (OSError,sqlite3.Error) as exc:
                    self._json({'ok':False,'error':'队列删除失败（'+type(exc).__name__+'）'},503)
                return
            if p == '/api/queue-action':
                if not self._confirmed_origin('X-Wxbot-Queue-Action'):
                    self._json({'ok':False,'error':'队列操作仅接受当前页面发出的确认请求'},403)
                    return
                try:
                    view=ConfigView(wxbot_config_path(),butler_config_path(),self.home)
                    result=QueueActions(view.queue_options()['path']).perform(self._body())
                    self._json(result)
                except ValueError as exc:
                    self._json({'ok':False,'error':str(exc)},409)
                except (OSError,sqlite3.Error) as exc:
                    self._json({'ok':False,'error':'队列操作失败（'+type(exc).__name__+'）'},503)
                return
            if p == "/api/heartbeat-trigger":
                body = self._body()
                contact_name = str(body.get("contact") or "").strip()
                contacts, config = load_butler_contacts()
                if not any(item["name"] == contact_name for item in contacts):
                    self._json({"ok": False, "error": "未知的 Butler 联系人"}, 400)
                    return
                status, result = trigger_butler_heartbeat(contact_name, config)
                if status >= 400:
                    self._json({"ok": False, "code": result.get("code"),
                                "error": result.get("error") or f"Butler 返回 HTTP {status}"}, status)
                    return
                self._json({"ok": True, "status": "started", "contact": contact_name}, 202)
                return
            if p == "/api/groups":       # 用户分组：绑定/解绑（只写字典文件）
                b = self._body()
                mt = _as_pos_int(b.get("type"))
                action = str(b.get("action") or "").strip()
                user = str(b.get("user") or "").strip()
                if mt is None:
                    self._json({"ok": False,
                                "error": "type 非法（须为正整数：1=新闻消息 2=问候消息 3=其他）"}, 400)
                    return
                if action not in ("bind", "unbind"):
                    self._json({"ok": False, "error": "action 只支持 bind / unbind"}, 400)
                    return
                if not user or len(user) > 64:
                    self._json({"ok": False,
                                "error": "user 为空或过长（微信窗口标题，≤64 字符）"}, 400)
                    return
                path = group_file_path(self.home)
                with config_lock(path):
                    groups, _ = load_groups_file(path)
                    users = list(groups.get(str(mt), []))
                    if action == "bind":
                        if user not in users:users.append(user)
                    else:users = [x for x in users if x != user]
                    groups[str(mt)] = users
                    save_groups_file(path, groups)
                self._json(build_groups_payload(self.home))
                return
            if p == "/api/heartbeat-config":
                b = self._body()
                contact_name = str(b.get("contact") or "").strip()
                contacts, config = load_butler_contacts()
                contact = next((item for item in contacts if item["name"] == contact_name), None)
                if contact is None:
                    self._json({"ok": False, "error": "未知的 Butler 联系人"}, 400)
                    return
                role = str(b.get("role_skill") or "").strip()
                allowed = b.get("allowed_skills")
                enabled = b.get("heartbeat_enabled")
                if not role or len(role) > 128:
                    self._json({"ok": False, "error": "必须选择有效的角色 skill"}, 400)
                    return
                if not isinstance(allowed, list) or any(not isinstance(x, str) for x in allowed):
                    self._json({"ok": False, "error": "allowed_skills 必须是字符串列表"}, 400)
                    return
                if not isinstance(enabled, bool):
                    self._json({"ok": False, "error": "heartbeat_enabled 必须是布尔值"}, 400)
                    return
                skills = fetch_hermes_skills(contact, config)
                skill_by_name = {item["name"]: item for item in skills}
                role_skill = skill_by_name.get(role)
                if role_skill is None or not is_butler_role_skill(role_skill):
                    self._json({"ok": False,
                                "error": "角色 skill 必须存在且带有 butler-role 标签"}, 400)
                    return
                role_names = {item["name"] for item in skills if is_butler_role_skill(item)}
                requested = {x.strip() for x in allowed if x.strip()}
                # Accept the role in an older browser draft, but never persist it as a tool.
                requested.discard(role)
                if requested & role_names:
                    self._json({"ok": False, "error": "角色 skill 不能放入允许调用的工具列表"}, 400)
                    return
                tool_names = set(skill_by_name) - role_names
                if not requested <= tool_names:
                    self._json({"ok": False, "error": "技能已不在 Hermes 可用目录中，请刷新后重试"}, 400)
                    return
                path = heartbeat_config_path(self.home, config)
                with _HEARTBEAT_CONFIG_LOCK,config_lock(path):
                    users = load_heartbeat_config(path)
                    valid_contacts = {item["name"] for item in contacts}
                    users = {name: value for name, value in users.items() if name in valid_contacts}
                    users[contact_name] = {
                        "role_skill": role,
                        "allowed_skills": sorted(requested),
                        "heartbeat_enabled": enabled,
                    }
                    save_heartbeat_config(path, users)
                self._json({"ok": True, "contact": contact_name, "policy": users[contact_name]})
                return
            self._json({"error": "not found", "path": p}, 404)
        except Exception as exc:
            self._json({"error": type(exc).__name__, "detail": str(exc)}, 500)


def main():
    ap = argparse.ArgumentParser(description="微信管家日志（wxbot 通道流水 + 定时任务 + 用户分组）")
    ap.add_argument("--host", default=_LOG_SETTINGS['server']['host'])
    ap.add_argument("--port", type=int, default=_LOG_SETTINGS['server']['port'])
    ap.add_argument("--home", default=HERMES_HOME)
    ap.add_argument("--open",action='store_true',help='启动后打开浏览器')
    args = ap.parse_args()

    Handler.home = args.home
    print(f"[wechat-inbox] HERMES_HOME = {args.home}")
    for pr, path in discover_dbs(args.home):
        print(f"  - {pr:<42} {path}")
    print(f"[wechat-inbox] 页面: http://{args.host}:{args.port}/   (Ctrl+C 退出)")
    try:
        server=ThreadingHTTPServer((args.host,args.port),Handler)
        if args.open:
            import webbrowser
            host='127.0.0.1' if args.host=='0.0.0.0' else args.host
            webbrowser.open(f'http://{host}:{server.server_port}/')
        try:server.serve_forever()
        finally:server.server_close()
    except KeyboardInterrupt:
        print("\n[wechat-inbox] 已停止")


if __name__ == "__main__":
    main()
