"""有界模型请求线程：只接触普通消息数据，绝不操作微信 UI。"""
import random
import threading
import time
from contextlib import nullcontext

from common.flow_trace import record

from .log import log
from .config import validate_model_concurrency


class ModelWorker:
    def __init__(self, store, router, *, quiet=3, max_wait=10, prefix="/",
                 reply_delay_min=0, reply_delay_max=0, clock=time.time, max_concurrency=2, trace=None):
        validate_model_concurrency(max_concurrency)
        self.max_concurrency = max_concurrency
        self.store, self.router = store, router
        self.quiet, self.max_wait, self.prefix = quiet, max_wait, prefix
        self.delay_min, self.delay_max = reply_delay_min, reply_delay_max
        self.clock = clock
        self.trace = trace
        self._stop = threading.Event()
        self._threads = []
        self._claims = threading.Lock()

    def process_once(self):
        with self._claims:
            if self._stop.is_set():
                return False
            now = self.clock()
            self._recover(now)
            count = self.store.prepare(quiet=self.quiet, max_wait=self.max_wait, prefix=self.prefix, now=now)
            if count:
                log.info("[队列] %d 个合并批次就绪，等待提交", count)
            if self._stop.is_set():
                return False
            batch = self.store.claim_batch(now=now)
            if self._stop.is_set() and batch is not None:
                self.store.release_unsubmitted_batch(batch.id)
                return False
        if batch is None:
            return False
        log.info("[队列][%s][%s] 模型线程已领取，准备请求后端；接收结果见流转记录", batch.contact, batch.id)
        with self.trace.bind(batch.contact,batch.id) if self.trace else nullcontext():
            started = time.monotonic()
            record('wxbot_model','started')
            record('wxbot_reply_mode', batch.reply_mode or 'text')
            try:
                # 所有批次都调用模型：群消息即使静默/发图也已进入该成员的会话上下文。
                reply = self.router.handle_reply(batch.contact, batch.text, context=batch.context, request_id=batch.id,
                                                 member_key=batch.member_key, member_name=batch.member_name)
                mode = batch.reply_mode or 'text'
                if mode == 'emoji':
                    # 丢弃模型文字，改为发一张表情图。
                    self.store.finish_batch_parts(batch.id, (), now=self.clock())
                    self.store.enqueue_sticker(batch.contact, now=self.clock())
                    record('wxbot_result','ok',part_count=0,characters=0,
                           elapsed_ms=round((time.monotonic()-started)*1000))
                    log.info("[队列][%s][%s] 本批次回复方式=表情图，已入表情发送队列", batch.contact, batch.id)
                elif mode == 'none':
                    # 已进上下文，但不发送任何回复。
                    self.store.finish_batch_parts(batch.id, (), now=self.clock())
                    record('wxbot_result','ok',part_count=0,characters=0,
                           elapsed_ms=round((time.monotonic()-started)*1000))
                    log.info("[队列][%s][%s] 本批次静默（已进上下文，不回复）", batch.contact, batch.id)
                else:
                    self.store.finish_batch_parts(batch.id, reply.parts, reply_text=reply.text, now=self.clock(),
                                                  delay=random.uniform(self.delay_min, self.delay_max))
                    record('wxbot_result','ok',part_count=len(reply.parts),characters=len(reply.text or ''),
                           elapsed_ms=round((time.monotonic()-started)*1000))
                    log.info("[队列][%s][%s] %s", batch.contact, batch.id,
                             f"完整回复已入发件箱，共 {len(reply.parts)} 句" if reply.parts else "本批次无需回复")
            except Exception as exc:
                record('wxbot_result','error',error_type=type(exc).__name__,
                       elapsed_ms=round((time.monotonic()-started)*1000))
                safe=getattr(exc,'retry_safe',False) is True
                self.store.fail_batch(batch.id,f"{type(exc).__name__}: {exc}",now=self.clock(),retry_safe=safe)
                log.error("[队列][%s][%s] 模型失败；%s；最长阻塞%g秒：%s",
                          batch.contact,batch.id,'尚未提交，稍后自动重试' if safe else '结果未知，不重放本条',
                          self.store.failure_timeout_seconds,str(exc))
        return True

    def _recover(self,now):
        for event in self.store.recover_model_failures(now=now):
            log.warning('[队列][%s][%s] %s：%s',event['contact'],event['id'],
                        '模型自动重试' if event['action']=='model_retry' else '模型失败已结束',event['reason'])

    def _maintain(self):
        # Expiry must keep running when every model worker is in network I/O.
        # Never time out/replay a currently running request here.
        while not self._stop.is_set():
            try:self._recover(self.clock())
            except Exception as exc:log.error('[队列] 失败任务清理异常: %s',type(exc).__name__)
            self._stop.wait(.2)

    def _run(self):
        while not self._stop.is_set():
            try:
                worked = self.process_once()
            except Exception as exc:
                log.error("[队列] 后台处理异常: %s", type(exc).__name__)
                worked = False
            self._stop.wait(0.01 if worked else 0.1)

    def start(self):
        if not self._threads and not self._stop.is_set():
            self._threads = [threading.Thread(target=self._run, name=f"wxbot-model-{n}", daemon=True)
                             for n in range(self.max_concurrency)]
            self._threads.append(threading.Thread(target=self._maintain,name='wxbot-model-maintenance',daemon=True))
            for thread in self._threads:
                thread.start()

    def stop(self, timeout=1):
        deadline = time.monotonic() + max(0, timeout)
        self._stop.set()  # Never wait for SQLite/claim locks to signal shutdown.
        for thread in self._threads:
            thread.join(max(0, deadline-time.monotonic()))
        return not any(thread.is_alive() for thread in self._threads)
