"""Text input, stream sealing and self-bubble evidence."""
from .bubble import BubbleDeliveryHandler
from ..log import log
from ..ui_contract import Snapshot


def reply_evidence(before, current, text):
    """发送确认的证据：(证据类型, 行, 引用是否可用)。

    'ref' 表示出现了 baseline 中没有、方向为自己的新行；'text' 是拿不到引用时的
    显式降级。两种证据都不成立才算未确认。
    """
    previous, now = Snapshot.take(before), Snapshot.take(current)
    evidence, row = now.sent_after(previous, text)
    return evidence, row, now.evidence_available(previous)


def reply_is_visible(before, current, text):
    return reply_evidence(before, current, text)[0] is not None


class TextDeliveryHandler(BubbleDeliveryHandler):
    def create_input(self, chat, delivery):
        mention_name = getattr(delivery, 'mention_name', '')
        if mention_name:
            return chat.start_send(delivery.text, mention_name=mention_name, clock=self.pump.monotonic)
        return chat.start_send(delivery.text, clock=self.pump.monotonic)

    def confirmation(self, active, current, text):
        evidence, _, by_ref = reply_evidence(active.baseline, current, text)
        return evidence is not None, evidence, by_ref

    def remember_sent(self, active, text):
        active.chat.remember_sent(text)

    def configure_input(self, delivery, typing):
        pump = self.pump
        stream_part=getattr(pump.store,'stream_part',lambda _:None)(delivery.id)
        if stream_part:
            if not hasattr(typing,'update_stream'):
                close=getattr(typing,'close',None)
                if stream_part['status']!='complete':
                    if close is not None: close()
                    pump.store.defer_stream_window(delivery.id,now=pump.clock())
                    log.info('[队列][%s] 窗口不支持流式输入，等待完整回复后发送',delivery.id)
                    return False
                # Completed immutable snapshot: legacy windows use their
                # existing buffered send path; never type an unsealed part.
            else:
                typing.update_stream(stream_part['text'],sealed=stream_part['sealed'])
                typing.enter_gate=lambda: pump.store.stream_enter_gate(
                    delivery.id,typing.text,getattr(typing,'stream_version',None))
                typing.stream_version=stream_part['version']
        elif (getattr(pump.store,'delivery_typing_mode',lambda _:'chunked')(delivery.batch_id)=='full'
                and hasattr(typing,'full_paste')):
            typing.full_paste()
        return True

    def sync_input(self, active, row):
        pump = self.pump
        part=getattr(pump.store,'stream_part',lambda _:None)(active.delivery.id)
        if part and not active.typing.enter_attempted:
            if part['status']=='cancelled' or row['state']=='skipped':
                # Clear exclusively the exact UI-readback prefix we own.
                draft=row.get('draft_text')
                cleared=False
                if draft and hasattr(active.chat,'clear_owned_draft'):
                    try: cleared=active.chat.clear_owned_draft(draft)
                    except Exception: pass
                if cleared:
                    pump.store.forget_draft(active.delivery.contact)
                    pump.store.stream_draft_cleaned(active.delivery.id)
                elif draft or getattr(active.typing,'_entered_length',0) or getattr(active.typing,'index',0):
                    pump.store.stream_draft_review(active.delivery.id)
                pump._finish(active.delivery,'skipped','流式回复已停止',{'manual_required':bool(draft and not cleared)})
                return False
            if hasattr(active.typing,'update_stream'):
                active.typing.update_stream(part['text'],sealed=part['sealed'])
                active.typing.stream_version=part['version']
        return True
