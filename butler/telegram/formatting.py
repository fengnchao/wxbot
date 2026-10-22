"""Plain-text relay messages, without model calls or media downloads."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

CST = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class Message:
    source_id: int
    message_id: int
    text: str
    published_at: datetime
    source_name: str
    source_username: str

    def __post_init__(self):
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError('消息时间必须带时区')
        if type(self.message_id) is not int or self.message_id <= 0:
            raise ValueError('消息 ID 无效')


def parts(message, *, limit=500):
    if not message.text.strip():
        return []
    link = f'https://t.me/{message.source_username}/{message.message_id}'
    header = f'Telegram｜{message.source_name}\n{message.published_at.astimezone(CST):%Y-%m-%d %H:%M} 北京时间'
    # Reserve space for segment numbers; an indivisible URL may exceed the target.
    budget = max(20, limit - len(header) - len(link) - 24)
    tokens = re.split(r'(https?://[^\s]+)', message.text)
    bodies, current = [], ''
    for token in tokens:
        if not token:
            continue
        if token.startswith(('https://', 'http://')):
            if current and len(current) + len(token) > budget:
                bodies.append(current)
                current = ''
            current += token
            continue
        while token:
            room = budget - len(current)
            if room <= 0:
                bodies.append(current)
                current = ''
                room = budget
            piece, token = token[:room], token[room:]
            current += piece
    if current:
        bodies.append(current)
    return [f'{header}' + (f'（{i}/{len(bodies)}）' if len(bodies) > 1 else '')
            + f'\n\n{body}\n\n{link}' for i, body in enumerate(bodies, 1)]
