"""Sticker sending and its existing immediate receipt semantics."""
from .base import DeliveryHandler


class EmojiDeliveryHandler(DeliveryHandler):
    def start(self, delivery):
        pump = self.pump
        chat = None
        try:
            pump.discover()
            chat = pump.get_chat(delivery.contact)
            if delivery.group_mode is not None:
                chat.expected_group = delivery.group_mode
            if not pump.capture_target(delivery.contact):
                pump._finish(delivery, "blocked", "目标会话尚不可用，未发送表情",
                             pump._diagnostics(chat, 'prepare_target', 'target_unavailable'))
                return
            status = chat.send_sticker(clock=pump.monotonic, timeout=pump.timeout)
            if status == "sent":
                pump._finish(delivery, "sent")
            elif status == "uncertain":
                pump._finish(delivery, "uncertain", "表情已点击但未确认发送，不自动重发",
                             pump._diagnostics(chat, 'sticker', 'sticker_unconfirmed'))
            else:
                pump._finish(delivery, "blocked", "表情发送失败或控件未校准",
                             pump._diagnostics(chat, 'sticker', 'sticker_unavailable'))
        except Exception as exc:
            pump._finish(delivery, "blocked", f"表情发送失败: {type(exc).__name__}",
                         pump._diagnostics(chat, 'sticker', 'ui_error'))
