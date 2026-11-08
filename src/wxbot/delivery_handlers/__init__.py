"""Send handlers selected only after the shared outbox claims a delivery."""
from .emoji import EmojiDeliveryHandler
from .image import ImageDeliveryHandler
from .text import TextDeliveryHandler
from .voice import VoiceDeliveryHandler


def create_handlers(pump):
    return {
        'text': TextDeliveryHandler(pump),
        'voice': VoiceDeliveryHandler(pump),
        'image': ImageDeliveryHandler(pump),
        'emoji': EmojiDeliveryHandler(pump),
    }
