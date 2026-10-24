"""管家主流程（把各块按顺序串起来）。

一条消息的生命周期：
  1. 认领补发队列（调模型之前！）
  2. 前置规则（空消息 / 新会话）
  3. 投递 Hermes（大模型 + skill 运行时）
  4. 拿结果 → 判断是否调用其他 skill（白名单执行）
  5. 静默判定 → 拼补发 → 出最终文案
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import time
import uuid

from common.flow_trace import FlowTrace, butler_trace_path, record

from .config import Config
from .contacts import Contact
from .flowlog import FlowLog
from .groups import GroupStore
from .hermes import HermesClient, HermesError
from .skill_policy import SkillPolicyStore
from .pending import PendingQueue, EmptyPendingQueue
from .push import push_to_wxbot
from .reply import split_reply
from .concurrency import RuntimeLocks
from . import router, skills


@dataclass
class Result:
    reply: str | None = None
    actions: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def as_dict(self, *, reply_chunk_chars=500) -> dict:
        return {"reply": self.reply, "actions": [a.as_dict() for a in self.actions],
                "reply_parts": split_reply(self.reply, reply_chunk_chars),
                "meta": {"reply_complete": True, **self.meta}}


class Butler:
    def __init__(self, cfg: Config, log=None):
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)
        self.runtime_locks = RuntimeLocks(cfg.hermes_url)
        self.hermes = HermesClient(cfg, self.log, locks=self.runtime_locks)
        self.skill_policies = SkillPolicyStore(cfg.heartbeat_config_path(), self.log)
        self.pending = PendingQueue(cfg.hermes_root, self.log, locks=self.runtime_locks)
        self.store = self.tools = None
        if cfg.provider == 'codex':
            from .plugin import validate_plugin
            self.plugin_info=validate_plugin(cfg.plugin_path())
            from .business import BusinessStore
            from .catalogue import SkillCatalogue
            from .tools import ToolService
            from .backends import create_backend
            self.store = BusinessStore(cfg.data_path()/'business.sqlite3')
            self.catalogue = SkillCatalogue(cfg.plugin_path()/'skills')
            self.tools = ToolService(self.store,self.catalogue,policy_loader=self.policy_for_contact,
                event_sink=lambda *args,**kw:self.trace.emit(*args,**kw))
            self.hermes = create_backend(cfg,self.log,locks=self.runtime_locks,store=self.store,tools=self.tools)
            self.pending = EmptyPendingQueue()
        self.flow = FlowLog(cfg.flow_log_path(), self.log)
        self.trace = FlowTrace(butler_trace_path(cfg.flow_log_path()), self.log)
        self.groups = GroupStore(cfg.group_file_path(), self.log)

    @property
    def backend(self):
        return self.hermes  # Preserve the public legacy alias used by integrations.

    def policy_for_contact(self,name):
        policy=self.skill_policies.for_contact(name)
        if self.cfg.provider=='codex':
            from .backends.codex import DEFAULT_POLICY
            return self.catalogue.validate(policy or DEFAULT_POLICY)
        return policy

    def heartbeat_contact(self,name):
        contact=self.contact_of(name)
        known=self.store.last_identity(name) if self.store else None
        return replace(contact,channel_type=known['channel_type']) if known else contact

    # ---------- 身份 ----------
    def contact_of(self, name: str) -> Contact:
        """未知联系人也要能回话（默认 profile=default, uid=窗口名），但留痕。"""
        c = self.cfg.contacts.get(name)
        if c is None:
            self.log("未知联系人的消息: %r → 按 default Profile 处理", name)
            return Contact(name=name, profile="default", uid=name)
        return c

    def _contact(self, name: str, channel_type: str, member_key: str = "") -> Contact:
        """按成员区分群会话：member_key 追加到 uid，使每个成员拥有独立 session 与记忆。"""
        c = replace(self.contact_of(name),
                    channel_type="group" if channel_type == "group" else "dm")
        if c.channel_type == "group" and member_key:
            c = replace(c, uid=f"{c.uid}::{member_key}")
        return c

    # ---------- 主流程 ----------
    def handle(self, contact_name: str, text: str, msg_id: str | None = None,
               channel_type: str = "dm", member_key: str = "", member_name: str = "") -> Result:
        started = time.monotonic()
        with self.trace.bind(contact_name, msg_id or uuid.uuid4().hex):
            record('butler_received','ok',characters=len(text))
            try:
                c = self._contact(contact_name, channel_type, member_key)
                record('butler_session','waiting')
                with self.runtime_locks.session(c):
                    record('butler_session','ok')
                    result = self._handle(c, text)
                record('butler_result','error' if result.meta.get('error') else 'ok',
                       characters=len(result.reply or ''),elapsed_ms=round((time.monotonic()-started)*1000))
            except Exception as exc:
                record('butler_result','error',error_type=type(exc).__name__,
                       elapsed_ms=round((time.monotonic()-started)*1000))
                raise
        if msg_id is not None:
            result.meta["msg_id"] = msg_id
        return result

    def _handle(self, c: Contact, text: str) -> Result:
        contact_name = c.name
        # Policies are keyed by WeChat window title. Apply a group role only when that
        # group window has an explicit policy; never infer it from an individual member.
        policy = self.policy_for_contact(c.name)
        self.flow.received(c.name, text)          # 流水：收到（在看板里与后面的回复配成一轮）

        # 1. 补发：先认领（这样模型自己再查队列看到的是空的，不会说两遍）
        pending = self.pending.take_and_claim(
            c, allow_unowned=self.cfg.contacts.is_sole_profile_owner(c))

        # 2. 前置规则
        dec = router.pre_route(c, text)
        if dec.kind == "reset":
            self.hermes.reset(c, skill_policy=policy)
            self.log("[%s] 新会话 id=%s", contact_name,
                     self.hermes.session_id(c, skill_policy=policy))
            reply = router.compose(["好，这段翻篇了，重新开始"], pending)
            self.flow.reply(c.name, reply)
            return Result(reply, meta={"reset": True, "pending": len(pending)})
        if dec.kind == "silent":
            reply = router.compose([], pending)
            self.flow.reply(c.name, reply)
            return Result(reply,
                          meta={"silent": True, "reason": dec.note, "pending": len(pending)})

        # 3. 投递 Hermes
        raw = ""
        try:
            raw = self.hermes.chat(c, text, skill_policy=policy)
        except HermesError as e:
            self.log("[%s] %s", contact_name, e)
            self.flow.api_error(c.name, str(e))
            if self.cfg.provider=='codex':
                return Result(reply=None,meta={'error':str(e),'status':e.status,'reply_complete':False,
                                              'retry_safe':getattr(e,'retry_safe',False) is True})
            if e.status in (401, 403):
                reply = "（配置错误：Hermes API Server 拒绝了这把密钥）"
            else:
                reply = "抱歉，我这边暂时出了点问题，稍后再试。"
            reply = router.compose([reply], pending)
            self.flow.reply(c.name, reply)
            return Result(reply,
                          meta={"error": str(e), "status": e.status, "pending": len(pending)})

        # 4. 拿结果 → 剥行动标记 → 判断是否调用其他 skill
        clean, acts = router.parse_actions(raw)
        results = []
        if acts and self.cfg.actions_enabled and self.cfg.provider!='codex':
            ctx = skills.Ctx(cfg=self.cfg, contact=c, hermes=self.hermes, log=self.log,
                             skill_policy=policy, runtime_locks=self.runtime_locks)
            for a in acts:
                record('butler_action','running',tool=a.get('skill',''))
                r = skills.execute(a, ctx)
                record('butler_action','completed' if r.ok else 'failed',tool=r.skill)
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
        self.flow.reply(c.name, reply)

        meta = {"pending": len(pending), "actions": len(results),
                "model_silent": model_silent, "sent": reply is not None,
                "session_id": self.hermes.session_id(c, skill_policy=policy)}
        return Result(reply, results, meta)

    # ---------- 其它 ----------
    def push(self, contact_name: str, text: str, *, push_type: int = 1,
             message_type: int | None = None) -> Result:
        """主动推送（type=1 指定用户）：记「外发」流水日志 → 转发 wxbot 代发。不走模型、不动会话。"""
        c = self.contact_of(contact_name)
        self.flow.outbound_queued(c.name, text)      # 看板：入队
        ok, detail = push_to_wxbot(self.cfg, c.name, text, self.log)
        if ok:
            self.flow.outbound_sent(c.name, text)    # 看板：已发出
        else:
            self.flow.api_error(c.name, f"外发失败: {detail}")
            self.log("[%s] 外发失败: %s", contact_name, detail)
        return Result(reply=None,
                      meta={"ok": ok, "detail": detail, "contact": c.name,
                            "type": push_type, "messageType": message_type})

    def push_group(self, message_type: int, text: str) -> Result:
        """群发（type=2）：按分组字典（messageType → 绑定用户）逐个推送。全部成功才算 ok。"""
        users = self.groups.users_of(message_type)
        self.log("群发 messageType=%s → 目标 %d 人: %s",
                 message_type, len(users), ", ".join(users) or "(无)")
        results = []
        for name in users:
            r = self.push(name, text, push_type=2, message_type=message_type)
            results.append({"contact": name, "ok": bool(r.meta.get("ok")),
                            "detail": r.meta.get("detail")})
        sent = sum(1 for r in results if r["ok"])
        return Result(reply=None, meta={
            "ok": bool(results) and sent == len(results),
            "detail": (f"{sent}/{len(results)} 已发送" if results
                       else f"messageType={message_type} 未绑定任何用户"),
            "type": 2, "messageType": message_type,
            "targets": list(users), "results": results})

    def reset(self, contact_name: str, *, channel_type: str = 'dm', member_key: str = "") -> Result:
        c = self._contact(contact_name, channel_type, member_key)
        with self.runtime_locks.session(c):
            policy = self.policy_for_contact(c.name)
            self.hermes.reset(c, skill_policy=policy)
        return Result("好，这段翻篇了，重新开始", meta={"reset": True})

    def health(self) -> dict:
        out = {}
        for p in sorted(self.cfg.contacts.profiles()):
            out[p] = self.hermes.alive(p)
        return out
