#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wxbot 流水日志解析、用户分组字典与消息流转聚合。

日志可能混有 UTF-8/GBK 行，逐行解码；分组文件与 butler 侧共用同一份 JSON。
原样搬自 server.py。
"""
import datetime
import json
import os
import re
import time
import tomllib

from common import news_config
from dashboard import services
from dashboard.api.support import (butler_config_path, unified_contact_store,
                                   wxbot_config_path)
from dashboard.config_view import ConfigView
from dashboard.flow_view import FlowView
from dashboard.sources import _as_pos_int, connect, display_of, display_of_ci, safe_query
from dashboard.settings import load_settings

_LOG_SETTINGS = load_settings()


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
    wxbot_config = services.get('wxbot_config_path', wxbot_config_path)
    try:
        import tomllib
        with open(wxbot_config(), "rb") as fh:
            cfg = tomllib.load(fh)
    except Exception:
        cfg = {}
    from butler.directory import DirectoryStore,directory_path,directory_enabled
    if directory_enabled(wxbot_config(),cfg):
        store=DirectoryStore(directory_path(wxbot_config(),cfg))
        cfg['contacts']=store.contact_rows()
        cfg.setdefault('bot',{}).update(store.channel_projection().get('bot',{}))
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


# ---------------------------------------------------------------- 用户分组（订阅字典）

# 与 src/butler/groups.py 保持同步（看板是独立进程，不 import butler 包，只认同一份文件）
GROUP_MESSAGE_TYPES = {1: "新闻消息", 2: "问候消息", 3: "其他"}


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
    store = unified_contact_store()
    groups, updated = (store.groups(), '') if store else load_groups_file(path)
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
        "ok": True, "file": str(store.path) if store else path, "exists": bool(store) or os.path.exists(path),
        "version": store.snapshot()['version'] if store else None,
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
