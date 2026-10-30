import pytest

from wxbot.queue_store import Incoming, QueueStore


def add_delivery(store, state, text=None, **values):
    record_id = store.enqueue_delivery('A', text or state, now=1)
    with store._transaction() as db:
        assignments = {'state': state, **values}
        db.execute('UPDATE outbox SET ' + ','.join(k+'=?' for k in assignments) + ' WHERE id=?',
                   (*assignments.values(), record_id))
    return record_id


def test_delete_unsent_removes_unsuccessful_records_and_preserves_active_and_sent():
    store = QueueStore(':memory:')
    try:
        removed = [add_delivery(store, state) for state in ('pending', 'blocked', 'uncertain', 'skipped')]
        sent = add_delivery(store, 'sent', 'already delivered')
        sending = add_delivery(store, 'sending')
        confirming = add_delivery(store, 'confirming')
        before = store.get_delivery(sent)
        result = store.delete_unsent(now=10)
        assert result['deleted_deliveries'] == 4
        assert result['protected_active'] == 2
        assert all(store.get_delivery(item) is None for item in removed)
        assert store.get_delivery(sent) == before
        assert store.get_delivery(sending)['state'] == 'sending'
        assert store.get_delivery(confirming)['state'] == 'confirming'
        assert store.delete_unsent(now=11)['deleted_deliveries'] == 0
        assert not store._db.execute('PRAGMA foreign_key_check').fetchall()
    finally:
        store.close()


def test_deleted_processing_batch_cannot_publish_a_late_reply():
    store = QueueStore(':memory:')
    try:
        store.capture('A', [], [Incoming('question')], now=0)
        store.prepare(quiet=0, max_wait=10, prefix='/', now=1)
        batch = store.claim_batch(now=1)
        result = store.delete_unsent(now=2)
        assert result['deleted_messages'] == 1
        assert store.get_batch(batch.id) is None
        with pytest.raises(ValueError):
            store.finish_batch_parts(batch.id, ('late answer',), now=3)
        store.fail_batch(batch.id, 'late failure', now=3)
        assert store.records('inbox') == []
        assert store.records('outbox') == []
    finally:
        store.close()


def test_partial_sent_reply_keeps_successful_part_and_cancels_remaining_reply():
    store = QueueStore(':memory:')
    try:
        store.capture('A', [], [Incoming('question')], now=0)
        store.prepare(quiet=0, max_wait=10, prefix='/', now=1)
        batch = store.claim_batch(now=1)
        store.finish_batch_parts(batch.id, ('sent part', 'unsent part'), now=1)
        delivery = store.claim_delivery(now=1)
        store.finish_delivery(delivery.id, 'sent', now=1)
        result = store.delete_unsent(now=2)
        assert result['deleted_deliveries'] == 1
        assert store.get_delivery(delivery.id)['state'] == 'sent'
        assert store.get_delivery(batch.id+':2') is None
        row = store.get_batch(batch.id)
        assert row['state'] == 'done'
        assert row['delivery_resolution'] == 'deleted'
        assert row['part_count'] == 2
        assert 'unsent part' not in row['reply_text']
        assert store.claim_delivery(now=3) is None
    finally:
        store.close()


def test_partially_deleted_package_keeps_a_failed_replay_receipt_after_active_part_finishes():
    store = QueueStore(':memory:')
    items = [{'kind': 'text', 'text': 'active'}, {'kind': 'text', 'text': 'remove'}]
    try:
        package = store.enqueue_package('A', items, 'cleanup-request', media_paths={}, now=0)
        active = store.claim_delivery(now=0)
        result = store.delete_unsent(now=1)
        assert result['deleted_deliveries'] == 1
        assert result['protected_active'] == 1
        store.finish_delivery(active.id, 'sent', now=2)
        assert store.package_receipt(package) == {'done': True, 'ok': False, 'state': 'cancelled'}
        assert store.enqueue_package('A', items, 'cleanup-request', media_paths={}, now=3) == package
        assert store.claim_delivery(now=3) is None
    finally:
        store.close()


def test_cleanup_rejects_an_old_in_memory_request_but_allows_a_new_request():
    store = QueueStore(':memory:')
    try:
        store.delete_unsent(now=10)
        with pytest.raises(ValueError, match='删除'):
            store.enqueue_delivery('A', 'old request', now=11, received_at=9)
        fresh = store.enqueue_delivery('A', 'new request', now=12, received_at=11)
        assert store.claim_delivery(now=12).id == fresh
    finally:
        store.close()


def test_deleting_unsent_resolves_waiters_without_waiting_for_timeout():
    from wxbot.delivery import DeliveryPump
    from wxbot.outbound import OutboundRequest
    store = QueueStore(':memory:')
    pump = DeliveryPump(store, lambda contact: None, lambda contact: False, lambda: None,
                        clock=lambda: 1, monotonic=lambda: 1)
    try:
        request = OutboundRequest('A', 'pending')
        pump.enqueue(request)
        store.delete_unsent(now=2)
        pump.tick(allow_start=False)
        assert request.event.is_set()
        assert request.ok is False
        assert '删除' in request.detail
    finally:
        store.close()


def test_deleted_draft_is_reported_without_operating_wechat():
    store = QueueStore(':memory:')
    try:
        task = add_delivery(store, 'blocked', draft_text='owned prefix', manual_required=1)
        result = store.delete_unsent(now=2)
        assert result['drafts_to_clear'] == 1
        assert store.get_delivery(task) is None
    finally:
        store.close()


def test_partial_reply_history_does_not_claim_deleted_parts_were_sent():
    from dashboard.queue_view import QueueView
    store = QueueStore(':memory:')
    try:
        store.capture('A', [], [Incoming('question')], now=0)
        store.prepare(quiet=0, max_wait=10, prefix='/', now=1)
        batch = store.claim_batch(now=1)
        store.finish_batch_parts(batch.id, ('sent part', 'deleted part'), now=1)
        sent = store.claim_delivery(now=1)
        store.finish_delivery(sent.id, 'sent', now=1)
        store.delete_unsent(now=2)
        from dashboard.reply_rounds import read_rounds
        rows, _ = read_rounds(store._db, QueueView._row, contact='', state='all', scope='history',
                              limit=50, offset=0, now=3, timeout=180)
        assert rows[0]['display_state'] == 'partial_deleted'
        assert rows[0]['part_count'] == store.get_delivery(sent.id)['part_count'] == 2
        assert rows[0]['sent_parts'] == 1
    finally:
        store.close()


@pytest.mark.parametrize('failure', ['blocked', 'uncertain'])
def test_late_active_package_failure_and_manual_confirmation_cannot_erase_cancellation(failure):
    store = QueueStore(':memory:')
    items = [{'kind': 'text', 'text': 'active'}, {'kind': 'text', 'text': 'deleted'}]
    try:
        package = store.enqueue_package('A', items, 'late-failure', media_paths={}, now=0)
        active = store.claim_delivery(now=0)
        store.delete_unsent(now=1)
        store.finish_delivery(active.id, failure, now=2)
        assert store.package_receipt(package)['state'] == 'cancelled'
        store.resolve(active.id, delivery=True, sent=True, now=3)
        assert store.package_receipt(package) == {'done': True, 'ok': False, 'state': 'cancelled'}
    finally:
        store.close()


def test_cleanup_does_not_relabel_an_untouched_active_reply_as_deleted():
    store = QueueStore(':memory:')
    try:
        store.capture('A', [], [Incoming('question')], now=0)
        store.prepare(quiet=0, max_wait=10, prefix='/', now=1)
        batch = store.claim_batch(now=1)
        store.finish_batch_parts(batch.id, ('active part',), now=1)
        store.claim_delivery(now=1)
        before = store.get_batch(batch.id)
        assert store.delete_unsent(now=2)['protected_active'] == 1
        assert store.get_batch(batch.id) == before
    finally:
        store.close()


def test_cleanup_protects_uncollected_read_tasks_instead_of_clearing_only_their_database_marker():
    store = QueueStore(':memory:')
    try:
        store.remember_session('unread chat', 2, True, now=0)
        before = store.pending_sessions()
        result = store.delete_unsent(now=1)
        assert result['protected_reads'] == 1
        assert result['protected_active'] == 1
        assert store.pending_sessions() == before
    finally:
        store.close()


def test_backup_is_taken_while_writers_are_locked_so_no_deleted_record_misses_the_snapshot(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path
    import wxbot.queue_cleanup as cleanup
    path = tmp_path/'queue.sqlite3'
    store = QueueStore(path)
    original = sqlite3.connect
    writer_was_locked = []

    def connect(database, *args, **kwargs):
        if Path(str(database)).name.startswith('delete-unsent-'):
            writer = original(path, timeout=0)
            try:
                writer.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError:
                writer_was_locked.append(True)
            else:
                writer_was_locked.append(False)
            finally:
                writer.rollback()
                writer.close()
        return original(database, *args, **kwargs)

    try:
        task = store.enqueue_delivery('A', 'unsent', now=0)
        monkeypatch.setattr(cleanup.sqlite3, 'connect', connect)
        result = store.delete_unsent(now=1)
        assert writer_was_locked == [True]
        with original(result['backup_path']) as backup:
            assert backup.execute('SELECT id FROM outbox WHERE id=?', (task,)).fetchone() == (task,)
    finally:
        store.close()
