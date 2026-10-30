import sqlite3
from types import SimpleNamespace

import pytest

from butler.channels.telegram.bot.news import NewsRelay
from butler.channels.telegram.bot.queue import Queue


def test_backup_of_deleted_telegram_work_uses_the_same_write_reservation(tmp_path, monkeypatch):
    import butler.channels.telegram.bot.cleanup as cleanup
    queue, _, _ = setup(tmp_path)
    ingest(queue)
    original = sqlite3.connect
    target = tmp_path/'delete-unsent-backup.sqlite3'
    locked = []

    def connect(database, *args, **kwargs):
        if str(database) == str(target):
            writer = original(queue.path, timeout=0)
            try:
                writer.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError:
                locked.append(True)
            else:
                locked.append(False)
            finally:
                writer.rollback()
                writer.close()
        return original(database, *args, **kwargs)

    monkeypatch.setattr(cleanup.sqlite3, 'connect', connect)
    cleanup.delete_unsent(queue.path, backup_path=target)
    assert locked == [True]
    with original(target) as backup:
        assert backup.execute('SELECT count(*) FROM pending').fetchone()[0] == 1


def message(uid=1, *, image=False, album=None):
    value = {'message_id': uid, 'date': 1700000000, 'from': {'id': 12},
             'chat': {'id': 12, 'type': 'private'}, 'text': 'news ' + str(uid)}
    if image:
        value['photo'] = [{'file_id': 'photo-' + str(uid)}]
    if album:
        value['media_group_id'] = album
    return value


def setup(tmp_path, *, images=False):
    queue = Queue(tmp_path / 'relay.sqlite3')
    group = tmp_path / 'groups.json'
    group.write_text('{"groups":{"1":["A","B"]}}', encoding='utf-8')
    settings = SimpleNamespace(include_images=images, include_text=True,
                               album_quiet_seconds=0, max_album_wait=10)
    calls = []
    relay = NewsRelay(queue, 99, SimpleNamespace(group_file_path=lambda: group), (12,), lambda _: None,
                      media=SimpleNamespace(prepare=lambda _: [{'kind': 'image', 'media_id': 'a' * 32}]),
                      relay_settings=lambda: settings, clock=lambda: 100,
                      push=lambda cfg, contact, text: calls.append(contact) or {'state': 'sent', 'reason': 'ok'},
                      bundle_push=lambda cfg, contact, items, request: calls.append(contact) or {'state': 'sent', 'reason': 'ok'})
    return queue, relay, calls


def ingest(queue, uid=1, *, image=False, album=None):
    queue.ingest(99, {'update_id': uid}, message(uid, image=image, album=album), now=90)
    queue.finish(99, uid, 'received')


def test_delete_unsent_physically_removes_messages_and_all_failed_delivery_states(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    queue, relay, calls = setup(tmp_path)
    ingest(queue)
    assert relay.expand_once()
    with queue.db() as db:
        db.execute("UPDATE news_delivery SET state='uncertain' WHERE contact='A'")
        db.execute("UPDATE news_delivery SET state='not_submitted' WHERE contact='B'")
    queue.ingest(99, {'update_id': 2}, message(2))
    report = delete_unsent(queue.path, now=101)
    assert report == {'deleted_messages': 2, 'deleted_deliveries': 2, 'protected_active': 0}
    with queue.db() as db:
        assert db.execute('SELECT count(*) FROM pending').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM news_plan').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM news_delivery').fetchone()[0] == 0
    assert queue.offset(99) == 3
    assert not relay.expand_once() and not relay.deliver_once() and calls == []
    assert delete_unsent(queue.path) == {'deleted_messages': 0, 'deleted_deliveries': 0, 'protected_active': 0}


def test_partial_sent_history_is_preserved_and_failed_siblings_cannot_be_reexpanded(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    queue, relay, calls = setup(tmp_path)
    ingest(queue)
    assert relay.expand_once() and relay.deliver_once()
    with queue.db() as db:
        sent = db.execute("SELECT * FROM news_delivery WHERE state='sent'").fetchone()
    assert delete_unsent(queue.path) == {'deleted_messages': 0, 'deleted_deliveries': 1, 'protected_active': 0}
    with queue.db() as db:
        assert db.execute('SELECT * FROM news_delivery').fetchall() == [sent]
        assert db.execute('SELECT count(*) FROM pending').fetchone()[0] == 1
        assert '已删除' in db.execute('SELECT reason FROM news_plan').fetchone()[0]
    assert not relay.expand_once() and not relay.deliver_once() and calls == ['A']


def test_sending_is_protected_while_queued_siblings_are_deleted(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    queue, relay, calls = setup(tmp_path)
    ingest(queue)
    assert relay.expand_once()
    with queue.db() as db:
        db.execute("UPDATE news_delivery SET state='sending' WHERE contact='A'")
    assert delete_unsent(queue.path) == {'deleted_messages': 0, 'deleted_deliveries': 1, 'protected_active': 1}
    with queue.db() as db:
        assert db.execute('SELECT contact,state FROM news_delivery').fetchall() == [('A', 'sending')]
    ingest(queue, 2)
    assert relay.expand_once() and relay.deliver_once() and calls == ['A']


def test_bundle_cleanup_preserves_success_and_aliases_without_claiming_full_success(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    queue, relay, calls = setup(tmp_path, images=True)
    ingest(queue, image=True, album='album')
    assert relay.expand_once() and relay.deliver_once()
    assert delete_unsent(queue.path) == {'deleted_messages': 0, 'deleted_deliveries': 1, 'protected_active': 0}
    with queue.db() as db:
        assert db.execute('SELECT state FROM news_bundle_delivery').fetchall() == [('sent',)]
        assert db.execute('SELECT state FROM news_package').fetchone()[0] == 'cancelled'
        assert db.execute('SELECT count(*) FROM news_package_alias').fetchone()[0] == 1
    assert not relay.expand_once() and not relay.deliver_once() and calls == ['A']


def test_unsuccessful_album_source_rows_plans_packages_and_aliases_are_deleted_together(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    queue, relay, calls = setup(tmp_path, images=True)
    ingest(queue, image=True, album='album')
    ingest(queue, 2, image=True, album='album')
    assert relay.expand_once()
    assert delete_unsent(queue.path) == {'deleted_messages': 2, 'deleted_deliveries': 2, 'protected_active': 0}
    with queue.db() as db:
        for table in ('pending', 'news_plan', 'news_package', 'news_package_alias', 'news_bundle_delivery'):
            assert db.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0
    assert not relay.expand_once() and not relay.deliver_once() and calls == []


def test_cleanup_cancels_preparing_album_and_late_media_completion_cannot_publish(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    queue, relay, calls = setup(tmp_path, images=True)
    ingest(queue, image=True, album='album')
    def prepare_then_delete(_):
        assert delete_unsent(queue.path) == {'deleted_messages': 1, 'deleted_deliveries': 0, 'protected_active': 0}
        return [{'kind': 'image', 'media_id': 'a' * 32}]
    relay.media.prepare = prepare_then_delete
    relay.expand_once()
    with queue.db() as db:
        assert db.execute('SELECT count(*) FROM news_package').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM news_bundle_delivery').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM pending').fetchone()[0] == 0
    assert not relay.deliver_once() and calls == []


def test_late_album_member_does_not_inherit_the_original_members_success(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    queue, relay, calls = setup(tmp_path, images=True)
    ingest(queue, image=True, album='album')
    assert relay.expand_once() and relay.deliver_once() and relay.deliver_once()
    ingest(queue, 2, image=True, album='album')
    assert relay.expand_once()
    assert delete_unsent(queue.path) == {'deleted_messages': 1, 'deleted_deliveries': 0, 'protected_active': 0}
    with queue.db() as db:
        assert db.execute('SELECT uid FROM pending').fetchall() == [(1,)]
        assert db.execute('SELECT uid FROM news_plan').fetchall() == [(1,)]
        assert db.execute('SELECT state FROM news_bundle_delivery').fetchall() == [('sent',), ('sent',)]


def test_sending_only_retained_source_does_not_claim_partial_success(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    queue, relay, calls = setup(tmp_path)
    ingest(queue)
    assert relay.expand_once()
    with queue.db() as db:
        db.execute("UPDATE news_delivery SET state='sending' WHERE contact='A'")
    assert delete_unsent(queue.path)['protected_active'] == 1
    with queue.db() as db:
        reason = db.execute('SELECT reason FROM news_plan').fetchone()[0]
        assert '部分成功' not in reason and '正在发送' in reason


def test_already_complete_history_is_unchanged(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    queue, relay, calls = setup(tmp_path, images=True)
    ingest(queue, image=True)
    assert relay.expand_once() and relay.deliver_once() and relay.deliver_once()
    before = queue.path.read_bytes()
    assert delete_unsent(queue.path) == {'deleted_messages': 0, 'deleted_deliveries': 0, 'protected_active': 0}
    assert queue.path.read_bytes() == before


def test_deleted_update_cannot_be_ingested_again_but_new_updates_and_other_bots_work(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    queue, relay, calls = setup(tmp_path)
    ingest(queue, 7)
    delete_unsent(queue.path)
    queue.ingest(99, {'update_id': 7}, message(7))
    queue.ingest(99, {'update_id': 8}, message(8))
    queue.ingest(100, {'update_id': 7}, message(7))
    with queue.db() as db:
        assert db.execute('SELECT bot,uid FROM pending ORDER BY bot,uid').fetchall() == [(99, 8), (100, 7)]
    assert queue.offset(99) == 9 and queue.offset(100) == 8


def test_cleanup_requires_existing_supported_database_without_initializing_or_migrating(tmp_path):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    path = tmp_path / 'missing.sqlite3'
    with pytest.raises((ValueError, FileNotFoundError)):
        delete_unsent(path)
    assert not path.exists()
    path.write_bytes(b'')
    before = path.read_bytes()
    with pytest.raises(ValueError):
        delete_unsent(path)
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT name FROM sqlite_master').fetchall() == []


def test_slow_text_expansion_cannot_recreate_tasks_after_cleanup(tmp_path, monkeypatch):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    import butler.channels.telegram.bot.news as news_module
    queue, relay, calls = setup(tmp_path)
    ingest(queue)
    original = news_module.format_news
    def format_then_delete(*args, **kwargs):
        value = original(*args, **kwargs)
        assert delete_unsent(queue.path)['deleted_messages'] == 1
        return value
    monkeypatch.setattr(news_module, 'format_news', format_then_delete)
    relay.expand_once()
    with queue.db() as db:
        assert db.execute('SELECT count(*) FROM news_delivery').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM news_plan').fetchone()[0] == 0
    assert not relay.deliver_once() and calls == []


def test_slow_bundle_selection_cannot_recreate_deleted_source(tmp_path, monkeypatch):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    import butler.channels.telegram.bot.news as news_module
    queue, relay, calls = setup(tmp_path, images=True)
    ingest(queue, image=True)
    original = news_module.read_subscribers
    def subscribers_then_delete(*args, **kwargs):
        value = original(*args, **kwargs)
        assert delete_unsent(queue.path)['deleted_messages'] == 1
        return value
    monkeypatch.setattr(news_module, 'read_subscribers', subscribers_then_delete)
    relay.expand_once()
    with queue.db() as db:
        assert db.execute('SELECT count(*) FROM news_package').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM news_bundle_delivery').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM news_plan').fetchone()[0] == 0
    assert calls == []


@pytest.mark.parametrize('images', [False, True])
def test_projection_shows_partial_success_and_deleted_remainder_instead_of_all_sent(tmp_path, images):
    from butler.channels.telegram.bot.cleanup import delete_unsent
    from dashboard.telegram_view import TelegramView
    queue, relay, calls = setup(tmp_path, images=images)
    ingest(queue, image=images)
    assert relay.expand_once() and relay.deliver_once()
    delete_unsent(queue.path)
    cfg, butler = tmp_path / 'telegram.toml', tmp_path / 'butler.toml'
    cfg.write_text('[telegram_bot]\nstate_dir="."\nbutler_config="butler.toml"\n', encoding='utf-8')
    butler.write_text('[agent]\nprovider="codex"\ndata_dir="private-data"\n', encoding='utf-8')
    view = TelegramView(cfg, butler)
    result = view.read(scope='history')
    assert result['status'] == 'ok' and result['page']['total'] == 1
    row = result['rows'][0]
    assert row['state'] == 'partial_deleted' and '部分成功' in row['reason'] and '已删除' in row['reason']
    assert [task['state'] for task in row['deliveries']] == ['sent']
    assert view.read(scope='active')['page']['total'] == 0
    workflow = view.workflow()['messages']
    assert len(workflow) == 1 and workflow[0]['terminal'] and workflow[0]['scope'] == 'complete'
