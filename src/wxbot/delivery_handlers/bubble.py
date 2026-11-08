"""Common guarded UI preparation and bubble confirmation for text and images."""
from .base import ActiveDelivery, DeliveryHandler
from ..log import log
from ..ui_contract import persisted_rows


class BubbleDeliveryHandler(DeliveryHandler):
    def create_input(self, chat, delivery):
        raise NotImplementedError

    def configure_input(self, delivery, typing):
        return True

    def confirmation(self, active, current, text):
        raise NotImplementedError

    def remember_sent(self, active, text):
        pass

    def start(self, delivery):
        pump = self.pump
        chat=None
        try:
            pump.discover()  # 点击前持久化未读数量。
            chat = pump.get_chat(delivery.contact)
            if delivery.group_mode is not None:
                chat.expected_group = delivery.group_mode
            if not pump.capture_target(delivery.contact):
                pump._finish(delivery, "blocked", "目标会话尚不可用，未键入",
                             pump._diagnostics(chat,'prepare_target','target_unavailable'))
                return
            baseline = chat.read_messages()
            pump.store.save_baseline(delivery.id, persisted_rows(baseline))
            draft = pump.store.owned_draft(delivery.contact)
            if draft is not None and hasattr(chat, 'clear_owned_draft'):
                if not chat.clear_owned_draft(draft):
                    details=pump._diagnostics(chat,'draft_cleanup','draft_conflict')
                    details['manual_required']=getattr(chat,'draft_conflict',False)
                    pump._finish(delivery, 'blocked', '草稿与已核验的机器人输入不匹配，请人工清理后重试',
                                 details)
                    return
                pump.store.forget_draft(delivery.contact)
            typing = self.create_input(chat, delivery)
            if typing is None:
                code='draft_conflict' if getattr(chat,'draft_conflict',False) else 'target_unavailable'
                details=pump._diagnostics(chat,'prepare_input',code)
                details['manual_required']=getattr(chat,'draft_conflict',False)
                pump._finish(delivery, "blocked", "输入框有草稿或无法读取、对象无法确认或窗口不可用", details)
                return
            if not self.configure_input(delivery, typing):
                return
            active = ActiveDelivery(delivery, chat, typing, baseline)
            typing.on_verified_draft = lambda text: pump.store.save_draft(delivery.id, text)
            typing.before_enter = lambda: self.before_enter(active)
            pump.active = active
            log.info("[队列][%s][%s][%d/%d] 开始分批粘贴（每%d字/%g秒）", delivery.contact, delivery.id,
                     delivery.part_seq, delivery.part_count,
                     getattr(typing,'chunk_size',5),getattr(typing,'chunk_interval',.5))
        except Exception as exc:
            pump._finish(delivery, "blocked", f"发送准备失败: {type(exc).__name__}",
                         pump._diagnostics(chat,'prepare','ui_error'))

    def before_enter(self, active):
        pump = self.pump
        if not active.chat.target_is_current(active.typing.win):
            raise RuntimeError("回车前目标会话变化")
        current = active.chat.read_from_window(active.typing.win, strict_sender=True)
        if pump.capture_messages is not None:
            pump.capture_messages(active.delivery.contact, active.chat, current)
        text = getattr(active.typing, "submitted_text", None) or active.delivery.text
        pump.store.save_baseline(active.delivery.id, persisted_rows(current), submitted_text=text)
        active.baseline = current
        # UIA reads may be slow: check freshness after the final snapshot, as
        # close as possible to the caller's guarded native submit operation.
        authorization=pump._package_authorization(active.delivery)
        if authorization is None:
            if active.authorization_paused_at is None:
                active.authorization_paused_at=pump.monotonic()
            return False
        if authorization is False:
            pump._cancel_revoked(active)
            return False

    def complete(self, active, state):
        pump = self.pump
        if not active.typing.enter_attempted:
            pump._finish(active.delivery, "blocked", active.typing.error)
            return
        if active.deadline is None:
            pump.store.confirming(active.delivery.id, now=pump.clock())
            log.info('[队列][%s][%s][%d/%d] 已回车，等待发送确认', active.delivery.contact,
                     active.delivery.id, active.delivery.part_seq, active.delivery.part_count)
            active.deadline = pump.monotonic() + pump.timeout
        try:
            if active.chat.target_is_current(active.typing.win):
                current = active.chat.read_from_window(active.typing.win, strict_sender=True)
                text = getattr(active.typing, "submitted_text", None) or active.delivery.text
                visible, evidence, by_ref = self.confirmation(active, current, text)
                if visible:
                    # Persist the same snapshot that proved the bubble is ours.
                    # Capture concurrent incoming messages before advancing the
                    # anchor; assigning the snapshot alone would lose them.
                    if pump.capture_messages is not None:
                        pump.capture_messages(active.delivery.contact, active.chat, current)
                        log.info('[收件防回流][%s][%s] 已同步发送确认快照；自己的气泡不入收件队列',
                                 active.delivery.contact, active.delivery.id)
                    self.remember_sent(active, text)
                    details={'mention_verified': getattr(active.typing, 'mention_verified', False),
                             'bubble_verified': True}
                    if evidence is not None:
                        details.update(confirm_evidence=evidence, ref_available=by_ref)
                    pump._finish(active.delivery, "sent", details=details)
                    return
        except Exception as exc:
            log.debug("[队列][%s] 发送确认暂时不可读: %s", active.delivery.id, type(exc).__name__)
        if pump.monotonic() >= active.deadline:
            pump._finish(active.delivery, "uncertain", "已尝试回车，但未确认新发送气泡，不自动重发",
                         pump._diagnostics(active.chat, 'confirm', 'enter_unconfirmed'))
