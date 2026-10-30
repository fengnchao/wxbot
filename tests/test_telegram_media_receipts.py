import json


def forwarded(mid=8, source_mid=50):
    return {'message_id': mid, 'from': {'id': 12}, 'chat': {'id': 12, 'type': 'private'},
        'text': 'private message body', 'forward_origin': {'type': 'channel',
            'chat': {'id': -100123, 'username': 'ChannelName', 'title': 'private source title'},
            'message_id': source_mid}}


def test_persisted_authorized_update_publishes_bounded_public_source_receipt(tmp_path):
    from butler.channels.telegram.bot.queue import Queue
    from butler.channels.telegram.bot.service import persist_update
    queue = Queue(tmp_path / 'q.db')
    state = tmp_path / 'receiver'
    # Seed public-only older entries; the actual new ingress uses the real queue.
    state.mkdir()
    old = {'bot_id': 99, 'at': '2026-10-25T00:00:00+00:00', 'receipts': [
        {'source_chat_id': -100123, 'source_username': 'ChannelName', 'source_message_id': n,
         'bot_message_id': n, 'received_at': '2026-10-25T00:00:00+00:00'} for n in range(1,2001)]}
    (state / 'forward-receipts.json').write_text(json.dumps(old), encoding='utf-8')
    msg = forwarded(mid=2002, source_mid=9000)
    persist_update(queue, state, 99, {'update_id': 2002, 'message': msg}, (12,))
    result = json.loads((state / 'forward-receipts.json').read_text(encoding='utf-8'))
    assert result['bot_id'] == 99 and len(result['receipts']) == 2000
    last = result['receipts'][-1]
    assert last['source_chat_id'] == -100123 and last['source_username'] == 'ChannelName'
    assert last['source_message_id'] == 9000 and last['bot_message_id'] == 2002
    assert set(last) == {'source_chat_id','source_username','source_message_id','bot_message_id','received_at'}
    assert 'private' not in json.dumps(result)
    assert queue.offset(99) == 2003 and queue.next(99)['message']['text'] == 'private message body'


def test_untrusted_and_legacy_updates_never_forge_receipts_and_write_failure_preserves_ingress(tmp_path, monkeypatch):
    from butler.channels.telegram.bot.queue import Queue
    import butler.channels.telegram.bot.service as module
    queue = Queue(tmp_path / 'q.db')
    state = tmp_path / 'receiver'
    msg = forwarded()
    module.persist_update(queue, state, 99, {'update_id': 1, 'message': msg}, (88,))
    assert queue.next(99) is None and not (state / 'forward-receipts.json').exists()
    legacy = forwarded()
    del legacy['forward_origin']
    module.persist_update(queue, state, 99, {'update_id': 2, 'message': legacy}, (12,))
    assert not (state / 'forward-receipts.json').exists()
    monkeypatch.setattr(module, '_atomic', lambda *args: (_ for _ in ()).throw(OSError('private-token')))
    logs = []
    monkeypatch.setattr(module, 'log', logs.append)
    module.persist_update(queue, state, 99, {'update_id': 3, 'message': msg}, (12,))
    assert queue.offset(99) == 4
    with queue.db() as db:
        assert db.execute('SELECT count(*) FROM pending').fetchone()[0] == 2
    assert logs and 'private-token' not in str(logs)


def test_duplicate_ingress_never_refreshes_old_forward_receipt_time_or_source(tmp_path):
    from butler.channels.telegram.bot.queue import Queue
    from butler.channels.telegram.bot.service import persist_update
    queue = Queue(tmp_path / 'q.db')
    state = tmp_path / 'receiver'
    msg = forwarded()
    persist_update(queue, state, 99, {'update_id': 1, 'message': msg}, (12,))
    path = state / 'forward-receipts.json'
    before = path.read_bytes()
    persist_update(queue, state, 99, {'update_id': 1, 'message': msg}, (12,))
    assert path.read_bytes() == before
    persist_update(queue, state, 99, {'update_id': 1, 'message': forwarded(mid=99, source_mid=999)}, (12,))
    assert path.read_bytes() == before
