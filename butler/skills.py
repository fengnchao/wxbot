"""决策层（第二半）：管家**能调哪些 skill** 的白名单 + 执行器。

这是本项目存在的理由：把"要不要调 skill"从提示词搬进代码。三条纪律：
  1. 白名单 —— 模型只能点名 CATALOG 里有的 skill，别的名字一律拒绝并记日志；
  2. 执行只有两种形态：本地脚本（确定性，优先）或 delegate（再问一次 Hermes，借它的 skill）；
  3. 每个 action 的成败都回给调用方（`actions` 数组），失败不吞。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from contextlib import nullcontext

# 让模型知道"想说执行动作时怎么说"。这段属于管家（协议由管家定义），
# 但需要由 Hermes 侧的 skill 转述给模型，所以放在这里 export 出去。
HERMES_HINT = (
    "如果需要执行动作（而不是只回文字），在回复末尾附一个带外标记，用户看不到它：\n"
    '<<butler:action {"skill":"<名字>","args":{...}}>>\n'
    "可用 skill：" + "、".join(["reminder.create", "reminder.list", "reminder.cancel",
                                "learn.card", "quiz.next"]) + "\n"
    "reminder.create 的 args：{\"content\":\"喝水\",\"at\":\"+30m 或 2026-10-11 15:00\"}\n"
    "只回文字、不需要动作时，不要写这个标记。"
)


@dataclass
class ActionResult:
    skill: str
    ok: bool
    detail: str = ""
    text: str = ""

    def as_dict(self) -> dict:
        return {"skill": self.skill, "ok": self.ok, "detail": self.detail,
                "text": self.text[:300]}


@dataclass
class Ctx:
    """执行 action 需要的东西：配置路径、当前联系人、Hermes 客户端。"""
    cfg: object
    contact: object
    hermes: object
    log: object = field(default=lambda *a, **k: None)
    skill_policy: dict | None = None
    runtime_locks: object | None = None

    def profile_dir(self) -> Path:
        return Path(self.cfg.hermes_root) / "profiles" / self.contact.profile

    def reminders(self) -> Path:
        return self.profile_dir() / "reminders.json"

    def script(self, name: str) -> str | None:
        p = os.path.join(self.cfg.script_dir or "", name)
        return p if os.path.exists(p) else None


# ---------------- 具体 skill ----------------

def _create_reminder(ctx: Ctx, args: dict) -> ActionResult:
    content = str(args.get("content") or "").strip()
    at = str(args.get("at") or "").strip()
    if not content or not at:
        return ActionResult("reminder.create", False, "缺 content 或 at")
    script = ctx.script("butler_reminder_create.py")
    if not script:
        return ActionResult("reminder.create", False,
                            f"找不到脚本 butler_reminder_create.py（script_dir={ctx.cfg.script_dir}）")
    cmd = [sys.executable, script, "--uid", ctx.contact.uid, "--profile", ctx.contact.profile,
           "--content", content, "--at", at]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        return ActionResult("reminder.create", False, f"执行异常 {type(e).__name__}: {e}")
    out = (r.stdout or "").strip()
    ok = r.returncode == 0
    detail = out[:300] or (r.stderr or "")[:300]
    return ActionResult("reminder.create", ok, detail)


def _list_reminders(ctx: Ctx, args: dict) -> ActionResult:
    p = ctx.reminders()
    if not p.exists():
        return ActionResult("reminder.list", True, "没有提醒文件", "现在没有进行中的提醒")
    try:
        store = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return ActionResult("reminder.list", False, f"读 reminders.json 失败: {e}")
    live = [r for r in (store.get("reminders") or [])
            if r.get("status") in ("scheduled", "reminded", "pending")]
    if not live:
        return ActionResult("reminder.list", True, "0 条", "现在没有进行中的提醒")
    lines = [f"· {r.get('content')} @ {r.get('scheduled_at')}（{r.get('status')}）" for r in live]
    return ActionResult("reminder.list", True, f"{len(live)} 条", "\n".join(lines))


def _cancel_reminder(ctx: Ctx, args: dict) -> ActionResult:
    """取消提醒 = reminders.json 置 cancelled + 把该提醒的 cron 任务从 Profile 里摘掉。"""
    rid = str(args.get("id") or "").strip()
    content = str(args.get("content") or "").strip()
    p = ctx.reminders()
    if not p.exists():
        return ActionResult("reminder.cancel", False, "没有提醒文件")
    try:
        store = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return ActionResult("reminder.cancel", False, f"读 reminders.json 失败: {e}")
    hit = None
    for r in (store.get("reminders") or []):
        if r.get("status") not in ("scheduled", "reminded", "pending"):
            continue
        if (rid and r.get("id") == rid) or (content and r.get("content") == content):
            hit = r
            break
    if not hit:
        return ActionResult("reminder.cancel", False, "没找到匹配的未完成提醒")
    hit["status"] = "cancelled"
    hit["cancelled_at"] = datetime.now().isoformat(timespec="seconds")
    p.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")

    ids = {hit.get("cron_job_id"), *(hit.get("followup_job_ids") or [])} - {None}
    removed = _drop_cron_jobs(ctx.profile_dir() / "cron" / "jobs.json", ids)
    return ActionResult("reminder.cancel", True,
                        f"已取消 {hit.get('id')}；摘掉 cron 任务 {removed} 个")


def _drop_cron_jobs(jobs_json: Path, ids: set) -> int:
    if not jobs_json.exists() or not ids:
        return 0
    try:
        d = json.loads(jobs_json.read_text(encoding="utf-8"))
    except Exception:
        return 0
    before = len(d.get("jobs") or [])
    d["jobs"] = [j for j in (d.get("jobs") or []) if j.get("id") not in ids]
    n = before - len(d["jobs"])
    if n:
        tmp = jobs_json.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(jobs_json)
    return n


def _delegate(instruction: str, user_text: str = ""):
    """生成一个 delegate 执行器：把 skill 的职责转述给 Hermes（同一会话，连续性不丢）。"""
    def run(ctx: Ctx, args: dict) -> ActionResult:
        text = str(args.get("text") or user_text or "").strip()
        try:
            out = ctx.hermes.chat(ctx.contact, text, extra_system=instruction,
                                  skill_policy=ctx.skill_policy)
        except Exception as e:
            return ActionResult("delegate", False, f"delegate 调用失败: {e}")
        return ActionResult("delegate", True, "已由 Hermes 侧 skill 执行", out)
    return run


# ---------------- 白名单 ----------------

@dataclass
class SkillSpec:
    name: str
    kind: str                       # "local" 本地确定性 | "hermes" 借 Hermes 的 skill
    run: object
    desc: str = ""


CATALOG: dict[str, SkillSpec] = {
    "reminder.create": SkillSpec("reminder.create", "local", _create_reminder,
                                 "建一条定时提醒（脚本确定性地写 reminders.json + cron）"),
    "reminder.list": SkillSpec("reminder.list", "local", _list_reminders, "列出进行中的提醒"),
    "reminder.cancel": SkillSpec("reminder.cancel", "local", _cancel_reminder, "取消提醒并摘掉 cron"),
    "learn.card": SkillSpec("learn.card", "hermes",
                            _delegate("请按 wechat-learn 技能，把用户刚才的内容整理成知识卡片并归档。"),
                            "知识卡片（执行在 Hermes 的 wechat-learn）"),
    "quiz.next": SkillSpec("quiz.next", "hermes",
                           _delegate("请按 wechat-quiz 技能，随机抽一道题考用户。"),
                           "随机抽题（执行在 Hermes 的 wechat-quiz）"),
}


def execute(action: dict, ctx: Ctx) -> ActionResult:
    name = str(action.get("skill") or "").strip()
    spec = CATALOG.get(name)
    if spec is None:
        return ActionResult(name or "(空)", False,
                            f"不在白名单里；可用：{', '.join(sorted(CATALOG))}")
    args = action.get("args") or {}
    try:
        guard = (ctx.runtime_locks.profile(ctx.contact.profile)
                 if spec.kind == 'local' and ctx.runtime_locks else nullcontext())
        with guard:
            res = spec.run(ctx, args)
    except Exception as e:
        return ActionResult(name, False, f"{type(e).__name__}: {e}")
    res.skill = name
    return res


def catalogue() -> list[dict]:
    return [{"name": s.name, "kind": s.kind, "desc": s.desc} for s in CATALOG.values()]
