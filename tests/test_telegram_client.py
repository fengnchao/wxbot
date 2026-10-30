import asyncio
from types import SimpleNamespace

import pytest

from telegram_fakes import FakeClient, config, raw


def test_unauthorized_run_does_not_prompt_or_start_login(tmp_path):
    from butler.channels.telegram.client import TelegramSource, FatalTelegramError
    fake = FakeClient()
    fake.authorized = False
    async def scenario():
        source = TelegramSource(config(tmp_path), factory=lambda *a, **kw: fake)
        with pytest.raises(FatalTelegramError):
            await source.connect()
        assert fake.start_calls == 0
        await source.close()
    asyncio.run(scenario())


def test_login_only_authorizes_and_disconnects(tmp_path):
    from butler.channels.telegram.client import login
    fake = FakeClient()
    fake.authorized = False
    asyncio.run(login(config(tmp_path), factory=lambda *a, **kw: fake))
    assert fake.start_calls == 1
    assert not fake.connected
    assert fake.scans == []


def test_scan_is_ascending_preserves_captions_and_embedded_links(tmp_path):
    from butler.channels.telegram.client import TelegramSource
    fake = FakeClient()
    fake.items = [raw(12, ''), raw(11, '图片说明', entities=[SimpleNamespace(url='https://example.com/hidden')])]
    async def scenario():
        source = TelegramSource(config(tmp_path), factory=lambda *a, **kw: fake)
        await source.connect()
        entity = await source.resolve('zaobaosg')
        pages = [page async for page in source.after(entity, 10)]
        assert pages[0][1] == 12
        assert [m.message_id for m in pages[0][0]] == [11, 12]
        assert '图片说明' in pages[0][0][0].text
        assert 'https://example.com/hidden' in pages[0][0][0].text
        assert pages[0][0][1].text == ''
        assert fake.scans == [(10, True)]
        await source.close()
    asyncio.run(scenario())


def test_unjoined_or_non_channel_source_is_rejected(tmp_path):
    from butler.channels.telegram.client import TelegramSource, FatalTelegramError
    async def scenario():
        for attr in ('left', 'broadcast'):
            fake = FakeClient()
            setattr(fake.entity, attr, attr == 'left')
            source = TelegramSource(config(tmp_path), factory=lambda *a, **kw: fake)
            await source.connect()
            with pytest.raises(FatalTelegramError):
                await source.resolve('zaobaosg')
            await source.close()
    asyncio.run(scenario())


def test_new_message_only_wakes_allowed_source_without_history_calls(tmp_path):
    from butler.channels.telegram.client import TelegramSource
    async def scenario():
        fake = FakeClient()
        source = TelegramSource(config(tmp_path), factory=lambda *a, **kw: fake)
        await source.connect()
        await source.resolve('zaobaosg')
        await source.on_message(SimpleNamespace(chat_id=-100456))
        assert not source.wake.is_set()
        await source.on_message(SimpleNamespace(chat_id=-100123))
        assert source.wake.is_set()
        assert fake.scans == []
        assert await source.account_id() == 9
        await source.close()
    asyncio.run(scenario())


def test_page_boundary_is_not_the_live_event_id(tmp_path):
    from butler.channels.telegram.client import TelegramSource
    async def scenario():
        fake = FakeClient()
        fake.items = [raw(i) for i in range(1, 206)]
        source = TelegramSource(config(tmp_path), factory=lambda *a, **kw: fake)
        await source.connect()
        entity = await source.resolve('zaobaosg')
        pages = [p async for p in source.after(entity, 0)]
        assert [cursor for _, cursor in pages] == [100, 200, 205]
        assert [len(items) for items, _ in pages] == [100, 100, 5]
        await source.close()
    asyncio.run(scenario())
