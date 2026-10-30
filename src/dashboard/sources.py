#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读数据源：Hermes 状态库、联系人口径、定时任务、收发消息统计。

一律 `mode=ro` 打开 SQLite，不建表、不迁移、不加运行锁。原样搬自 server.py。
"""
import hashlib
import json
import os
import re
import sqlite3
import time

from dashboard.api.support import WXBOT_CHANNEL


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


def load_wxbot_profile_map():
    """Profile → 联系人窗口标题（投递映射，用于给定时任务标归属）。"""
    try:
        return json.loads(open(WXBOT_CHANNEL, encoding="utf-8").read()).get("profile_to_contact") or {}
    except Exception:
        return {}


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
