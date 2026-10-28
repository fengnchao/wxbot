import sqlite3

import pytest

from log.queue_actions import QueueActions
from wxbot.queue_store import QueueStore


def test_bulk_delete_requires_explicit_confirmation_before_modifying_any_record(tmp_path):
    path = tmp_path/'q.db'
    store = QueueStore(path)
    try:
        task = store.enqueue_delivery('A', 'not yet sent', now=0)
        for body in ({}, {'acknowledge': False}, {'acknowledge': True, 'path': 'untrusted.db'}):
            with pytest.raises(ValueError):
                QueueActions(path).delete_unsent(body, now=1)
        assert store.get_delivery(task)['state'] == 'pending'
    finally:
        store.close()


def test_bulk_delete_returns_actual_counts_and_a_restorable_backup(tmp_path):
    path = tmp_path/'q.db'
    store = QueueStore(path)
    try:
        task = store.enqueue_delivery('A', 'unsent', now=0)
        result = QueueActions(path).delete_unsent({'acknowledge': True}, now=1)
        assert result['ok']
        assert result['wxbot']['deleted_deliveries'] == 1
        assert result['telegram']['deleted_deliveries'] == 0
        assert store.get_delivery(task) is None
        with sqlite3.connect(result['wxbot']['backup_path']) as backup:
            assert backup.execute('SELECT text FROM outbox WHERE id=?', (task,)).fetchone() == ('unsent',)
    finally:
        store.close()


def test_bulk_delete_handles_missing_queues_without_creating_databases(tmp_path):
    path = tmp_path/'missing.db'
    result = QueueActions(path).delete_unsent({'acknowledge': True}, telegram_config=tmp_path/'missing.toml')
    assert result['ok']
    assert result['wxbot']['deleted_deliveries'] == result['telegram']['deleted_deliveries'] == 0
    assert not path.exists()


def test_bulk_delete_covers_telegram_using_server_configuration_and_preserves_cursor(tmp_path):
    from butler.telegram_bot.queue import Queue
    state = tmp_path/'telegram'
    queue = Queue(state/'relay.sqlite3')
    message = {'message_id': 1, 'from': {'id': 12}, 'chat': {'id': 12, 'type': 'private'}, 'text': 'news'}
    queue.ingest(99, {'update_id': 1}, message)
    with queue.db() as db:
        db.execute("UPDATE pending SET state='received'")
        db.execute("INSERT INTO news_plan VALUES(99,1,'ready')")
        db.execute("INSERT INTO news_delivery(bot,uid,contact,part,text) VALUES(99,1,'A',1,'news')")
    config = tmp_path/'telegram.toml'
    config.write_text('[telegram_bot]\nstate_dir="telegram"\n', encoding='utf-8')
    result = QueueActions(tmp_path/'missing.db').delete_unsent({'acknowledge': True}, telegram_config=config, now=1)
    assert result['ok'] and result['telegram']['deleted_messages'] == 1
    assert result['telegram']['deleted_deliveries'] == 1
    assert queue.offset(99) == 2
    assert queue.next(99) is None
    with sqlite3.connect(result['telegram']['backup_path']) as backup:
        assert backup.execute('SELECT count(*) FROM pending').fetchone()[0] == 1


def test_partial_failure_is_explicit_and_does_not_hide_successful_other_channel_cleanup(tmp_path):
    path = tmp_path/'q.db'
    store = QueueStore(path)
    try:
        task = store.enqueue_delivery('A', 'unsent', now=0)
        config = tmp_path/'broken.toml'
        config.write_text('not valid toml', encoding='utf-8')
        result = QueueActions(path).delete_unsent({'acknowledge': True}, telegram_config=config, now=1)
        assert result['ok'] is False and 'Telegram' in result['error']
        assert result['wxbot']['deleted_deliveries'] == 1
        assert store.get_delivery(task) is None
    finally:
        store.close()


def test_bulk_delete_http_route_checks_origin_json_and_explicit_confirmation(tmp_path):
    from email.message import Message
    from io import BytesIO
    import json
    from types import SimpleNamespace
    from log.server import Handler

    path = tmp_path/'q.db'
    store = QueueStore(path)
    task = store.enqueue_delivery('A', 'unsent', now=0)
    base = 'http://127.0.0.1:8788'
    valid = {'Host': '127.0.0.1:8788', 'Origin': base,
             'Content-Type': 'application/json', 'X-Wxbot-Queue-Action': '1'}

    def post(headers, payload):
        handler = Handler.__new__(Handler)
        handler.path = '/api/queue-delete-unsent'
        handler.headers = Message()
        raw = json.dumps(payload).encode()
        for name, value in {**headers, 'Content-Length': str(len(raw))}.items():
            handler.headers[name] = value
        handler.rfile = BytesIO(raw)
        handler.connection = SimpleNamespace(getsockname=lambda: ('127.0.0.1', 8788))
        handler.server = SimpleNamespace(server_port=8788)
        handler._config_view = lambda: SimpleNamespace(root=tmp_path, queue_options=lambda: {'path': path})
        results = []
        handler._json = lambda data, code=200: results.append((code, data))
        handler.do_POST()
        return results[0]

    try:
        assert post({}, {'acknowledge': True})[0] == 403
        assert post({**valid, 'Origin': 'https://attacker.example'}, {'acknowledge': True})[0] == 403
        assert post({**valid, 'Host': 'attacker.example:8788', 'Origin': 'http://attacker.example:8788'}, {'acknowledge': True})[0] == 403
        assert post({**valid, 'Content-Type': 'text/plain'}, {'acknowledge': True})[0] == 403
        assert post(valid, {'acknowledge': False})[0] == 409
        assert store.get_delivery(task)['state'] == 'pending'
        status, data = post(valid, {'acknowledge': True})
        assert status == 200 and data['ok'] and data['wxbot']['deleted_deliveries'] == 1
        assert store.get_delivery(task) is None
    finally:
        store.close()
