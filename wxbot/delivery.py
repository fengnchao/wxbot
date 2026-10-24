"""UI 发件执行器：逐步输入、核对新增自己的气泡，保存确定/不确定结果。"""
from dataclasses import asdict, dataclass
import json
import time

from .log import log
from .state import overlap_end
from .wechat.chat_window import Message
from .queue_store import FAILURE_TIMEOUT_SECONDS, MAX_DELIVERY_RETRIES


def reply_is_visible(before, current, text):
    if before:
        end = overlap_end(before, current)
        if end is None:
            return False
        delta = current[end:]
    else:
        delta = current
    normalize = lambda value: value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return any(m.sender == "self" and normalize(m.text) == normalize(text) for m in delta)


@dataclass
class ActiveDelivery:
    delivery: object
    chat: object
    typing: object
    baseline: list
    deadline: float | None = None


class DeliveryPump:
    def __init__(self, store, get_chat, capture_target, discover, *, timeout=5,
                 clock=time.time, monotonic=time.monotonic, capture_messages=None):
        self.store, self.get_chat = store, get_chat
        self.capture_target, self.discover = capture_target, discover
        self.timeout, self.clock, self.monotonic = timeout, clock, monotonic
        self.capture_messages = capture_messages
        self.active = None
        self._waiters = {}
        self._next_expiry=0

    @property
    def busy(self):
        return self.active is not None

    def enqueue(self, request):
        try:
            record_id = self.store.enqueue_delivery(request.contact, request.text, now=self.clock())
            self._waiters[record_id] = request
            log.info("[队列][%s][%s] 主动推送已持久化入发件箱", request.contact, record_id)
            return record_id
        except Exception as exc:
            request.finish(False, "发件入库失败")
            log.error("[队列] 发件入库失败: %s", type(exc).__name__)
            return None

    @staticmethod
    def _diagnostics(chat,phase):
        details={'phase':phase,'enter_attempted':False}
        probe=getattr(chat,'send_diagnostics',None)
        if probe is not None:
            try:details.update(probe())
            except Exception:pass
        return details

    def _finish(self, delivery, state, error="",details=None):
        details=dict(details or {})
        if self.active is not None:
            details.update(getattr(self.active.typing,'failure_details',{}))
            details.setdefault('enter_attempted',self.active.typing.enter_attempted)
            close=getattr(self.active.typing,'close',None)
            if close is not None: close()
        self.store.finish_delivery(delivery.id, state, now=self.clock(), error=error,details=details)
        if state in {'blocked','uncertain'}:
            row=self.store.get_delivery(delivery.id)
            log.error('[发送失败][%s][%s] 状态=%s 原因=%s 详情=%s 自动丢弃截止=%s',
                      delivery.contact,delivery.id,state,error,json.dumps(details,ensure_ascii=False),
                      '不自动重发，已退出阻塞，等待人工核对' if row.get('detached') else row['failed_at']+getattr(self.store,'failure_timeout_seconds',FAILURE_TIMEOUT_SECONDS))
        waiter = self._waiters.pop(delivery.id, None)
        if waiter is not None:
            waiter.finish(state == "sent", "sent" if state == "sent" else error or state)
        log.info("[队列][%s][%s][%d/%d] 发送状态=%s %s", delivery.contact, delivery.id,
                 delivery.part_seq, delivery.part_count, state, error)
        if delivery.batch_id:
            batch = self.store.get_batch(delivery.batch_id)
            if batch and batch['state'] == 'done':
                log.info('[队列][%s][%s] 整轮结束', delivery.contact, delivery.batch_id)
        self.active = None

    def expire_failures(self):
        if self.monotonic()<self._next_expiry:
            return
        self._next_expiry=self.monotonic()+1
        for row in self.store.retry_failed_deliveries(now=self.clock()):
            log.warning('[发送自动重试][%s][%s] 第%s/%s次 原失败原因=%s；已重新入队',
                        row['contact'],row['id'],row['retries'],
                        getattr(self.store,'max_delivery_retries',MAX_DELIVERY_RETRIES),row['error'])
        for row in self.store.expire_failed_deliveries(now=self.clock()):
            log.warning('[发送超时丢弃][%s][%s] 首次失败=%s 等待上限=%s秒 原因=%s；后续队列已释放',
                        row['contact'],row['id'],row['failed_at'],
                        getattr(self.store,'failure_timeout_seconds',FAILURE_TIMEOUT_SECONDS),row['error'])
            waiter=self._waiters.pop(row['id'],None)
            if waiter is not None:waiter.finish(False,row['error'])

    def close(self):
        if self.active is not None:
            close=getattr(self.active.typing,'close',None)
            if close is not None: close()

    def _start(self, delivery):
        chat=None
        try:
            if delivery.kind == "emoji":
                self._start_emoji(delivery)
                return
            self.discover()  # 点击前持久化未读数量。
            chat = self.get_chat(delivery.contact)
            if delivery.group_mode is not None:
                chat.expected_group = delivery.group_mode
            if not self.capture_target(delivery.contact):
                self._finish(delivery, "blocked", "目标会话尚不可用，未键入",self._diagnostics(chat,'prepare_target'))
                return
            baseline = chat.read_messages()
            self.store.save_baseline(delivery.id, [asdict(m) for m in baseline])
            draft = self.store.owned_draft(delivery.contact)
            if draft is not None and hasattr(chat, 'clear_owned_draft'):
                if not chat.clear_owned_draft(draft):
                    self._finish(delivery, 'blocked', '草稿与已核验的机器人输入不匹配，请人工清理后重试',
                                 {'phase':'draft_cleanup','manual_required':getattr(chat,'draft_conflict',False)})
                    return
                self.store.forget_draft(delivery.contact)
            typing = chat.start_send(delivery.text, clock=self.monotonic)
            if typing is None:
                self._finish(delivery, "blocked", "输入框有草稿或无法读取、对象无法确认或窗口不可用",
                             {**self._diagnostics(chat,'prepare_input'), 'manual_required':getattr(chat,'draft_conflict',False)})
                return
            active = ActiveDelivery(delivery, chat, typing, baseline)
            typing.on_verified_draft = lambda text: self.store.save_draft(delivery.id, text)
            typing.before_enter = lambda: self._prepare_enter(active)
            self.active = active
            log.info("[队列][%s][%s][%d/%d] 开始分批粘贴（每%d字/%g秒）", delivery.contact, delivery.id,
                     delivery.part_seq, delivery.part_count,
                     getattr(typing,'chunk_size',5),getattr(typing,'chunk_interval',.5))
        except Exception as exc:
            self._finish(delivery, "blocked", f"发送准备失败: {type(exc).__name__}",self._diagnostics(chat,'prepare'))

    def _start_emoji(self, delivery):
        chat = None
        try:
            self.discover()
            chat = self.get_chat(delivery.contact)
            if delivery.group_mode is not None:
                chat.expected_group = delivery.group_mode
            if not self.capture_target(delivery.contact):
                self._finish(delivery, "blocked", "目标会话尚不可用，未发送表情",
                             self._diagnostics(chat, 'prepare_target'))
                return
            status = chat.send_sticker(clock=self.monotonic, timeout=self.timeout)
            if status == "sent":
                self._finish(delivery, "sent")
            elif status == "uncertain":
                self._finish(delivery, "uncertain", "表情已点击但未确认发送，不自动重发",
                             self._diagnostics(chat, 'sticker'))
            else:
                self._finish(delivery, "blocked", "表情发送失败或控件未校准",
                             self._diagnostics(chat, 'sticker'))
        except Exception as exc:
            self._finish(delivery, "blocked", f"表情发送失败: {type(exc).__name__}",
                         self._diagnostics(chat, 'sticker'))

    def _prepare_enter(self, active):
        if not active.chat.target_is_current(active.typing.win):
            raise RuntimeError("回车前目标会话变化")
        current = active.chat.read_from_window(active.typing.win, strict_sender=True)
        if self.capture_messages is not None:
            self.capture_messages(active.delivery.contact, active.chat, current)
        text = getattr(active.typing, "submitted_text", None) or active.delivery.text
        self.store.save_baseline(active.delivery.id, [asdict(m) for m in current], submitted_text=text)
        active.baseline = current

    def start_next(self):
        if self.busy:
            return False
        self.expire_failures()
        delivery = self.store.claim_delivery(now=self.clock())
        if delivery is None:
            return False
        self._start(delivery)
        return True  # A blocked preparation still consumed one UI service turn.

    def tick(self, *, allow_start=True):
        self.expire_failures()
        if self.active is None:
            if allow_start:
                self.start_next()
            return
        active = self.active
        row = self.store.get_delivery(active.delivery.id)
        if (active.delivery.batch_id and row['failed_at'] is not None
                and self.clock() >= row['failed_at'] + self.store.failure_timeout_seconds
                and not active.typing.enter_attempted):
            self._finish(active.delivery, 'blocked', '整轮失败等待期限已到，停止输入，未按回车')
            self.store.expire_failed_deliveries(now=self.clock())
            return
        state = active.typing.step()
        if state == "typing":
            return
        if not active.typing.enter_attempted:
            self._finish(active.delivery, "blocked", active.typing.error)
            return
        if active.deadline is None:
            self.store.confirming(active.delivery.id, now=self.clock())
            log.info('[队列][%s][%s][%d/%d] 已回车，等待发送确认', active.delivery.contact,
                     active.delivery.id, active.delivery.part_seq, active.delivery.part_count)
            active.deadline = self.monotonic() + self.timeout
        try:
            if active.chat.target_is_current(active.typing.win):
                current = active.chat.read_from_window(active.typing.win, strict_sender=True)
                text = getattr(active.typing, "submitted_text", None) or active.delivery.text
                if reply_is_visible(active.baseline, current, text):
                    # Persist the same snapshot that proved the bubble is ours.
                    # Capture concurrent incoming messages before advancing the
                    # anchor; assigning the snapshot alone would lose them.
                    if self.capture_messages is not None:
                        self.capture_messages(active.delivery.contact, active.chat, current)
                        log.info('[收件防回流][%s][%s] 已同步发送确认快照；自己的气泡不入收件队列',
                                 active.delivery.contact, active.delivery.id)
                    active.chat.remember_sent(active.delivery.text)
                    self._finish(active.delivery, "sent")
                    return
        except Exception as exc:
            log.debug("[队列][%s] 发送确认暂时不可读: %s", active.delivery.id, type(exc).__name__)
        if self.monotonic() >= active.deadline:
            self._finish(active.delivery, "uncertain", "已尝试回车，但未确认新发送气泡，不自动重发")

    def reconcile(self):
        """重启后只核对已知不确定发件；不再输入，也不再按回车。"""
        self.expire_failures()
        for row in self.store.records("outbox"):
            if row["state"] != "uncertain" or row["baseline"] is None or (row.get('detached') and row['batch_id']):
                continue
            try:
                self.discover()
                if not self.capture_target(row["contact"]):
                    continue
                chat = self.get_chat(row["contact"])
                before = [Message(**item) for item in json.loads(row["baseline"])]
                if reply_is_visible(before, chat.read_messages(strict_sender=True), row["submitted_text"] or row["text"]):
                    self.store.finish_delivery(row["id"], "sent", now=self.clock())
                    chat.remember_sent(row["text"])
                    log.info("[队列][%s][%s] 恢复核对：已确认发送", row["contact"], row["id"])
                else:
                    log.warning("[队列][%s][%s] 发送仍无法确认，保留 uncertain 等待人工核对",
                                row["contact"], row["id"])
            except Exception as exc:
                log.warning("[队列][%s] 恢复核对失败: %s", row["id"], type(exc).__name__)
