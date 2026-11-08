"""Shared UI delivery scheduler; send details live in delivery_handlers."""
import json
import time

from .delivery_handlers import create_handlers
from .delivery_handlers.base import ActiveDelivery  # Public compatibility import.
from .delivery_handlers.text import reply_evidence, reply_is_visible
from .log import log
from .ui_contract import disposition, failure
from .wechat.chat_window import Message
from .queue_store import FAILURE_TIMEOUT_SECONDS, MAX_DELIVERY_RETRIES
from .voice.policy import resolve_queued_media_path


class DeliveryPump:
    def __init__(self, store, get_chat, capture_target, discover, *, timeout=5,
                 clock=time.time, monotonic=time.monotonic, capture_messages=None,
                 package_authorizer=None, voice_policy=None, tts_source=None, voice_policy_loader=None):
        self.store, self.get_chat = store, get_chat
        self.capture_target, self.discover = capture_target, discover
        self.timeout, self.clock, self.monotonic = timeout, clock, monotonic
        self.capture_messages = capture_messages
        self.package_authorizer = package_authorizer
        self.voice_policy = voice_policy
        self.voice_policy_loader = voice_policy_loader
        self.tts_source = tts_source
        self.handlers = create_handlers(self)
        self.voice_handler = self.handlers["voice"]
        self._closed = False
        self.active = None
        self._waiters = {}
        self._package_waiters = {}
        self._next_expiry=0

    @property
    def busy(self):
        return self.active is not None

    @property
    def requires_ui_review(self):
        return self.store.requires_image_ui_review()

    def enqueue(self, request):
        try:
            if getattr(request,'items',None) is not None:
                voice_bundle = getattr(request, 'kind', '') == 'voice_bundle'
                if voice_bundle and self.voice_handler.mode_for(request.contact) == 'off':
                    raise ValueError('请开启语音总开关和当前联系人的语音模式')
                enqueue = self.store.enqueue_voice_package if voice_bundle else self.store.enqueue_package
                package_id=enqueue(request.contact,request.items,request.request_id,
                                                      media_paths=request.media_paths,now=self.clock(),
                                                      received_at=getattr(request,'received_at',None))
                if voice_bundle:
                    request.package_id = package_id
                    request.persisted.set()
                self._package_waiters.setdefault(package_id,[]).append(request)
                self._notify_package(package_id)
                return package_id
            if getattr(request, 'kind', 'text') == 'voice':
                media = ''
                policy = self.voice_handler.current_policy()
                if policy is not None:
                    media = resolve_queued_media_path(policy)
                record_id = self.store.enqueue_voice(
                    request.contact, request.text, now=self.clock(), media_path=media,
                    received_at=getattr(request, 'received_at', None))
            else:
                record_id = self.store.enqueue_delivery(request.contact, request.text, now=self.clock(),
                                                       received_at=getattr(request,'received_at',None))
            self._waiters[record_id] = request
            log.info("[队列][%s][%s] 主动推送已持久化入发件箱", request.contact, record_id)
            return record_id
        except Exception as exc:
            request.finish(False, "发件入库失败")
            persisted = getattr(request, 'persisted', None)
            if persisted is not None:
                persisted.set()
            log.error("[队列] 发件入库失败: %s", type(exc).__name__)
            return None

    def _notify_package(self,package_id):
        receipt=self.store.package_receipt(package_id)
        if receipt['done']:
            for request in self._package_waiters.pop(package_id,[]):
                request.finish(receipt['ok'],receipt['state'])

    @staticmethod
    def _diagnostics(chat,phase,code):
        details=failure(code)
        details.update(phase=phase,enter_attempted=False)
        probe=getattr(chat,'send_diagnostics',None)
        if probe is not None:
            try:details.update(probe())
            except Exception:pass
        return details

    def _finish(self, delivery, state, error="",details=None):
        details=dict(details or {})
        handler = self.handler_for(delivery.kind)
        original_state = state
        if self.active is not None:
            details.update(handler.failure_details(self.active, state))
            details.update(getattr(self.active.typing,'failure_details',{}))
            details.setdefault('enter_attempted',self.active.typing.enter_attempted)
            close=getattr(self.active.typing,'close',None)
            if close is not None: close()
        state = handler.prepare_finish(delivery, state, details)
        if state in {'blocked','uncertain'}:
            # 代码给队列和看板看；重试语义由代码决定，不由状态反推。
            details.setdefault('error_code','ui_error')
            details.setdefault('retry',disposition(details['error_code']))
        self.store.finish_delivery(delivery.id, state, now=self.clock(), error=error,details=details)
        part=getattr(self.store,'stream_part',lambda _:None)(delivery.id)
        if part and state in {'blocked','uncertain'}:
            self.store.cancel_stream(delivery.batch_id,now=self.clock(),reason=error or '流式投递停止')
        if state in {'blocked','uncertain'}:
            row=self.store.get_delivery(delivery.id)
            log.error('[发送失败][%s][%s] 状态=%s 原因=%s 详情=%s 自动丢弃截止=%s',
                      delivery.contact,delivery.id,state,error,json.dumps(details,ensure_ascii=False),
                      '不自动重发，已退出阻塞，等待人工核对' if row.get('detached') else row['failed_at']+getattr(self.store,'failure_timeout_seconds',FAILURE_TIMEOUT_SECONDS))
        handler.after_finish(delivery, state, error, original_state)
        waiter = self._waiters.pop(delivery.id, None)
        if waiter is not None:
            waiter.finish(state == "sent", "sent" if state == "sent" else error or state)
        if getattr(delivery,'package_id',None):
            self._notify_package(delivery.package_id)
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
        self._closed = True
        for handler in self.handlers.values():
            handler.close()
        if self.active is not None:
            close = getattr(self.active.typing, 'close', None)
            if close is not None:
                close()

    def handler_for(self, kind):
        # Preserve the legacy fallback for old rows with unrecognized kinds.
        return self.handlers.get(kind, self.handlers['text'])

    def _start(self, delivery):
        try:
            authorization = self._package_authorization(delivery)
            if authorization is None:
                self.store.defer_delivery(delivery.id, now=self.clock())
            elif authorization is False:
                self._finish(delivery, 'skipped', '新闻订阅已撤销，图文包停止')
            else:
                self.handler_for(delivery.kind).start(delivery)
        except Exception as exc:
            self._finish(delivery, 'blocked', f'发送准备失败: {type(exc).__name__}',
                         self._diagnostics(None, 'prepare', 'ui_error'))

    def _package_authorization(self,delivery):
        if delivery.kind == 'voice' and getattr(delivery, 'package_id', None) and getattr(delivery, 'media_id', ''):
            # Authenticated speech packages are independent of news subscriptions.
            return self.voice_handler.mode_for(delivery.contact) != 'off'
        if not getattr(delivery,'package_id',None) or self.package_authorizer is None:
            return True
        try:
            answer=self.package_authorizer(delivery)
            return answer if answer is True or answer is False else None
        except Exception:
            return None

    def _cancel_revoked(self,active):
        task=active.typing
        pasted=(getattr(task,'_pasted',False) or getattr(task,'index',0)>0 or
                bool(getattr(task,'mention_verified',False)))
        if task.enter_attempted:
            self._finish(active.delivery,'uncertain','新闻订阅已撤销，已提交结果待核对，停止剩余图文包',
                         {'manual_required':pasted})
        elif pasted:
            self._finish(active.delivery,'blocked','新闻订阅已撤销，保留已输入内容，未提交发送',
                         {'manual_required':True})
        else:
            self._finish(active.delivery,'skipped','新闻订阅已撤销，图文包停止')

    def start_next(self):
        if self.busy or any(handler.preparing for handler in self.handlers.values()) or self._closed:
            return False
        self.expire_failures()
        delivery = self.store.claim_delivery(now=self.clock())
        if delivery is None:
            return False
        self._start(delivery)
        return True  # A blocked preparation still consumed one UI service turn.

    def tick(self, *, allow_start=True):
        if self._closed:
            return
        for record_id, request in list(self._waiters.items()):
            if self.store.get_delivery(record_id) is None:
                self._waiters.pop(record_id, None)
                request.finish(False, '消息已由用户删除，停止投递')
        for package_id in list(self._package_waiters):
            self._notify_package(package_id)
        self.expire_failures()
        if self.active is None:
            for handler in self.handlers.values():
                if handler.poll():
                    return
        if self.active is None:
            if allow_start:
                self.start_next()
            return
        active = self.active
        authorization=self._package_authorization(active.delivery)
        if authorization is None:
            if active.authorization_paused_at is None:
                active.authorization_paused_at=self.monotonic()
            return
        if authorization is False:
            self._cancel_revoked(active)
            return
        if active.authorization_paused_at is not None:
            resume=getattr(active.typing,'resume_after_authorization_pause',None)
            if resume is not None:
                resume(max(0,self.monotonic()-active.authorization_paused_at))
            if active.deadline is not None:
                active.deadline+=max(0,self.monotonic()-active.authorization_paused_at)
            active.authorization_paused_at=None
        row = self.store.get_delivery(active.delivery.id)
        handler = self.handler_for(active.delivery.kind)
        if not handler.sync_input(active, row):
            return
        if (active.delivery.batch_id and row['failed_at'] is not None
                and self.clock() >= row['failed_at'] + self.store.failure_timeout_seconds
                and not active.typing.enter_attempted):
            self._finish(active.delivery, 'blocked', '整轮失败等待期限已到，停止输入，未按回车')
            self.store.expire_failed_deliveries(now=self.clock())
            return
        state = active.typing.step()
        if self.active is None:
            return
        if state == "typing":
            return
        handler.complete(active, state)

    def reconcile(self):
        """重启后只核对已知不确定发件；不再输入，也不再按回车。"""
        self.expire_failures()
        for row in self.store.records("outbox"):
            # Image identities are per UI session. A restart cannot prove which
            # picture was ours from a text-only snapshot; leave it for review.
            if row['kind'] in {'image', 'voice'}:
                continue
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
