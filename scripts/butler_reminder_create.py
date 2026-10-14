#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性创建一条微信定时提醒（wxbot 通道）——**一条命令干完全部**。

为什么需要它（2026-10-10 实测教训）：
  管家按 skill 的旧流程建一条提醒要 14~25 次工具调用（读档案 → 读 skill → 读脚本 →
  写 4 个 wrapper → 建 4 个 cron job → 回写 reminders.json → 自检），每次工具调用都是
  一次模型往返（1.8~2.5s）→ 光"建个定时任务"就 30~60 秒；而自检那一步还把提醒提前发了出去。
  现在：一条命令写完 reminders.json + 8 个 wrapper（两个目录各 4 个）+ 4 个 no_agent cron job，
  管家只需 "调用本脚本 → 回一句确认" 两次往返。

用法：
    butler_reminder_create.py --uid 101 --content 喝水 --at +5m
    butler_reminder_create.py --uid 101 --content 抽烟 --at 2026-10-10T11:58:55
    butler_reminder_create.py ... --dry-run        # 只打印计划，什么都不写
    butler_reminder_create.py ... --json           # 机器可读输出（默认就是 JSON）

语义：
  * 主提醒在 --at 时刻发；3 次追问在 +2/+4/+6 分钟（未回复才发，回复即静默）。
  * 本脚本**只创建，不发送**。发送永远由 cron 到点触发 butler_reminder_push.py。
  * 幂等性：每次生成新 rid；wrapper 文件名带 rid，不会互相覆盖。
"""
import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(r"D:/ai/hermes")
PUSH = Path(__file__).resolve().parent / "butler_reminder_push.py"   # 与本脚本同目录（项目 scripts/，自定位）
STAGES = ("main", "chase1", "chase2", "chase3")
CHASE_OFFSET_MIN = {"main": 0, "chase1": 2, "chase2": 4, "chase3": 6}
LABEL = {"main": "main", "chase1": "chase1", "chase2": "chase2", "chase3": "chase3"}

WRAPPER_TMPL = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动生成：提醒 {rid} 的 {stage} 阶段（由 butler_reminder_create.py 生成，请勿手改）。

cron 的 script 参数只能填文件名、不能带参数，所以用 wrapper 预设 argv。
"""
import runpy
import sys

sys.argv = [r"{push}", "{stage}", "{rid}", "{profile}"] + sys.argv[1:]
#   末尾 + sys.argv[1:]：把调用方多给的参数转发进去 —— 有人拿 wrapper 自检（多带参数）时，
#   push 脚本会把"多出来的参数"判成误用 → 只演练、不发送（2026-10-10 实测教训）。
runpy.run_path(r"{push}", run_name="__main__")
'''


def parse_at(raw: str, now: datetime) -> datetime:
    s = (raw or "").strip()
    m = re.fullmatch(r"\+?(\d+)\s*([smhd])", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return now + timedelta(**{ {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[unit]: n })
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise SystemExit(f"无法解析 --at: {raw!r}（用 +5m / +90s / +2h 或 2026-10-10T11:58:55）")


def read_model(cfg_path: Path):
    """从 Profile 的 config.yaml 取当前模型/provider，用来固定 cron job（不固定会在模型漂移时被跳过）。"""
    try:
        txt = cfg_path.read_text(encoding="utf-8")
    except Exception:
        return None, None
    try:
        import yaml  # 有就用，最稳
        cfg = yaml.safe_load(txt) or {}
        m = cfg.get("model") or {}
        return m.get("default"), m.get("provider")
    except Exception:
        # 没 yaml 就退化成逐行找 model: 块里的 default/provider
        model = provider = None
        in_model = False
        for line in txt.splitlines():
            if re.match(r"^model:\s*$", line):
                in_model = True
                continue
            if in_model and re.match(r"^\S", line):
                in_model = False
                continue
            if in_model:
                m1 = re.match(r"\s+default:\s*(\S+)", line)
                if m1:
                    model = m1.group(1).strip("\"'")
                m2 = re.match(r"\s+provider:\s*(\S+)", line)
                if m2:
                    provider = m2.group(1).strip("\"'")
        return model, provider


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", required=True, help="用户 uid（wxbot 通道就是窗口标题，如 101）")
    ap.add_argument("--content", required=True, help="提醒内容，如 喝水 / 抽烟 / 开会")
    ap.add_argument("--at", required=True, help="主提醒时间：+5m / +90s / 2026-10-10T11:58:55")
    ap.add_argument("--profile", default="wxbot-101")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写任何文件")
    ap.add_argument("--force", action="store_true", help="跳过重复提醒检查")
    args = ap.parse_args()

    now = datetime.now()
    base = parse_at(args.at, now)
    phome = ROOT / "profiles" / args.profile
    if not phome.is_dir():
        raise SystemExit(f"Profile 目录不存在: {phome}")
    scripts_dirs = [phome / "scripts", ROOT / "scripts"]     # cron script 解析目录有歧义 → 两处都放
    rid = uuid.uuid4().hex[:8]
    model, provider = read_model(phome / "config.yaml")

    # 同内容 + 未过期 + 时间接近的提醒，默认不重复建
    rp = phome / "reminders.json"
    store = {"reminders": []}
    if rp.exists():
        try:
            store = json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            store = {"reminders": []}
    store.setdefault("reminders", [])
    if not args.force:
        for r in store["reminders"]:
            if (r.get("content") == args.content and r.get("user_id") == args.uid
                    and r.get("status") in ("scheduled", "reminded")):
                print(json.dumps({"ok": False, "error": "已有一条同内容未完成的提醒",
                                  "existing": {"id": r.get("id"), "status": r.get("status"),
                                               "scheduled_at": r.get("scheduled_at")},
                                  "hint": "要再建一条就加 --force，或先取消旧的"},
                                 ensure_ascii=False, indent=2))
                return 2

    plan, new_files, jobs = [], [], []
    for stage in STAGES:
        at = base + timedelta(minutes=CHASE_OFFSET_MIN[stage])
        at_iso = at.isoformat(timespec="seconds")
        jid = uuid.uuid4().hex[:12]
        script = f"reminder_{rid}_{stage}.py"
        wrapper = WRAPPER_TMPL.format(rid=rid, stage=stage, profile=args.profile,
                                      push=str(PUSH).replace("\\", "/"))
        jobs.append({
            "id": jid,
            "name": f"提醒-{args.content}-{LABEL[stage]}",
            "prompt": f"no_agent 提醒投递（{args.content} / {stage}，由 butler_reminder_create.py 生成）",
            "skills": [], "skill": None,
            "model": model, "provider": provider,
            "provider_snapshot": provider, "model_snapshot": model, "base_url": None,
            "script": script, "no_agent": True, "context_from": None,
            "schedule": {"kind": "once", "run_at": at_iso, "display": f"once at {at:%Y-%m-%d %H:%M}"},
            "schedule_display": f"once at {at:%Y-%m-%d %H:%M}",
            "repeat": {"times": 1, "completed": 0},
            "enabled": True, "state": "scheduled", "paused_at": None, "paused_reason": None,
            "created_at": now.isoformat(timespec="seconds"),
            "next_run_at": at_iso, "last_run_at": None, "last_status": None,
            "last_error": None, "last_delivery_error": None,
            "deliver": "local", "origin": None, "enabled_toolsets": None,
            "workdir": None, "fire_claim": None,
        })
        for d in scripts_dirs:
            new_files.append((d / script, wrapper))
        plan.append({"stage": stage, "at": at_iso, "job_id": jid, "script": script})
        jobs[-1]["_wrapper"] = wrapper

    out = {"ok": True, "dry_run": args.dry_run, "rid": rid, "uid": args.uid,
           "profile": args.profile, "content": args.content,
           "model": model, "provider": provider,
           "scheduled_at": base.isoformat(timespec="seconds"),
           "jobs": [{k: v for k, v in p.items()} for p in plan],
           "wrapper_paths": [str(p) for p, _ in new_files]}

    if args.dry_run:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # ---- 落盘 ----
    for path, content in new_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    rec = {"id": rid, "user_id": args.uid, "platform": "wxbot", "chat_id": args.uid,
           "content": args.content,
           "created_at": now.isoformat(timespec="seconds"),
           "scheduled_at": base.isoformat(timespec="seconds"),
           "status": "scheduled",
           "cron_job_id": plan[0]["job_id"],
           "followup_job_ids": [p["job_id"] for p in plan[1:]],
           "followup_count": 0}
    store["reminders"].append(rec)
    rp.parent.mkdir(parents=True, exist_ok=True)
    tmp = rp.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(rp)

    jp = phome / "cron" / "jobs.json"
    jp.parent.mkdir(parents=True, exist_ok=True)
    jdata = {"jobs": [], "updated_at": now.isoformat(timespec="seconds")}
    if jp.exists():
        try:
            jdata = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            pass
    jdata.setdefault("jobs", [])
    for job in jobs:
        job.pop("_wrapper", None)
        jdata["jobs"].append(job)
    jdata["updated_at"] = now.isoformat(timespec="seconds")
    tmpj = jp.with_suffix(".tmp")
    tmpj.write_text(json.dumps(jdata, ensure_ascii=False, indent=2), encoding="utf-8")
    tmpj.replace(jp)

    out["jobs_in_file"] = len(jdata["jobs"])
    out["reminders_in_file"] = len(store["reminders"])
    out["hint"] = "已创建；确认回复只用一句'⏰ 好嘞，到点喊你～'。不要运行 main/chase 脚本做自检（会真发）。"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
