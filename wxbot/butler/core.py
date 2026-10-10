"""管家主流程（把各块按顺序串起来）。

一条消息的生命周期：
  1. 认领补发队列（调模型之前！）
  2. 前置规则（空消息 / 新会话）
  3. 投递 Hermes（大模型 + skill 运行时）
  4. 拿结果 → 判断是否调用其他 skill（白名单执行）
  5. 静默判定 → 拼补发 → 出最终文案
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .contacts import Contact
from .hermes import HermesClient, HermesError
from .pending import PendingQueue
from . import router, skills


@dataclass
class Result:
    reply: str | None = None
    actions: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"reply": self.reply, "actions": [a.as_dict() for a in self.actions],
                "meta": self.meta}


class Butler:
    def __init__(self, cfg: Config, log=None):
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)
        self.hermes = HermesClient(cfg, self.log)
        self.pending = PendingQueue(cfg.hermes_root, self.log)

    # ---------- 身份 ----------
    def contact_of(self, name: str) -> Contact:
        """未知联系人也要能回话（默认 profile=default, uid=窗口名），但留痕。"""
        c = self.cfg.contacts.get(name)
        if c is None:
            self.log("未知联系人的消息: %r → 按 default Profile 处理", name)
            return Contact(name=name, profile="default", uid=name)
        return c

    # ---------- 主流程 ----------
    def handle(self, contact_name: str, text: str, msg_id: str | None = None) -> Result:
        c = self.contact_of(contact_name)

        # 1. 补发：先认领（这样模型自己再查队列看到的是空的，不会说两遍）
        pending = self.pending.take(c.profile)
        if pending:
            self.pending.claim(c.profile, [i.get("key") for i in pending])

        # 2. 前置规则
        dec = router.pre_route(c, text)
        if dec.kind == "reset":
            self.hermes.reset(c)
            self.log("[%s] 新会话 id=%s", contact_name, self.hermes.session_id(c))
            return Result(router.compose(["好，这段翻篇了，重新开始"], pending),
                          meta={"reset": True, "pending": len(pending)})
        if dec.kind == "silent":
            return Result(router.compose([], pending),
                          meta={"silent": True, "reason": dec.note, "pending": len(pending)})

        # 3. 投递 Hermes
        raw = ""
        try:
            raw = self.hermes.chat(c, text)
        except HermesError as e:
            self.log("[%s] %s", contact_name, e)
            if e.status in (401, 403):
                reply = "（配置错误：Hermes API Server 拒绝了这把密钥）"
            else:
                reply = "抱歉，我这边暂时出了点问题，稍后再试。"
            return Result(router.compose([reply], pending),
                          meta={"error": str(e), "status": e.status, "pending": len(pending)})

        # 4. 拿结果 → 剥行动标记 → 判断是否调用其他 skill
        clean, acts = router.parse_actions(raw)
        results = []
        if acts and self.cfg.actions_enabled:
            ctx = skills.Ctx(cfg=self.cfg, contact=c, hermes=self.hermes, log=self.log)
            for a in acts:
                r = skills.execute(a, ctx)
                results.append(r)
                self.log("[%s] action %s ok=%s %s", contact_name, r.skill, r.ok, r.detail[:120])

        # 5. 静默判定 + 拼补发
        parts = []
        model_silent = router.is_silent(clean)
        if not model_silent:
            parts.append(clean)
        # action 产出的文本（delegate / list 这类）要给用户看；local 脚本自己会发提醒，不重复说
        for r in results:
            if r.ok and r.text and r.skill in ("reminder.list", "learn.card", "quiz.next"):
                parts.append(r.text)
        # 注意：模型说静默时，**认领过的补发照样要发** —— 静默的模型不能把积压吞掉。
        # 所以 sent 与 model_silent 是两个不同的判据，别混成一个。
        reply = router.compose(parts, pending)

        meta = {"pending": len(pending), "actions": len(results),
                "model_silent": model_silent, "sent": reply is not None,
                "session_id": self.hermes.session_id(c)}
        if msg_id:
            meta["msg_id"] = msg_id
        return Result(reply, results, meta)

    # ---------- 其它 ----------
    def reset(self, contact_name: str) -> Result:
        c = self.contact_of(contact_name)
        self.hermes.reset(c)
        return Result("好，这段翻篇了，重新开始", meta={"reset": True})

    def health(self) -> dict:
        out = {}
        for p in sorted(self.cfg.contacts.profiles()):
            out[p] = self.hermes.alive(p)
        return out
