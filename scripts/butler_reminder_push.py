#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提醒投递（wxbot 通道 / no_agent cron 专用）。

用法: butler_reminder_push.py <stage> <rid> [profile]    stage in main|chase1|chase2|chase3

语义：stdout 为空 = 不投递（静默）。只有 wxbot 通道不可用（退出码 2）时才把正文
打到 stdout 作最后机会。内部异常一律吞掉并记日志，避免把错误推给用户。

文案按 reminders.json 里的 content 动态生成（支持任意提醒内容，不再写死喝水）。
注意：不要以标点结尾——wxbot 读回自己发的气泡时末尾标点会丢失，
导致 _sent 文本比对失配、被误判成对方消息而自环。
"""
import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROFILES_ROOT = Path(r"D:/ai/hermes/profiles")
PROFILE_ID = "wxbot-101"                    # 默认；多用户时由 argv[2] + use_profile() 覆盖
PROFILE_HOME = PROFILES_ROOT / PROFILE_ID
REMINDERS = PROFILE_HOME / "reminders.json"
LOG = PROFILE_HOME / "logs" / "butler_reminder.log"
WXBOT_DELIVER = Path(r"D:/bot/scripts/wxbot_deliver.py")
DRY = os.environ.get("BUTLER_DRY") == "1"
_DRY = DRY


def use_profile(name):
    """切到某个 Profile 的提醒状态（wxbot 多用户：每个联系人一个 Profile）。

    名字非法或不存在 → 返回 False（调用方据此判定为自检/误用，转演练）。
    """
    global PROFILE_ID, PROFILE_HOME, REMINDERS, LOG
    n = (name or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._\-]{1,40}", n):
        return False
    d = PROFILES_ROOT / n
    if not d.is_dir():
        return False
    PROFILE_ID, PROFILE_HOME = n, d
    REMINDERS, LOG = d / "reminders.json", d / "logs" / "butler_reminder.log"
    return True

# 每种内容的文案模板（main / chase1 / chase2 / chase3），{name} 会被替换成称呼
CONTENT_TEXTS = {
    "喝水": {
        "main": "⏰ {name}！喝水时间到啦～ 忙了这么久，起来走走，给杯子续个水 💧 喝完回我一下哦",
        "chase1": "💧 {name}～ 喝水的提醒别忘了哦！看到回我一下",
        "chase2": "🥤 {name}！水还没喝吗？别忘了呀～ 看到回我",
        "chase3": "😤 {name}！喊了三次啦，水还是没喝，不管你了哼",
    },
    "打水": {
        "main": "⏰ {name}！该去打水啦～ 别忘了哦 🚰 打完回我一下哦",
        "chase1": "🚰 {name}～ 打水那事儿别忘了哦！看到回我一下",
        "chase2": "⏳ {name}！水还没打回来吗～ 别忘了呀 看到回我",
        "chase3": "😤 {name}！喊了三次啦，水还是没打，不管你了哼",
    },
    "抽烟": {
        "main": "⏰ {name}！该去抽烟咯～ 说好的别忘了哈 🚬 抽完回我一下哦",
        "chase1": "🚬 {name}～ 抽烟那事儿别忘了哦！看到回我一下",
        "chase2": "⏳ {name}！烟还没去抽吗～ 别忘了呀 看到回我",
        "chase3": "😤 {name}！喊了三次啦，烟还是没抽，不管你了哼",
    },
}

GENERIC_TEXTS = {
    "main": "⏰ {name}！{content}的时间到啦～ 别忘了哦 弄完回我一下哦",
    "chase1": "⏳ {name}～ {content}的提醒别忘了哦！看到回我一下",
    "chase2": "⏳ {name}！{content}还没去做吗～ 别忘了呀 看到回我",
    "chase3": "😤 {name}！喊了三次啦，{content}还是没动静，不管你了哼",
}


def texts_for(content):
    c = (content or "").strip()
    for key, tpl in CONTENT_TEXTS.items():
        if key in c:
            return tpl
    return GENERIC_TEXTS


def log(msg):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.now().isoformat(timespec="seconds"), msg))
    except Exception:
        pass


def load():
    try:
        d = json.loads(REMINDERS.read_text(encoding="utf-8"))
    except Exception:
        return {"reminders": []}
    if isinstance(d, list):
        d = {"reminders": d}
    d.setdefault("reminders", [])
    return d


def save(d):
    tmp = REMINDERS.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(REMINDERS)


def find(d, rid):
    for r in d.get("reminders", []):
        if r.get("id") == rid:
            return r
    return None


def display_name(uid):
    try:
        p = json.loads((PROFILE_HOME / "butler_profiles" / ("%s_user.json" % uid)).read_text(encoding="utf-8"))
        if (p.get("name") or "").strip():
            return p["name"].strip()
    except Exception:
        pass
    try:
        p = json.loads((PROFILE_HOME / "butler_profiles" / ("%s.json" % uid)).read_text(encoding="utf-8"))
        return ((p.get("answers") or {}).get("0") or "").strip()
    except Exception:
        return ""


def deliver(text):
    if _DRY:
        # 演练：只写日志、绝不打 stdout（no_agent cron 下 stdout 非空 = 会被当成投递内容送出去）
        log("DRY 未发送: " + text[:120])
        if os.environ.get("BUTLER_REMINDER_VERBOSE") == "1":
            print("[DRY] " + text)
        return 0
    r = subprocess.run([sys.executable, str(WXBOT_DELIVER), "--profile", PROFILE_ID,
                        "--job-id", "butler-reminder", "--job-name", "提醒", "--text", text],
                       capture_output=True, text=True, timeout=180)
    tail = (r.stdout or "").strip() or (r.stderr or "").strip()
    log("deliver rc=%s out=%r" % (r.returncode, tail[:200]))
    if r.returncode == 2 and tail:
        print(text)
    return r.returncode


def run():
    args = sys.argv[1:]
    stage = args[0] if args else ""
    rid = args[1] if len(args) > 1 else ""
    prof_arg = args[2] if len(args) > 2 else ""      # 可选：目标 Profile（多用户时 wrapper 会带上）
    extra = args[3:]                                 # 再多出来的参数 = 自检/误用
    global _DRY
    ok_prof = use_profile(prof_arg) if prof_arg else True
    # 自检护栏（2026-10-10 实测：管家"自检"时真把提醒发出去了一条）：
    # 多带参数 / 认不出的 Profile / selftest 阶段 → 一律只演练：不发送、不改状态。
    _DRY = DRY or bool(extra) or not ok_prof or stage in ("selftest", "check", "dryrun")
    if _DRY:
        log("DRY 演练 stage=%s rid=%s profile=%s extra=%s" % (stage, rid, PROFILE_ID, list(extra)))
    d = load()
    r = find(d, rid)
    if not r:
        log("rid=%s stage=%s NOT FOUND, silent" % (rid, stage))
        return 0
    status = r.get("status")
    uid = r.get("user_id", "")
    content = r.get("content", "")
    tpl = texts_for(content)
    if stage == "main":
        if status in ("acknowledged", "cancelled", "expired"):
            log("rid=%s status=%s, skip" % (rid, status))
            return 0
        if _DRY:
            log("DRY main rid=%s（不发送、不改状态）" % rid)
            return 0
        r["status"] = "reminded"
        r["followup_count"] = 0
        save(d)
        log("rid=%s main -> send" % rid)
        deliver(tpl["main"].format(name=display_name(uid), content=content))
        return 0
    if not (stage.startswith("chase") and stage[-1] in "123"):
        log("rid=%s unknown stage=%s" % (rid, stage))
        return 0
    n = stage[-1]
    if status != "reminded":
        log("rid=%s status=%s != reminded, skip %s" % (rid, status, stage))
        return 0
    if _DRY:
        log("DRY %s rid=%s（不发送、不改状态）" % (stage, rid))
        return 0
    if n == "3":
        r["status"] = "expired"
    r["followup_count"] = int(n)
    save(d)
    log("rid=%s %s -> send" % (rid, stage))
    deliver(tpl[stage].format(name=display_name(uid), content=content))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except SystemExit:
        raise
    except Exception:
        log("EXC " + traceback.format_exc()[:600].replace("\n", " | "))
        sys.exit(0)
