import asyncio
import json
import threading
from types import SimpleNamespace

import pytest

from telegram_fakes import FakeClient, config, raw


def setup_relay(tmp_path, push=None, fake=None):
    from butler.channels.telegram.client import TelegramSource
    from butler.channels.telegram.store import Store
    from butler.channels.telegram.service import Relay
    cfg = config(tmp_path)
    group = tmp_path / 'groups.json'
    group.write_text(json.dumps({'groups': {'1': ['A', 'B']}}), encoding='utf-8')
    bc = SimpleNamespace(group_file_path=lambda: str(group))
    fake = fake or FakeClient()
    source = TelegramSource(cfg, factory=lambda *a, **kw: fake)
    store = Store(cfg.state_path / 'relay.sqlite3')
    calls = []
    def send(*args):
        calls.append(args[1:])
        return push(*args) if push else {'state': 'sent', 'reason': 'confirmed'}
    return Relay(cfg, bc, store, source, push=send), fake, calls, group


def test_initial_baseline_then_new_text_fanout_and_repeat_scan(tmp_path):
    async def scenario():
        relay, fake, calls, _ = setup_relay(tmp_path)
        await relay.scan_once()
        assert relay.store.cursor(-100123) == 10
        assert not relay.deliver_once()
        fake.items += [raw(11, '新增新闻')]
        await relay.scan_once()
        assert relay.deliver_once()
        assert relay.deliver_once()
        await relay.scan_once()
        assert not relay.deliver_once()
        assert [who for who, text in calls] == ['A', 'B']
        assert all('新增新闻' in text for who, text in calls)
        await relay.source.close()
        relay.store.close()
    asyncio.run(scenario())


def test_initialization_race_and_reconnect_catch_up(tmp_path):
    class ArrivalAtBootstrap(FakeClient):
        async def get_messages(self, entity, limit):
            snapshot = self.items[-limit:]
            self.items.append(raw(11, 'during bootstrap'))
            return snapshot
    async def scenario():
        relay, fake, _, _ = setup_relay(tmp_path, fake=ArrivalAtBootstrap())
        await relay.scan_once()
        assert [m.message_id for m in relay.store.unexpanded()] == [11]
        await relay.source.close()
        fake.items.append(raw(12, 'during disconnect'))
        await relay.scan_once()
        assert relay.store.cursor(-100123) == 12
        assert [m.message_id for m in relay.store.unexpanded()] == [11, 12]
        await relay.source.close()
        relay.store.close()
    asyncio.run(scenario())


def test_invalid_group_preserves_message_and_latest_group_controls_delivery(tmp_path):
    async def scenario():
        relay, fake, calls, group = setup_relay(tmp_path)
        await relay.scan_once()
        fake.items.append(raw(11))
        await relay.scan_once()
        group.write_text('broken', encoding='utf-8')
        with pytest.raises(ValueError):
            relay.deliver_once()
        assert len(relay.store.unexpanded()) == 1
        group.write_text('{"groups":{"1":["C"]}}', encoding='utf-8')
        relay.deliver_once()
        assert [who for who, _ in calls] == ['C']
        await relay.source.close()
        relay.store.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('contents', ['{}', '{"groups":{}}', '{"groups":{"2":["A"]}}'])
def test_missing_news_group_pauses_without_skipping_or_cancelling(tmp_path, contents):
    async def scenario():
        relay, fake, calls, group = setup_relay(tmp_path)
        await relay.scan_once()
        fake.items.append(raw(11))
        await relay.scan_once()
        assert relay.deliver_once()  # A confirmed, B still pending.
        fake.items.append(raw(12))
        await relay.scan_once()
        group.write_text(contents, encoding='utf-8')
        with pytest.raises(ValueError):
            relay.deliver_once()
        assert relay.store.status()['deliveries']['pending'] == 1
        assert [m.message_id for m in relay.store.unexpanded()] == [12]
        assert len(calls) == 1
        await relay.source.close()
        relay.store.close()
    asyncio.run(scenario())


def test_empty_group_is_skipped_and_unsubscribe_cancels_pending(tmp_path):
    async def scenario():
        relay, fake, calls, group = setup_relay(tmp_path)
        await relay.scan_once()
        fake.items.append(raw(11))
        await relay.scan_once()
        group.write_text('{"groups":{"1":[]}}', encoding='utf-8')
        assert not relay.deliver_once()
        fake.items.append(raw(12))
        await relay.scan_once()
        group.write_text('{"groups":{"1":["A","B"]}}', encoding='utf-8')
        assert relay.deliver_once()
        group.write_text('{"groups":{"1":["A"]}}', encoding='utf-8')
        assert not relay.deliver_once()
        assert [who for who, _ in calls] == ['A']
        assert relay.store.status()['deliveries']['skipped_removed'] == 1
        await relay.source.close()
        relay.store.close()
    asyncio.run(scenario())


def test_unknown_result_blocks_one_recipient_without_retry(tmp_path):
    async def scenario():
        relay, fake, calls, _ = setup_relay(tmp_path, push=lambda cfg, contact, text:
            {'state': 'uncertain' if contact == 'A' else 'sent', 'reason': 'receipt'})
        await relay.scan_once()
        fake.items += [raw(11), raw(12)]
        await relay.scan_once()
        while relay.deliver_once():
            pass
        assert [who for who, _ in calls] == ['A', 'B', 'B']
        assert relay.store.status()['deliveries']['uncertain'] == 1
        await relay.source.close()
        relay.store.close()
    asyncio.run(scenario())


def test_sending_does_not_block_scanning_and_stop_prevents_next_claim(tmp_path):
    async def scenario():
        started, release = threading.Event(), threading.Event()
        def delayed(*args):
            started.set()
            assert release.wait(5)
            return {'state': 'sent', 'reason': 'ok'}
        relay, fake, calls, _ = setup_relay(tmp_path, push=delayed)
        await relay.scan_once()
        fake.items.append(raw(11))
        await relay.scan_once()
        sending = asyncio.create_task(asyncio.to_thread(relay.deliver_once))
        assert await asyncio.to_thread(started.wait, 3)
        fake.items.append(raw(12))
        await relay.scan_once()
        assert relay.store.cursor(-100123) == 12
        relay.stopping.set()
        release.set()
        await sending
        assert not relay.deliver_once()
        assert len(calls) == 1
        await relay.source.close()
        relay.store.close()
    asyncio.run(scenario())


def test_account_or_source_change_on_reconnect_stops_before_more_delivery(tmp_path):
    async def scenario():
        relay, fake, calls, _ = setup_relay(tmp_path)
        await relay.scan_once()
        await relay.source.close()
        fake.entity.id = 456
        with pytest.raises(ValueError):
            await relay.scan_once()
        assert not relay.deliver_once()
        assert calls == []
        await relay.source.close()
        relay.store.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['source', 'membership'])
def test_source_change_during_connected_session_stops_delivery(tmp_path, change):
    async def scenario():
        relay, fake, calls, _ = setup_relay(tmp_path)
        await relay.scan_once()
        fake.items.append(raw(11))
        await relay.scan_once()
        if change == 'source':
            fake.entity.id = 456
        else:
            fake.entity.left = True
        assert fake.connected
        with pytest.raises(ValueError):
            await relay.scan_once()
        assert not relay.deliver_once()
        assert calls == []
        await relay.source.close()
        relay.store.close()
    asyncio.run(scenario())


def test_single_instance_lock_rejects_second_owner(tmp_path):
    from butler.channels.telegram.service import instance_lock
    with instance_lock(tmp_path / 'run.lock'):
        with pytest.raises(RuntimeError):
            with instance_lock(tmp_path / 'run.lock'):
                pytest.fail('second owner acquired lock')


def test_service_run_stops_cleanly_without_sending_history(tmp_path):
    async def scenario():
        relay, fake, calls, _ = setup_relay(tmp_path)
        stop = asyncio.Event()
        task = asyncio.create_task(relay.run(stop))
        await asyncio.sleep(.05)
        stop.set()
        await asyncio.wait_for(task, 2)
        assert calls == []
        assert not fake.connected
        relay.store.close()
    asyncio.run(scenario())
