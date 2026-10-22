"""主窗口持续收件；模型与发件通过 SQLite 队列和 UI 主线程衔接。"""
from dataclasses import asdict
import math
import time
import uuid

from common.flow_trace import FlowTrace,queue_trace_path
from .wechat.clipboard import restore_pending

from .delivery import DeliveryPump
from .config import validate_model_concurrency, validate_runtime_config
from .log import log
from .queue_store import Incoming, QueueStore, queue_database
from .queue_worker import ModelWorker
from .state import new_messages, overlap_end
from .wechat.chat_window import Message
from .wechat.main_window import MainWindow, Session


def mentioned_text(text: str, names: list[str]) -> str | None:
    import re

    separators = r"[\s\u00a0\u2000-\u200b\u202f\u205f\u3000]"
    for name in names:
        name = str(name).strip().lstrip("@")
        if not name:
            continue
        match = re.search(r"@" + re.escape(name) + r"(?=" + separators + r"|[:：,，]|$)"
                          r"(?:[\s\u00a0\u2000-\u200b\u202f\u205f\u3000]+|[:：,，]\s*)?",
                          text, flags=re.IGNORECASE)
        if match:
            return (text[:match.start()] + text[match.end():]).strip()
    return None


class MainInbox:
    def __init__(self, cfg, router, *, desktop=None, store=None,
                 clock=time.time, monotonic=time.monotonic):
        validate_runtime_config(cfg)
        self.cfg, self.bot = cfg, cfg["bot"]
        self.clock, self.monotonic = clock, monotonic
        self.desktop = desktop if desktop is not None else MainWindow(cfg["wechat"])
        qcfg = cfg.get("queue", {})
        concurrency = qcfg.get('max_model_requests', 2)
        validate_model_concurrency(concurrency)
        quiet = float(qcfg.get("quiet_seconds", 3))
        max_wait = float(qcfg.get("max_wait_seconds", 10))
        confirm_timeout = float(qcfg.get("confirm_timeout", 5))
        if (not all(math.isfinite(value) for value in (quiet, max_wait, confirm_timeout))
                or quiet < 0 or max_wait <= 0 or confirm_timeout <= 0):
            raise ValueError("queue.quiet_seconds 必须 >= 0，max_wait_seconds/confirm_timeout 必须 > 0，且为有限数值")
        self.store = store if store is not None else QueueStore(
            queue_database(cfg), failure_timeout_seconds=qcfg.get('failure_discard_seconds', 180))
        self.trace = FlowTrace(queue_trace_path(self.store.path),log.info)
        self.chats, self.snapshots, self.pending = {}, {}, {}
        self.groups = set(self.bot.get("bound_groups", []))
        self.bound = set(self.bot.get("bound_users", [])) | self.groups
        self.listen_all = cfg["wechat"].get("main_window", {}).get("listen_all", True)
        for name, (snapshot, group_mode) in self.store.snapshots().items():
            self.snapshots[name] = [Message(**item) for item in snapshot]
            if group_mode:
                self.groups.add(name)
        for row in self.store.pending_sessions():
            self.pending[row["contact"]] = Session(row["contact"], row["unread_count"], bool(row["mentioned"]))
        self.worker = ModelWorker(
            self.store, router, quiet=quiet, max_wait=max_wait,
            prefix=self.bot.get("command_prefix", "/"), clock=clock,
            reply_delay_min=self.bot.get("reply_delay_min", 0.8),
            reply_delay_max=self.bot.get("reply_delay_max", 2.5),
            max_concurrency=concurrency,trace=self.trace,
        )
        self.delivery = DeliveryPump(
            self.store, self._chat, self._capture_target, self._discover,
            timeout=confirm_timeout, clock=clock, monotonic=monotonic,
            capture_messages=self._capture,
        )
        self.desktop.before_switch = self._before_switch
        self._connected = None
        self._next_poll = 0
        self._next_ui = 'receive'
        self._receive_retry = {}

    def start(self):
        self.store.acquire_runtime()
        recovered = self.store.recover()
        log.info("[队列] 已恢复：%s；当前状态：%s", recovered, self.store.counts())
        self.delivery.reconcile()
        self.worker.start()

    def close(self):
        self.delivery.close()
        restore_pending(force=True)
        if self.worker.stop():
            self.store.close()
        else:
            log.warning("[队列] 模型请求尚未返回；已持久化处理中状态，重启后核对，不自动重放")

    def _allowed(self, name):
        return self.listen_all or name in self.bound

    def _chat(self, name):
        if name not in self.chats:
            self.chats[name] = self.desktop.chat(name, group_mode=name in self.groups)
            self.chats[name].expected_group = (name in self.groups
                                              if name in self.snapshots or name in self.groups else None)
        return self.chats[name]

    def _capture(self, name, chat, messages, *, fresh=None):
        expected = getattr(chat, "expected_group", None)
        if expected is not None and chat.group_mode != expected:
            raise RuntimeError(f"[{name}] 会话类型变化，拒绝覆盖原快照或继续收发")
        if fresh is None:
            previous = self.snapshots.get(name)
            fresh = new_messages(previous, messages) if previous else messages if previous == [] else []
        incoming = []
        for message in fresh:
            if message.sender != "other" or not self._allowed(name):
                continue
            text, member, context = message.text, "", ""
            if chat.group_mode:
                text = mentioned_text(text, self.bot.get("mention_names", []))
                if text is None:
                    log.info("[%s] 群消息未 @机器人，跳过", name)
                    continue
                member = message.sender_key or "unknown-" + uuid.uuid4().hex
                context = (f"[群聊发言人：{message.sender_name or '未知成员'}; "
                           f"member_id={message.sender_key or 'unknown'}]")
            incoming.append(Incoming(text, member, context))
        ids = self.store.capture(name, [asdict(m) for m in messages], incoming,
                                 group_mode=chat.group_mode, now=self.clock())
        self.snapshots[name] = messages  # 事务成功后才移动锚点。
        chat.expected_group = chat.group_mode
        self.pending.pop(name, None)
        if chat.group_mode:
            self.groups.add(name)
        if ids:
            log.info("[队列][%s] 采集入库 %d 条，接收序号 %s–%s，等待连续消息合并",
                     name, len(ids), ids[0], ids[-1])

    def _before_switch(self, current, root):
        if current.title not in self.snapshots:
            return
        chat = self._chat(current.title)
        chat.group_mode = current.group_mode
        self._capture(current.title, chat, chat.read_from_window(root))

    def deliver(self, request):
        return self.delivery.enqueue(request)

    def _discover(self, *, scan=False):
        for session in self.desktop.sessions(scan=scan):
            if not session.unread_count or not self._allowed(session.contact):
                continue
            if session.contact in self.groups and not session.mentioned:
                continue
            if session.contact not in self.pending:
                log.info("[%s] 发现未读 %d 条；有人@我=%s", session.contact,
                         session.unread_count, session.mentioned)
            self.store.remember_session(session.contact, session.unread_count,
                                        session.mentioned, now=self.clock())
            previous = self.pending.get(session.contact)
            self.pending[session.contact] = Session(
                session.contact, max(session.unread_count, previous.unread_count if previous else 0),
                session.mentioned or bool(previous and previous.mentioned),
            )

    def _receive(self, session):
        name = session.contact
        chat = self._chat(name)
        # Re-click an unread conversation even when its panel is already selected;
        # merely activating WeChat does not acknowledge its unread badge.
        available = chat.available(click_current=True) if session.unread_count else chat.available()
        if not available:
            return False
        if session.unread_count:
            messages, unread = chat.read_bundle(session.unread_count)
            previous = self.snapshots.get(name)
            if previous is None or (previous and overlap_end(previous, messages) is None):
                fresh = unread
                if previous:
                    log.warning("[%s] 旧快照已不在加载区，按未读 %d 条采集当前可读取的消息",
                                name, session.unread_count)
            elif [m.text for m in previous] == [m.text for m in messages]:
                fresh = unread
                if fresh:
                    log.info("[%s] 快照正文相同，按明确未读信号补采 %d 条", name, len(fresh))
            else:
                fresh = None
        else:
            messages, fresh = chat.read_messages(), None
        self._capture(name, chat, messages, fresh=fresh)
        return True

    def _capture_target(self, name):
        return self._receive(self.pending.get(name, Session(name)))

    def _capture_current(self, *, root=None):
        root = self.desktop.passive_window(self.bound, root=root)
        if root is None:
            return
        current = self.desktop.current_conversation(root)
        if current is None or not self._allowed(current.title) or current.title in self.pending:
            return
        if not self.desktop.matches(root, current.title):
            return
        chat = self._chat(current.title)
        chat.group_mode = current.group_mode
        self._capture(current.title, chat, chat.read_from_window(root))

    def _receive_one(self):
        if not self._connected:
            return False
        now = self.monotonic()
        session = next((s for s in self.pending.values()
                        if self._receive_retry.get(s.contact, 0) <= now), None)
        if session is None:
            return False
        succeeded = False
        try:
            succeeded = self._receive(session)
        except Exception as exc:
            log.error('[%s] 采集失败，未读任务保留待下轮处理: %s',
                      session.contact, type(exc).__name__)
        if succeeded:
            self._receive_retry.pop(session.contact, None)
        else:
            self._receive_retry[session.contact] = now + self._poll_interval()
        return True

    def _poll_interval(self):
        return max(0.1, float(self.bot.get('poll_interval', 1.5)))

    def poll(self, *, allow_switch=False):
        connected = self.desktop.available()
        if connected != self._connected:
            self._connected = connected
            if connected:
                log.info("[主窗口] 已连接微信主窗口，持续采集会话消息")
            else:
                log.warning("[主窗口] 没找到微信主窗口，请保持微信已登录并打开")
        if not connected:
            return
        self._discover()  # 普通轮询永远不滚动/激活；有待采集任务才选择会话。
        if allow_switch and not self.delivery.busy:
            self._receive_one()
        active = self.delivery.active
        # After Enter, the delivery reader owns this snapshot until it has
        # classified the new bubble. Do not enqueue it through a second,
        # potentially different visual reading before confirmation completes.
        if active is not None and active.typing.enter_attempted:
            return
        self._capture_current(root=active.typing.win if active is not None else None)

    def tick(self):
        restore_pending()
        was_busy = self.delivery.busy
        if self.monotonic() >= self._next_poll:
            try:
                self.poll(allow_switch=False)
            except Exception as exc:
                log.error("[队列] 会话采集暂时失败，保留快照与未读任务: %s", type(exc).__name__)
            finally:
                self._next_poll = self.monotonic() + self._poll_interval()
        self.delivery.tick(allow_start=False)
        if was_busy:
            if not self.delivery.busy:
                self._next_poll = 0
            return
        receive_ready = bool(self._connected and any(
            self._receive_retry.get(name, 0) <= self.monotonic() for name in self.pending))
        send_ready = self.store.has_ready_delivery(now=self.clock())
        action = self._next_ui if receive_ready and send_ready else 'receive' if receive_ready else 'send'
        if action == 'receive' and receive_ready:
            if self._receive_one():
                self._next_ui = 'send'
        elif send_ready and self.delivery.start_next():
            self._next_ui = 'receive'


def run_main_inbox(cfg, router, queue):
    inbox = MainInbox(cfg, router)
    log.info("微信主窗口队列模式；监听范围：%s；连续消息合并=%s 秒，最长=%s 秒",
             "全部会话" if inbox.listen_all else "已绑定会话", inbox.worker.quiet, inbox.worker.max_wait)
    if not cfg["bot"].get("mention_names"):
        log.warning("[bot].mention_names 为空，群聊不会触发回复")
    try:
        inbox.start()
        while True:
            for request in queue.drain():
                inbox.deliver(request)
            try:
                inbox.tick()
            except Exception as exc:
                log.error("[队列] UI 采集/发送暂时失败，保留持久化任务: %s", type(exc).__name__)
            time.sleep(0.05)
    finally:
        inbox.close()
