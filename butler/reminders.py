"""Durable reminder dispatch owned by Butler, independent of agent availability."""
import threading


class ReminderScheduler:
    def __init__(self,butler):
        self.butler=butler
        self.stop_event=threading.Event()
        self.thread=None

    def tick(self,now=None):
        for _ in range(20):
            if self.stop_event.is_set():
                break
            # Leave later reminders cancellable while the current delivery waits.
            items=self.butler.store.claim_due(now,limit=1)
            if not items:
                break
            item=items[0]
            try:
                result=self.butler.push(item['contact'],item['text'])
                ok=bool(result.meta.get('ok'))
                detail=result.meta.get('detail','')
            except Exception as exc:
                ok=False; detail=type(exc).__name__
            self.butler.store.finish_reminder(item['id'],ok,detail,now)
            self.butler.store.event(item['contact'],'reminder_delivery','ok' if ok else 'failed',
                                    reminder_id=item['id'],delivery_id=item['delivery_id'])

    def start(self):
        self.butler.store.recover_deliveries()
        def run():
            while not self.stop_event.is_set():
                try:
                    self.tick()
                except Exception as exc:
                    self.butler.log('提醒调度异常: %s',type(exc).__name__)
                self.stop_event.wait(1)
        self.thread=threading.Thread(target=run,daemon=True,name='butler-reminders')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
