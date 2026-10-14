#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""习惯提醒：工作日按随机时间提醒「喝水」「活动颈椎腰椎」（wxbot 通道）。

为什么不是普通 cron 表达式：
  需求是「工作日 09:00-12:00 与 13:30-17:00 内，每隔 1~2 小时随机时间提醒」——
  cron 表达式表达不了"随机时刻"，也没法在窗口末尾自然收尾。
  所以这里做成一枚**有状态的调度器**：由 cron 每 2 分钟 tick 一次，脚本自己维护
  “下次该提醒的时刻”，到点就发；发完在区间内随机下一个时刻。状态落盘，重启不丢。

用法:
  butler_habit_nudge.py                     # 正常 tick（cron 用；无事发生则完全静默）
  butler_habit_nudge.py --status            # 看计划与上次发送
  butler_habit_nudge.py --simulate T ...    # 模拟时刻序列（只打印决策，不发送、不写状态）
  butler_habit_nudge.py --dry-run           # 按当前时刻 tick，但只打印、不发送
  butler_habit_nudge.py --fire water|neck   # 立刻发一条（手动测试，会真发出去）

规则（CONFIG 可改，改完即生效，不用动 cron）：
  · 只在「工作日」（周一~周五）与窗口时段内提醒；窗口外不打扰（也顺带避开半夜）。
  · water 首次延迟 60~120 分钟，之后间隔 60~120 分钟（随机）。
  · neck  首次延迟 45 分钟，之后间隔 45 分钟。
  · 提醒时刻若超出当前窗口末尾 → 本窗口收尾，等下一个窗口重新规划。
  · 若脚本在窗口中途才启动（比如刚开机）：首个提醒 = 现在 + 一个随机间隔。
  · stdout 保持为空 —— no_agent cron 下 stdout 非空等于要把内容投递出去。
"""
import argparse
import json
import random
import subprocess
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

HERMES = Path(r"D:/ai/hermes")
DELIVER = Path(__file__).resolve().parent / "wxbot_deliver.py"      # 与本脚本同目录（自定位）

CONFIG = {
    "profile": "wxbot-101",          # 经哪个 Hermes Profile 投递（决定发到哪个微信窗口）
    "uid": "101",                    # 档案键（读称呼用）
    "name": "",                      # 留空 = 从 butler_profiles/{uid}_user.json 读称呼
    "weekdays": [0, 1, 2, 3, 4],     # 0=周一
    "windows": [("09:00", "12:00"), ("13:30", "17:00")],
    "habits": {
        "water": {
            "label": "喝水",
            "first_delay_min": (60, 120),
            "interval_min": (60, 120),
            "text": "💧 {name}该喝水啦～ 站起来走两步，顺手给杯子续点水",
        },
        "neck": {
            "label": "活动颈椎腰椎",
            "first_delay_min": (45, 45),
            "interval_min": (45, 45),
            "text": "🧘 {name}起来活动下颈椎和腰椎～ 抬抬头、转转肩，别一直钉在椅子上",
        },
    },
    "state_keep": 60,                # 状态里保留多少条发送记录
}


def state_path():
    return HERMES / "profiles" / CONFIG["profile"] / "habit_nudges.json"


def log_path():
    return HERMES / "profiles" / CONFIG["profile"] / "logs" / "butler_habit.log"


def log(msg):
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (datetime.now().isoformat(timespec="seconds"), msg))
    except Exception:
        pass


def display_name():
    """称呼：优先 CONFIG['name']，其次该用户档案（{uid}_user.json 的 name / {uid}.json 第 0 题）。"""
    if CONFIG.get("name"):
        return CONFIG["name"]
    d = HERMES / "profiles" / CONFIG["profile"] / "butler_profiles"
    for fn, key in ((f"{CONFIG['uid']}_user.json", "name"), (f"{CONFIG['uid']}.json", None)):
        try:
            obj = json.loads((d / fn).read_text(encoding="utf-8"))
            if key:
                v = (obj.get(key) or "").strip()
                if v:
                    return v
            else:
                v = ((obj.get("answers") or {}).get("0") or "").strip()
                if v:
                    return v
        except Exception:
            continue
    return ""


def load():
    try:
        st = json.loads(state_path().read_text(encoding="utf-8"))
    except Exception:
        st = {}
    st.setdefault("next", {})
    st.setdefault("last", {})
    st.setdefault("sent", [])
    # 落盘后 next 是 ISO 字符串，读回来必须还原成 datetime，否则 now >= nxt 会 TypeError
    for k, v in list((st.get("next") or {}).items()):
        if isinstance(v, str):
            try:
                st["next"][k] = datetime.fromisoformat(v)
            except ValueError:
                st["next"][k] = None
    return st


def save(st):
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # datetime 不能直接 JSON 序列化 → next 里的时刻统一落盘成 ISO 字符串
    out = dict(st)
    out["next"] = {k: (v.isoformat(timespec="seconds") if isinstance(v, datetime) else v)
                   for k, v in (st.get("next") or {}).items()}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def hm2min(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def window_of(now):
    """返回 (窗口起点 datetime, 窗口终点 datetime)；不在窗口内返回 None。"""
    if now.weekday() not in CONFIG["weekdays"]:
        return None
    cur = now.hour * 60 + now.minute
    for a, b in CONFIG["windows"]:
        if hm2min(a) <= cur < hm2min(b):
            s = now.replace(hour=hm2min(a) // 60, minute=hm2min(a) % 60, second=0, microsecond=0)
            e = now.replace(hour=hm2min(b) // 60, minute=hm2min(b) % 60, second=0, microsecond=0)
            return s, e
    return None


def next_window_start(now):
    for i in range(0, 8):
        day = now + timedelta(days=i)
        if day.weekday() not in CONFIG["weekdays"]:
            continue
        for a, _b in CONFIG["windows"]:
            s = day.replace(hour=hm2min(a) // 60, minute=hm2min(a) % 60, second=0, microsecond=0)
            if s > now:
                return s
    return None


def rand_range(rng):
    lo, hi = rng
    return random.randint(lo, hi) if hi > lo else lo


def plan_first(kind, now, win_start, win_end):
    """首个提醒时刻：窗口起点 + 随机首延迟；若已过点（窗口中途才启动）→ 现在 + 随机间隔。"""
    cfg = CONFIG["habits"][kind]
    cand = win_start + timedelta(minutes=rand_range(cfg["first_delay_min"]))
    if cand <= now:
        cand = now + timedelta(minutes=rand_range(cfg["interval_min"]))
    return cand if cand < win_end else None


def send(text, dry=False):
    """经 wxbot 投递（不可用时由 wxbot_deliver 转入补发队列，不丢）。返回 (ok, note)。"""
    if dry:
        return True, "dry-run 未发送"
    try:
        r = subprocess.run([sys.executable, str(DELIVER), "--profile", CONFIG["profile"],
                            "--job-id", "habit-nudge", "--job-name", "习惯提醒", "--text", text],
                           capture_output=True, text=True, timeout=180)
        tail = (r.stdout or "").strip() or (r.stderr or "").strip()
        return (r.returncode == 0), "rc=%s %s" % (r.returncode, tail[:120])
    except Exception as e:
        return False, "EXC %s" % e


def tick(now, dry=False, force=None, state=None, verbose=False):
    """跑一次调度。返回本轮发出的 [(kind, text, note)]。"""
    st = state if state is not None else load()
    win = window_of(now)
    fired = []
    name = display_name()
    for kind, cfg in CONFIG["habits"].items():
        nxt = st["next"].get(kind)
        if force == kind:
            nxt = now
        if win is None:
            # 窗口外：清掉计划，等下一个窗口重新规划（也顺手避免跨窗口追发）
            st["next"][kind] = None
            continue
        ws, we = win
        if nxt is None:
            nxt = plan_first(kind, now, ws, we)
        if nxt is not None and now >= nxt:
            text = cfg["text"].format(name=((name + "，") if name else "")).strip()
            ok, note = send(text, dry=dry)
            fired.append((kind, text, note))
            log("%s %s -> %s (%s)" % (now.isoformat(timespec="seconds"), kind, "sent" if ok else "FAIL", note))
            st["last"][kind] = {"at": now.isoformat(timespec="seconds"), "text": text}
            st["sent"].append({"at": now.isoformat(timespec="seconds"), "kind": kind, "ok": ok})
            st["sent"] = st["sent"][-CONFIG["state_keep"]:]
            base = max(now, nxt)
            nxt = base + timedelta(minutes=rand_range(cfg["interval_min"]))
            if nxt >= we:
                nxt = None                      # 本窗口收尾
        st["next"][kind] = nxt
    st["last_tick"] = now.isoformat(timespec="seconds")   # 心跳留痕：--status 能看出它还活着
    if not dry and state is None:
        save(st)
    if verbose:
        for kind in CONFIG["habits"]:
            n = st["next"].get(kind)
            print("   %-6s next=%s" % (kind, n.strftime("%m-%d %H:%M") if isinstance(n, datetime) else "—"))
    return fired


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="打印计划，不发送")
    ap.add_argument("--dry-run", action="store_true", help="按当前时刻 tick，但不发送")
    ap.add_argument("--simulate", nargs="+", action="extend", default=[], metavar="TIME",
                    help="模拟时刻（可多次），如 '2026-10-12 09:05'，只打印不发送")
    ap.add_argument("--fire", choices=list(CONFIG["habits"]), help="立刻发一条（会真发）")
    a = ap.parse_args()

    if a.status:
        st = load()
        now = datetime.now()
        print("配置: profile=%s 窗口=%s 工作日=%s" % (CONFIG["profile"], CONFIG["windows"], CONFIG["weekdays"]))
        print("称呼: %r" % display_name())
        print("现在: %s (%s)" % (now.strftime("%Y-%m-%d %H:%M:%S"), "窗口内" if window_of(now) else "窗口外"))
        print("心跳: 上次 tick=%s" % (st.get("last_tick") or "—"))
        if st.get("last_error"):
            print("上次异常: %s" % st["last_error"])
        for kind, cfg in CONFIG["habits"].items():
            n = st["next"].get(kind)
            last = (st["last"].get(kind) or {}).get("at", "—")
            print("  %-6s 间隔%s分钟  下次=%s  上次=%s" % (
                kind, cfg["interval_min"], n or "—", last))
        return 0

    if a.simulate:
        random.seed(20261010)                 # 模拟用固定种子 → 结果可复现
        st = {"next": {}, "last": {}, "sent": []}
        for raw in a.simulate:
            t = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
                try:
                    t = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
            if t is None:
                print("!! 无法解析时刻: %r" % raw)
                continue
            res = tick(t, dry=True, state=st)
            tag = "窗口内" if window_of(t) else "窗口外"
            print("%s (%s %s) -> %s" % (t.strftime("%Y-%m-%d %H:%M"), "一二三四五六日"[t.weekday()], tag,
                                        "; ".join("发「%s」" % k for k, _x, _n in res) if res else "不发"))
            for k, _x, note in res:
                print("        └ %s" % note)
        return 0

    if a.fire:
        res = tick(datetime.now(), force=a.fire)
        log("manual fire %s -> %s" % (a.fire, res))
        return 0 if res else 1

    tick(datetime.now(), dry=a.dry_run, verbose=a.dry_run)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        tb = traceback.format_exc()
        log("EXC " + tb[:600].replace("\n", " | "))
        try:                                   # 异常也要留痕，否则 no_agent 下静默到没人知道
            st = load()
            st["last_error"] = "%s %s" % (datetime.now().isoformat(timespec="seconds"),
                                          (tb.strip().splitlines() or [""])[-1][:200])
            save(st)
        except Exception:
            pass
        sys.exit(0)                            # 绝不让异常变成 cron 的投递内容
