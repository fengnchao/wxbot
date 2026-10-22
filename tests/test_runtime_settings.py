"""Runtime settings use temporary configuration, temporary queues and fake UI controls."""
import logging
from types import SimpleNamespace

import pytest

from wxbot.config import load_config
from wxbot.inbox import MainInbox
from wxbot.queue_store import QueueStore
from wxbot.wechat.typing import TypingSession


@pytest.mark.parametrize('section,key,value', [
    ('wechat.typing', 'chunk_size', value)
    for value in ('0', '101', '1.5', 'true', '"private-invalid-value"', '[]')
] + [
    ('wechat.typing', 'chunk_interval', value)
    for value in ('0.049', '10.001', 'nan', 'inf', '-inf', 'true', '"private-invalid-value"', '[]')
] + [
    ('queue', 'failure_discard_seconds', value)
    for value in ('0', '86401', 'nan', 'inf', '-inf', 'true', '"private-invalid-value"', '[]')
])
def test_loading_config_rejects_invalid_runtime_settings_without_echoing_values(tmp_path, section, key, value):
    path = tmp_path / 'settings.toml'
    path.write_text(f'[{section}]\n{key} = {value}\n', encoding='utf-8')
    with pytest.raises(ValueError) as caught:
        load_config(path)
    assert f'{section}.{key}' in str(caught.value)
    assert 'private-invalid-value' not in str(caught.value)


@pytest.mark.parametrize('text,field', [
    ('wechat = "private-invalid-value"', 'wechat'),
    ('queue = "private-invalid-value"', 'queue'),
    ('[wechat]\ntyping = "private-invalid-value"', 'wechat.typing'),
])
def test_loading_config_rejects_runtime_sections_that_are_not_tables(tmp_path, text, field):
    path = tmp_path / 'settings.toml'
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError) as caught:
        load_config(path)
    assert field in str(caught.value)
    assert 'private-invalid-value' not in str(caught.value)


@pytest.mark.parametrize('size,interval,ttl', [(1, .05, 1), (100, 10, 86400)])
def test_loading_config_accepts_runtime_boundaries(tmp_path, size, interval, ttl):
    path = tmp_path / 'settings.toml'
    path.write_text(f'[wechat.typing]\nchunk_size={size}\nchunk_interval={interval}\n'
                    f'[queue]\nfailure_discard_seconds={ttl}\n', encoding='utf-8')
    cfg = load_config(path)
    assert cfg['wechat']['typing']['chunk_size'] == size
    assert cfg['wechat']['typing']['chunk_interval'] == interval
    assert cfg['queue']['failure_discard_seconds'] == ttl


@pytest.mark.parametrize('key,value', [
    ('chunk_size', 0), ('chunk_size', 101), ('chunk_size', True), ('chunk_size', 2.0),
    ('chunk_interval', .049), ('chunk_interval', 10.001), ('chunk_interval', True),
    ('chunk_interval', float('nan')), ('chunk_interval', float('inf')),
    ('chunk_interval', 'private-invalid-value'),
])
def test_direct_typing_session_rejects_invalid_settings(key, value):
    chat = SimpleNamespace(wcfg={'typing': {key: value}})
    with pytest.raises(ValueError) as caught:
        TypingSession(chat, object(), object(), 'hello')
    assert f'wechat.typing.{key}' in str(caught.value)
    assert 'private-invalid-value' not in str(caught.value)


def test_typing_uses_configured_chunks_and_interval_with_prefix_checks(monkeypatch):
    from test_typing import make_chat
    chat, sent = make_chat(monkeypatch)
    chat.wcfg['typing'] = {'chunk_size': 3, 'chunk_interval': .2}
    clock = [0]
    task = chat.start_send('1234\r\n56🤖', clock=lambda: clock[0])
    assert task.step() == 'typing'
    assert task.edit.pasted == ['123']
    clock[0] = .199
    assert task.step() == 'typing'
    assert task.edit.pasted == ['123']
    clock[0] = .2
    assert task.step() == 'typing'
    assert task.edit.pasted == ['123', '4\n5']
    clock[0] = .4
    assert task.step() == 'typing'
    assert task.edit.pasted == ['123', '4\n5', '6🤖']
    clock[0] = .46
    assert task.step() == 'submitted'
    assert sent == ['{Ctrl}v', '{Ctrl}v', '{Ctrl}v', '{Enter}']
    assert task.edit.clipboard.data == task.edit.original_clipboard


def test_typing_failure_reports_actual_configured_chunk_character_count(monkeypatch):
    from test_typing import make_chat
    chat, sent = make_chat(monkeypatch)
    chat.wcfg['typing'] = {'chunk_size': 3, 'chunk_interval': .2}
    task = chat.start_send('123456', clock=lambda: 0)
    task.step()
    monkeypatch.setattr(chat, '_can_send', lambda *args: False)
    assert task.step() == 'blocked'
    assert task.failure_details['characters_entered'] == 3
    assert sent == ['{Ctrl}v']
    assert task.edit.clipboard.data == task.edit.original_clipboard


@pytest.mark.parametrize('value', [0, 86401, True, float('nan'), float('inf'), 'private-invalid-value'])
def test_queue_rejects_invalid_timeout_before_creating_database(tmp_path, value):
    path = tmp_path / 'must-not-exist' / 'queue.sqlite3'
    with pytest.raises(ValueError) as caught:
        QueueStore(path, failure_timeout_seconds=value)
    assert 'queue.failure_discard_seconds' in str(caught.value)
    assert 'private-invalid-value' not in str(caught.value)
    assert not path.parent.exists()


@pytest.mark.parametrize('state', ['blocked', 'uncertain'])
def test_configured_failure_timeout_releases_next_task_and_preserves_audit(state):
    from test_delivery_failure_policy import failed
    store = QueueStore(':memory:', failure_timeout_seconds=7.5)
    try:
        task = failed(store, state=state, at=10)
        later = store.enqueue_delivery('A', 'next', now=11)
        assert store.expire_failed_deliveries(now=17.49) == []
        assert store.claim_delivery(now=17.49) is None
        assert [row['id'] for row in store.expire_failed_deliveries(now=17.5)] == [task]
        row = store.get_delivery(task)
        assert row['failed_at'] == 10
        assert row['state'] == 'skipped' and row['resolution'] == 'timeout'
        assert '7.5秒' in row['error'] and 'foreground changed' in row['error']
        assert store.claim_delivery(now=17.5).id == later
        events = store.delivery_events()
        assert [event['action'] for event in events] == ['failed', 'timeout_discard']
        assert '7.5秒' in events[-1]['reason']
    finally:
        store.close()


def test_restart_applies_current_timeout_to_original_first_failure(tmp_path):
    from test_delivery_failure_policy import failed
    path = tmp_path / 'queue.sqlite3'
    store = QueueStore(path, failure_timeout_seconds=30)
    try:
        task = failed(store, at=10)
        store.retry(task, delivery=True, now=20)
        store.claim_delivery(now=20)
        store.finish_delivery(task, 'blocked', now=20, error='focus changed')
    finally:
        store.close()
    store = QueueStore(path, failure_timeout_seconds=60)
    try:
        assert store.get_delivery(task)['failed_at'] == 10
        assert store.expire_failed_deliveries(now=69.9) == []
        assert [row['id'] for row in store.expire_failed_deliveries(now=70)] == [task]
    finally:
        store.close()


@pytest.mark.parametrize('access', ['readonly', 'admin'])
def test_management_connections_do_not_expire_failures_on_open(tmp_path, access):
    from test_delivery_failure_policy import failed
    path = tmp_path / 'queue.sqlite3'
    runtime = QueueStore(path)
    try:
        task = failed(runtime, at=0)
        reader = QueueStore(path, access=access, failure_timeout_seconds=1)
        try:
            assert reader.get_delivery(task)['state'] == 'blocked'
            assert [event['action'] for event in reader.delivery_events()] == ['failed']
        finally:
            reader.close()
    finally:
        runtime.close()


def test_delivery_logs_deadline_and_expiry_using_store_timeout(caplog):
    from test_delivery_queue import Chat, pump
    store = QueueStore(':memory:', failure_timeout_seconds=7.5)
    try:
        task = store.enqueue_delivery('A', 'private reply body', now=12)
        clock = [12]
        sender = pump(store, Chat(), clock)
        sender.capture_target = lambda contact: False
        with caplog.at_level(logging.ERROR):
            sender.start_next()
        assert '自动丢弃截止=19.5' in caplog.text
        assert 'private reply body' not in caplog.text
        clock[0] = 19.5
        with caplog.at_level(logging.WARNING):
            sender.tick(allow_start=False)
        assert '等待上限=7.5秒' in caplog.text
        assert store.get_delivery(task)['resolution'] == 'timeout'
    finally:
        store.close()


def test_delivery_supports_legacy_store_without_timeout_attribute(caplog):
    from test_delivery_queue import Chat, pump
    store = QueueStore(':memory:')
    class LegacyStore:
        def __getattr__(self, name):
            if name == 'failure_timeout_seconds':
                raise AttributeError(name)
            return getattr(store, name)
    try:
        task = store.enqueue_delivery('A', 'reply', now=12)
        sender = pump(LegacyStore(), Chat(), [12])
        sender.capture_target = lambda contact: False
        with caplog.at_level(logging.ERROR):
            sender.start_next()
        assert '自动丢弃截止=192' in caplog.text
        assert store.get_delivery(task)['state'] == 'blocked'
    finally:
        store.close()


def test_delivery_start_log_shows_configured_typing_settings(monkeypatch, caplog):
    from test_delivery_queue import pump
    from test_typing import make_chat
    chat, _ = make_chat(monkeypatch)
    chat.wcfg['typing'] = {'chunk_size': 3, 'chunk_interval': .2}
    monkeypatch.setattr(chat, 'read_messages', lambda: [])
    store = QueueStore(':memory:')
    try:
        store.enqueue_delivery('A', 'reply', now=0)
        sender = pump(store, chat, [0])
        with caplog.at_level(logging.INFO):
            sender.start_next()
        assert '每3字/0.2秒' in caplog.text
    finally:
        store.close()


def test_main_inbox_passes_configured_timeout_to_runtime_store():
    from test_main_window import Desktop, Router, cfg
    config = cfg()
    config['queue']['failure_discard_seconds'] = 12
    inbox = MainInbox(config, Router(), desktop=Desktop([]))
    try:
        task = inbox.store.enqueue_delivery('A', 'reply', now=0)
        inbox.store.claim_delivery(now=0)
        inbox.store.finish_delivery(task, 'blocked', now=0, error='focus changed')
        assert inbox.store.expire_failed_deliveries(now=11.9) == []
        assert [row['id'] for row in inbox.store.expire_failed_deliveries(now=12)] == [task]
    finally:
        inbox.store.close()


def test_direct_main_inbox_rejects_invalid_timeout_with_supplied_store():
    from test_main_window import Desktop, Router, cfg
    config = cfg()
    config['queue']['failure_discard_seconds'] = True
    store = QueueStore(':memory:')
    try:
        with pytest.raises(ValueError, match='queue.failure_discard_seconds'):
            MainInbox(config, Router(), desktop=Desktop([]), store=store)
    finally:
        store.close()
