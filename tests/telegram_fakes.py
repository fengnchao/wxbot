"""External Telegram and Butler doubles; storage/service code stays real."""
from datetime import datetime, timezone
from types import SimpleNamespace


def raw(number, text='原文', *, entities=None):
    return SimpleNamespace(id=number, raw_text=text, date=datetime(2026, 10, 22, tzinfo=timezone.utc),
                           entities=entities or [], action=None, media=None)


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.authorized = True
        self.connected = False
        self.entity = SimpleNamespace(id=123, title='zaobao.sg 早报', username='zaobaosg', left=False, broadcast=True, megagroup=False)
        self.items = [raw(10)]
        self.me = SimpleNamespace(id=9, bot=False)
        self.start_calls = 0
        self.scans = []
        self.handlers = []
    async def connect(self):
        self.connected = True
    def is_connected(self):
        return self.connected
    async def disconnect(self):
        self.connected = False
    async def is_user_authorized(self):
        return self.authorized
    async def get_me(self):
        return self.me
    async def get_entity(self, username):
        return self.entity
    async def get_peer_id(self, entity):
        return -100123 if entity.id == 123 else -100456
    async def get_permissions(self, entity, who):
        if entity.left:
            raise ValueError('not joined')
        return SimpleNamespace(is_banned=False)
    async def get_messages(self, entity, limit):
        return self.items[-limit:]
    def add_event_handler(self, callback, *args):
        self.handlers.append(callback)
    async def start(self, **kwargs):
        self.start_calls += 1
        self.authorized = True
    async def iter_messages(self, entity, *, min_id, reverse, **kwargs):
        self.scans.append((min_id, reverse))
        for item in sorted(self.items, key=lambda x: x.id):
            if item.id > min_id:
                yield item
    async def send_message(self, *args, **kwargs):
        raise AssertionError('reception must not send Telegram messages')


def config(tmp_path, enabled=True):
    from butler.telegram.config import TelegramConfig
    return TelegramConfig(enabled, ('zaobaosg',), tmp_path/'session/account', tmp_path/'state',
                          tmp_path/'config.butler.toml', 123, 'local-test-secret', None, 1)
