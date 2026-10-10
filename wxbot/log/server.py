#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信收件日志 — 只读

只做一件事：把微信机器人（wechat-butler）**收到的消息**按发送人分组记下来。
不显示思考过程、工具调用、token、成本 —— 只看谁发了什么、什么时候发的。

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
    GET /api/jobs                定时任务（按人分组）
    GET /api/wxbot               wxbot 通道流水（收到/回复/外发 + agent 耗时 + 任务归属）
    """
import argparse
import datetime
import hashlib
import json
import os
import re
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

HERE = os.path.dirname(os.path.abspath(__file__))
HERMES_HOME = os.environ.get("HERMES_HOME", r"D:\ai\hermes")
EXPORT_DIR = os.path.join(HERMES_HOME, "logs", "wechat-inbox")
# wxbot 侧的绑定关系（联系人 ↔ Profile ↔ uid）唯一事实来源
WXBOT_CONFIG = os.environ.get("WXBOT_CONFIG", r"D:\ai\wxbot\config.toml")
WXBOT_CHANNEL = os.path.join(HERMES_HOME, "scripts", "wxbot_channel.json")


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


def collect_jobs(home):
    """读所有 Profile 的 cron/jobs.json，按发送人归属。"""
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
                "enabled": bool(j.get("enabled")),
                "state": j.get("state") or ("scheduled" if j.get("enabled") else "paused"),
                "script": j.get("script") or "",
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
        with open(WXBOT_CONFIG, "rb") as fh:
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


def collect_wxbot(home, directory):
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
    return {
        "ok": True,
        "log": log_path,
        "log_exists": os.path.exists(log_path),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "window_s": 90,
        "stats": stats,
        "contacts": contacts,
        "events": rows,
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

            directory = load_directory(self.home)

            if p == "/api/health":
                self._json({"ok": True, "home": self.home,
                            "dbs": [{"profile": a, "path": b} for a, b in discover_dbs(self.home)]})
                return

            if p == "/api/jobs":
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
                    if flt != "all" and k != flt:
                        continue
                    by_uid.setdefault(k or "(no-owner)", []).append(j)
                users_out = []
                for key, js in by_uid.items():
                    nm = ""
                    disp = ""
                    if key != "(no-owner)":
                        nm = display_of_ci(key, directory)
                        disp = orig.get(key) or next(
                            (x.get("uid") for x in js if x.get("uid")), key)
                        if not nm and disp:
                            nm = disp
                    for x in js:
                        x["ui_state"] = jobs_ui_state(x)
                    js.sort(key=lambda x: (x["ui_state"] != "active", x.get("name") or ""))
                    users_out.append({
                        "uid": "" if key == "(no-owner)" else key,
                        "uid_display": "" if key == "(no-owner)" else (disp or key),
                        "name": nm or "系统 / 无归属",
                        "count": len(js),
                        "active": sum(1 for x in js if x["ui_state"] == "active"),
                        "paused": sum(1 for x in js if x["ui_state"] == "paused"),
                        "error": sum(1 for x in js if x["ui_state"] == "error"),
                        "jobs": js,
                    })
                users_out.sort(key=lambda u: (u["uid"] == "(no-owner)",
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
                self._json(collect_wxbot(self.home, directory))
                return

            self._json({"error": "not found", "path": p}, 404)
        except Exception as exc:
            self._json({"error": type(exc).__name__, "detail": str(exc)}, 500)


def main():
    ap = argparse.ArgumentParser(description="微信管家日志（wxbot 通道流水 + 定时任务，只读）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--home", default=HERMES_HOME)
    args = ap.parse_args()

    Handler.home = args.home
    print(f"[wechat-inbox] HERMES_HOME = {args.home}")
    for pr, path in discover_dbs(args.home):
        print(f"  - {pr:<42} {path}")
    print(f"[wechat-inbox] 页面: http://{args.host}:{args.port}/   (Ctrl+C 退出)")
    try:
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n[wechat-inbox] 已停止")


if __name__ == "__main__":
    main()
