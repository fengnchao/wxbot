"""主窗口持续收件；模型与发件通过 SQLite 队列和 UI 主线程衔接。"""
from dataclasses import asdict
from collections import OrderedDict
import math
import random
import time
import uuid

from common.flow_trace import FlowTrace,queue_trace_path,record
from .wechat.clipboard import restore_pending

from .delivery import DeliveryPump
from .config import validate_model_concurrency, validate_runtime_config, validate_typing_mode
from .log import log
from .queue_store import Incoming, QueueStore, queue_database
from .queue_worker import ModelWorker
from .state import new_messages, overlap_end
from .wechat.chat_window import Message, ReadDeferred
from .wechat.main_window import MainWindow, Session, preview_sender


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
                 clock=time.time, monotonic=time.monotonic, telegram=None):
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
            queue_database(cfg), failure_timeout_seconds=qcfg.get('failure_discard_seconds', 180),
            retry_delay_seconds=qcfg.get('retry_delay_seconds',20),
            max_delivery_retries=qcfg.get('max_delivery_retries',2),
            restart_chat_policy=qcfg.get('restart_chat_policy','discard'),
            directory_path=cfg.get('_directory_path'))
        self.trace = FlowTrace(queue_trace_path(self.store.path),log.info)
        self.chats, self.snapshots, self.pending = {}, {}, {}
        self.session_previews = {}
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
            typing_mode=validate_typing_mode(cfg.get('wechat', {})),
        )
        self.delivery = DeliveryPump(
            self.store, self._chat, self._capture_target, self._discover,
            timeout=confirm_timeout, clock=clock, monotonic=monotonic,
            capture_messages=self._capture_for_delivery,
        )
        self.desktop.before_switch = self._before_switch
        self._connected = None
        self._next_poll = 0
        self._next_ui = 'receive'
        self._receive_retry = {}
        self.telegram=telegram
        self._telegram_turn=False

    def start(self):
        self.store.acquire_runtime()
        recovered = self.store.recover()
        log.info("[队列] 已恢复：%s；当前状态：%s", recovered, self.store.counts())
        if not self.delivery.requires_ui_review and not (self.telegram and self.telegram.requires_ui_review):
            self.delivery.reconcile()
        self.sync_users()
        self.worker.start()

    def sync_users(self):
        """Register saved identities; never submit historical text or create replies."""
        observe = getattr(self.worker.router, 'observe_users', None)
        if observe is None:
            return
        # Current snapshots may contain only an unresolved row. Earlier captured
        # avatar evidence remains usable for enrollment without replaying text.
        captured = {}
        for row in self.store.identity_observations():
            captured.setdefault((row['contact'],row['group_mode']),[]).append(
                {key:row[key] for key in ('member_key','member_name','avatar')})
        for (name, group), values in captured.items():
            for offset in range(0,len(values),50):
                try:
                    observe(name, 'group' if group else 'dm', values[offset:offset+50])
                except Exception as exc:
                    log.warning('[用户登记] 已收头像登记失败，未重放历史消息：%s', type(exc).__name__)
                    return
        for name, messages in self.snapshots.items():
            metadata = {}
            for message in messages:
                if message.sender == 'other':
                    item = {'member_key': message.sender_key or '', 'member_name': message.sender_name or '',
                            'avatar': message.avatar or ''}
                    metadata[(item['member_key'], item['avatar']) if name in self.groups else ('dm','')] = item
            values = list(metadata.values())
            for offset in range(0, len(values), 50):
                try:
                    observe(name, 'group' if name in self.groups else 'dm', values[offset:offset+50])
                except Exception as exc:
                    log.warning('[用户登记] 启动快照登记失败，未重放历史消息：%s', type(exc).__name__)
                    return

    def close(self):
        telegram=getattr(self,'telegram',None)
        if telegram is not None:telegram.close()
        self.delivery.close()
        authorization=getattr(self,'relay_authorization',None)
        if authorization is not None:authorization.close()
        restore_pending(force=True)
        if self.worker.stop():
            self.store.close()
        else:
            log.warning("[队列] 模型请求尚未返回；已持久化处理中状态，重启后核对，不自动重放")

    def _allowed(self, name):
        return self.listen_all or name in self.bound

    def _should_interject(self):
        chance = float(self.bot.get("group_reply_chance", 0.1))
        return chance > 0 and random.random() < chance

    def _emoji_chance(self):
        return float(self.bot.get("emoji_chance", 0.2))

    def _emoji_available(self):
        """表情面板是否已校准（button/item 都配了才视为可用，未校准则自动降级为文字）。"""
        emoji = self.cfg.get("wechat", {}).get("emoji") or {}
        return bool(emoji.get("button")) and bool(emoji.get("item"))

    def _reply_mode(self, mentioned, *, contact=''):
        """群消息的回复方式：@必回文字；普通消息抽中后文字/表情二选一，未抽中静默。"""
        if mentioned:
            self._last_reply_reason = 'direct'
            record('wxbot_group_decision', 'direct')
            return "text"
        if self._should_interject():
            if contact:
                now = self.clock()
                history = getattr(self, '_group_reply_history', None)
                if history is None:
                    self._group_reply_history = history = OrderedDict()
                times = history.pop(contact, [])
                window = self.bot.get('group_reply_budget_window_seconds', 600)
                times = [at for at in times if now - at < window]
                history[contact] = times
                if len(history) > 1000:
                    history.popitem(last=False)
                if times and now - times[-1] < self.bot.get('group_reply_cooldown_seconds', 30):
                    self._last_reply_reason = 'cooldown'
                    record('wxbot_group_decision', 'cooldown')
                    return 'none'
                if len(times) >= self.bot.get('group_reply_budget', 10):
                    self._last_reply_reason = 'budget'
                    record('wxbot_group_decision', 'budget')
                    return 'none'
                times.append(now)
            if self._emoji_available() and random.random() < self._emoji_chance():
                self._last_reply_reason = 'emoji'
                record('wxbot_group_decision', 'emoji')
                return "emoji"
            self._last_reply_reason = 'random'
            record('wxbot_group_decision', 'random')
            return "text"
        self._last_reply_reason = 'silent'
        record('wxbot_group_decision', 'silent')
        return "none"

    def _group_direct_request(self, contact, member, text, mentioned, previous_sender):
        """Only the recent addressed member continues a turn after a bot bubble."""
        prefix = self.bot.get('command_prefix', '/')
        named = any(text.startswith(str(name).strip().lstrip('@') + delimiter)
                    for name in self.bot.get('mention_names', []) if str(name).strip().lstrip('@')
                    for delimiter in (' ', ',', '，', ':', '：', '、'))
        direct = mentioned or bool(prefix and text.startswith(prefix)) or named
        turns = getattr(self, '_group_direct_turns', None)
        if turns is None:
            self._group_direct_turns = turns = OrderedDict()
        now = self.clock()
        last_member, at = turns.get(contact, ('', float('-inf')))
        continuation = (previous_sender == 'self' and member == last_member and bool(member)
                        and 0 <= now - at < self.bot.get('group_continuation_seconds', 120))
        if direct or continuation:
            turns.pop(contact, None)
            turns[contact] = (member, now)
            if len(turns) > 1000:
                turns.popitem(last=False)
            return True
        return False

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
        session = self.pending.get(name)
        if (fresh is None and session and session.unread_count
                and not any(message.sender in {'other', 'system'} for message in messages)):
            # Passive/handoff/send reads contain text only. They cannot consume
            # pending unread work without a readable incoming row. A successful
            # read_bundle supplies explicit fresh entries, including [] for images.
            raise ReadDeferred('unread_messages_not_visible', '未读消息尚未在可读区域显示，保留未读任务等待重读')
        if fresh is None:
            previous = self.snapshots.get(name)
            fresh = new_messages(previous, messages) if previous else messages if previous == [] else []
        if any(message.sender == 'system' for message in fresh):
            # Text rows with no reliable direction are not system notifications.
            # Do not consume their text checkpoint before a readable retry.
            raise ReadDeferred('unknown_fresh_sender','新文字消息发送方暂不可确认，保留快照等待重读')
        # The session preview describes the last message, never an arbitrary earlier
        # incoming row. Keep the learned names scoped to this group across restarts.
        if chat.group_mode and messages and messages[-1].sender == "other":
            last = messages[-1]
            preview = self.session_previews.pop(name, "")
            nickname = preview_sender(preview, last.text)
            if nickname:
                try:
                    current = next((s.preview for s in self.desktop.sessions(scan=False)
                                    if s.contact == name), "")
                except Exception as exc:
                    log.debug("[%s] 无法复核群昵称摘要: %s", name, type(exc).__name__)
                    current = ""
                if current != preview:
                    nickname = None  # Another member may have sent the same text meanwhile.
            if (last.sender_key and nickname
                    and nickname != self.store.group_member_name(name, last.sender_key)):
                self.store.remember_group_member(name, last.sender_key, nickname, now=self.clock())
                log.info("[%s] 自动映射群成员昵称：member_id=%s，昵称=%s", name, last.sender_key, nickname)
        incoming = []
        previous_senders = {id(m): messages[n-1].sender if n else '' for n, m in enumerate(messages)}
        for message in fresh:
            if message.sender != "other" or not self._allowed(name):
                continue
            text, member, member_name, context = message.text, "", "", ""
            reply_mode = "text"
            if chat.group_mode:
                mention = mentioned_text(text, self.bot.get("mention_names", []))
                mentioned = mention is not None
                text = mention if mentioned else text      # 去掉 @Bot 前缀；无 @ 时保留原文
                member = message.sender_key or "unknown-" + uuid.uuid4().hex
                member_name = message.sender_name or ""
                if member_name == f"成员-{(message.sender_key or 'unknown')[:8]}":
                    member_name = ""
                member_name = member_name or self.store.group_member_name(name, member)
                context = (f"[群聊发言人：{member_name or '未知成员'}; "
                           f"member_id={message.sender_key or 'unknown'}]")
                direct = self._group_direct_request(name, member, text, mentioned,
                                                    previous_senders.get(id(message), ''))
                reply_mode = self._reply_mode(direct, contact=name)
                log.info("[%s] 群消息入队（成员 %s，回复方式=%s，member_id=%s，内容=%s）",
                         name, member_name, reply_mode, message.sender_key or 'unknown', text[:40])
            incoming.append(Incoming(text, member, context, member_name, reply_mode,
                                     avatar=getattr(message, 'avatar', ''),
                                     reply_reason=self._last_reply_reason if chat.group_mode else ''))
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
        try:
            self._capture(current.title, chat, chat.read_from_window(root))
        except ReadDeferred as exc:
            # This is the conversation being left, not the send target. Keep
            # its read task without preventing independent target validation.
            self._defer_capture(current.title, exc)

    def _defer_capture(self, name, exc):
        session = self.pending.get(name, Session(name))
        self.store.remember_session(name, session.unread_count, session.mentioned, now=self.clock())
        self.pending[name] = session
        self._receive_retry[name] = self.monotonic() + self._poll_interval()
        log.warning('[%s] 采集暂缓，保留快照与未读任务，发送仍独立核验: %s', name, exc.read_code)

    def _capture_for_delivery(self, name, chat, messages):
        try:
            self._capture(name, chat, messages)
        except ReadDeferred as exc:
            if exc.read_code not in {'unknown_fresh_sender', 'unknown_unread_sender', 'unread_messages_not_visible'}:
                raise
            # Baseline/bubble reads belong to DeliveryPump. An ambiguous
            # incoming row cannot invalidate its independently verified send.
            self._defer_capture(name, exc)

    def deliver(self, request):
        return self.delivery.enqueue(request)

    def _discover(self, *, scan=False):
        sessions = self.desktop.sessions(scan=scan)
        self.session_previews = {s.contact: s.preview for s in sessions}
        for session in sessions:
            if not session.unread_count or not self._allowed(session.contact):
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
            candidates = new_messages(previous, messages) if previous else []
            if not candidates:
                candidates = [message for message in messages if message.sender != 'self'][-session.unread_count:]
            if any(message.sender == 'system' for message in candidates):
                raise ReadDeferred('unknown_unread_sender','未读文字消息发送方暂不可确认，保留未读任务等待重读')
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
                # The bundle also verified nontext entries; keep its successful
                # read explicit even when no incoming text was found.
                fresh = new_messages(previous, messages) if previous else messages
        else:
            messages, fresh = chat.read_messages(), None
        self._capture(name, chat, messages, fresh=fresh)
        return True

    def _capture_target(self, name):
        try:
            return self._receive(self.pending.get(name, Session(name)))
        except ReadDeferred as exc:
            if exc.read_code not in {'unknown_fresh_sender', 'unknown_unread_sender', 'unread_messages_not_visible'}:
                raise
            # _receive already verified chat availability before sender
            # classification. DeliveryPump must still read its own baseline;
            # message_list_unavailable and all target errors remain fatal.
            self._defer_capture(name, exc)
            return True

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
            log.error('[%s] 采集失败，未读任务保留待下轮处理: %s%s',
                      session.contact, type(exc).__name__,
                      '（'+exc.read_code+'）' if isinstance(exc,ReadDeferred) else '')
        if succeeded:
            self._receive_retry.pop(session.contact, None)
        else:
            self._receive_retry[session.contact] = now + self._poll_interval()
        return True

    def _poll_interval(self):
        return max(0.1, float(self.bot.get('poll_interval', 1.5)))

    def poll(self, *, allow_switch=False):
        if self.cfg.get('_directory_path'):
            from butler.directory import DirectoryStore
            projection = DirectoryStore(self.cfg['_directory_path']).channel_projection()
            self.bot.update(projection.get('bot', {}))
            self.groups = set(self.bot.get('bound_groups', []))
            self.bound = set(self.bot.get('bound_users', [])) | self.groups
            self.listen_all = projection.get('wechat', {}).get('main_window', {}).get('listen_all', True)
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
        telegram=getattr(self,'telegram',None)
        if getattr(self.delivery,'requires_ui_review',False) or (telegram and getattr(telegram,'requires_ui_review',False)):
            return
        if telegram and telegram.busy:
            telegram.tick()
            self._next_poll=0
            return
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
        if telegram and (self._telegram_turn or not(receive_ready or send_ready)):
            self._telegram_turn=False
            if telegram.tick():return
        action = self._next_ui if receive_ready and send_ready else 'receive' if receive_ready else 'send'
        if action == 'receive' and receive_ready:
            if self._receive_one():
                self._next_ui = 'send'
                self._telegram_turn=True
        elif send_ready and self.delivery.start_next():
            self._next_ui = 'receive'
            self._telegram_turn=True


def run_main_inbox(cfg, router, queue):
    import os
    from pathlib import Path
    from .config import ROOT
    from .telegram_desktop import DesktopRelay
    base=Path(os.environ.get('WXBOT_CONFIG') or ROOT/'config.wxbot.toml').resolve().parent
    relay=cfg.get('telegram_relay',{})
    config_path=Path(relay.get('config','config.telegram-relay.toml'))
    state_path=Path(relay.get('state_dir','data/telegram-relay'))
    config_path=config_path if config_path.is_absolute() else base/config_path
    state_path=state_path if state_path.is_absolute() else base/state_path
    inbox = MainInbox(cfg, router,telegram=DesktopRelay(config_path,state_path))
    from .relay_authorization import RelayAuthorization
    butler=cfg.get('butler',{})
    inbox.relay_authorization=RelayAuthorization(butler.get('url',''),butler.get('token',''))
    inbox.delivery.package_authorizer=inbox.relay_authorization.allowed
    log.info("微信主窗口队列模式；监听范围：%s；连续消息合并=%s 秒，最长=%s 秒",
             "全部会话" if inbox.listen_all else "已绑定会话", inbox.worker.quiet, inbox.worker.max_wait)
    if not cfg["bot"].get("mention_names"):
        log.warning("[bot].mention_names 为空，无法识别 @机器人，群聊将按普通消息概率随机插话")
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
