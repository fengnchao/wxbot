"""Image preview sending and image-specific confirmation/manual review."""
from .bubble import BubbleDeliveryHandler


class ImageDeliveryHandler(BubbleDeliveryHandler):
    def create_input(self, chat, delivery):
        return chat.start_image(delivery.media_path, clock=self.pump.monotonic)

    def confirmation(self, active, current, text):
        return active.typing.confirmation_visible(), None, None

    def failure_details(self, active, state):
        if state != 'sent' and getattr(active.typing, '_pasted', False):
            return {'manual_required': True}
        return {}
