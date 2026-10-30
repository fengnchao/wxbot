"""Small receive-only Telethon adapter. Importing this module never logs in."""
import asyncio
from dataclasses import dataclass, field
from datetime import timezone
from getpass import getpass
from pathlib import Path

from butler.channels.telegram.formatting import Message


class FatalTelegramError(ValueError):
    """Authorization or source configuration requires operator intervention."""


@dataclass(frozen=True)
class Source:
    id: int
    username: str
    title: str
    entity: object = field(repr=False)


def fatal_error(exc):
    return isinstance(exc, FatalTelegramError) or type(exc).__name__ in {
        'AuthKeyUnregisteredError', 'SessionRevokedError', 'SessionExpiredError',
        'AuthKeyDuplicatedError', 'UserDeactivatedError', 'UserDeactivatedBanError',
        'ChannelPrivateError', 'UserNotParticipantError', 'UsernameInvalidError',
        'UsernameNotOccupiedError', 'AuthKeyNotFound',
    }


class TelegramSource:
    def __init__(self, config, *, factory=None):
        self.config, self.factory = config, factory
        self.client = None
        self.wake = asyncio.Event()
        self.sources = {}

    def _create(self, *, for_login=False):
        if self.client is not None:
            return
        if not self.config.api_id or not self.config.api_hash:
            raise FatalTelegramError('请先在本机配置自己的 Telegram api_id 和 api_hash')
        session = str(self.config.session_path)
        session_file = Path(session if session.endswith('.session') else session + '.session')
        if not self.factory and not for_login and not session_file.is_file():
            raise FatalTelegramError('尚未授权，请先运行 Telegram login 命令')
        if for_login:
            session_file.parent.mkdir(parents=True, exist_ok=True)
        factory = self.factory
        event = None
        if factory is None:
            try:
                from telethon import TelegramClient, events
            except ImportError:
                raise FatalTelegramError('缺少 Telegram 可选依赖，请按 TELEGRAM_NEWS.md 安装') from None
            factory = TelegramClient
            event = events.NewMessage(incoming=True)
        self.client = factory(session, self.config.api_id, self.config.api_hash,
            proxy=self.config.proxy, connection_retries=0, request_retries=0,
            flood_sleep_threshold=0, auto_reconnect=False, timeout=15)
        self.client.add_event_handler(self.on_message, event)

    async def connect(self):
        self._create()
        if not self.client.is_connected():
            self.sources.clear()
            async with asyncio.timeout(30):
                await self.client.connect()
        async with asyncio.timeout(30):
            if not await self.client.is_user_authorized():
                raise FatalTelegramError('Telegram 会话未授权或已失效，请在本机重新登录')

    async def account_id(self):
        async with asyncio.timeout(30):
            user = await self.client.get_me()
        if user is None or getattr(user, 'bot', False):
            raise FatalTelegramError('须使用已授权的个人 Telegram 账号')
        return user.id

    async def resolve(self, username):
        # Refresh even on a healthy connection: names and membership can change.
        async with asyncio.timeout(30):
            entity = await self.client.get_entity(username)
            if getattr(entity, 'left', True) or not (getattr(entity, 'broadcast', False) or getattr(entity, 'megagroup', False)):
                raise FatalTelegramError('来源须为当前账号已加入的频道或公开群')
            await self.client.get_permissions(entity, 'me')
            source_id = await self.client.get_peer_id(entity)
        source = Source(source_id, username, entity.title, entity)
        self.sources[username] = source
        return source

    async def latest(self, source):
        async with asyncio.timeout(30):
            items = await self.client.get_messages(source.entity, limit=1)
        return items[0].id if items else 0

    async def on_message(self, event):
        if event.chat_id in {source.id for source in self.sources.values()}:
            self.wake.set()

    async def after(self, source, cursor):
        iterator = self.client.iter_messages(source.entity, min_id=cursor, reverse=True, limit=None)
        page = []
        while True:
            try:
                async with asyncio.timeout(45):
                    item = await anext(iterator)
            except StopAsyncIteration:
                break
            text = getattr(item, 'raw_text', '') or ''
            if getattr(item, 'action', None) is not None:
                text = ''
            if text:
                for entity in getattr(item, 'entities', None) or []:
                    url = getattr(entity, 'url', None)
                    if isinstance(url, str) and url.startswith(('http://', 'https://')) and url not in text:
                        text += '\n' + url
            published = item.date
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            page.append(Message(source.id, item.id, text, published, source.title, source.username))
            if len(page) == 100:
                yield page, page[-1].message_id
                page = []
        if page:
            yield page, page[-1].message_id

    async def close(self):
        if self.client is not None:
            async with asyncio.timeout(10):
                await self.client.disconnect()


async def login(config, *, factory=None):
    source = TelegramSource(config, factory=factory)
    try:
        source._create(for_login=True)
        await source.client.start(
            phone=lambda: input('Telegram 手机号（含国家区号）：'),
            code_callback=lambda: getpass('Telegram 登录验证码（不回显）：'),
            password=lambda: getpass('Telegram 两步验证密码（不回显）：'))
        return {'status': 'authorized', 'account_id': await source.account_id()}
    finally:
        await source.close()
