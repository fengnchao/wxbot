import hashlib
import json
import sqlite3

import pytest


def fixture(tmp_path, package_state='ready', deliveries=('pending',), *, legacy=False):
    from butler.telegram_bot.queue import Queue
    cfg = tmp_path / 'config.telegram-bot.toml'
    cfg.write_text('[telegram_bot]\nstate_dir="state"\nbutler_config="butler.toml"\n', encoding='utf-8')
    butler = tmp_path / 'butler.toml'
    butler.write_text('[agent]\nprovider="codex"\ndata_dir="private-data"\n', encoding='utf-8')
    path = tmp_path / 'state' / 'relay.sqlite3'
    queue = Queue(path)
    for uid in (1, 2):
        msg = {'message_id': uid, 'date': 1700000000, 'from': {'id': 12},
               'chat': {'id': 12, 'type': 'private'}, 'media_group_id': 'album',
               'photo': [{'file_id': str(uid)}]}
        queue.ingest(99, {'update_id': uid}, msg)
        queue.finish(99, uid, 'received')
    with queue.db() as db:
        for uid in (1, 2):
            db.execute('INSERT INTO news_plan VALUES(?,?,?)', (99, uid, '图片准备'))
        if legacy:
            db.execute('DROP TABLE news_package')
            db.execute('DROP TABLE news_bundle_delivery')
            db.execute("INSERT INTO news_delivery(bot,uid,contact,part,text,state) VALUES(99,1,'A',1,'old text','sent')")
        else:
            db.execute('INSERT INTO news_package(bot,package_key,uid,items,sender,state,reason) VALUES(?,?,?,?,?,?,?)',
                (99, 'chat:12:album:album', 1, json.dumps([{'kind':'image','media_id':'a'*32}]),
                 12, package_state, '图片下载失败' if package_state == 'media_failed' else '图片就绪'))
            for number, state in enumerate(deliveries, 1):
                db.execute('INSERT INTO news_bundle_delivery(bot,package_key,contact,request_id,state,reason) VALUES(?,?,?,?,?,?)',
                    (99, 'chat:12:album:album', 'A' if number == 1 else 'B', 'source-' + str(number), state,
                     '整个图文包确认' if state == 'sent' else '等待整包回执'))
    return cfg, butler, path


@pytest.mark.parametrize('package_state,deliveries,expected', [
    ('preparing', (), 'preparing'), ('ready', (), 'ready'),
    ('media_failed', (), 'media_failed'), ('ready', ('pending',), 'pending'),
    ('ready', ('sent',), 'sent'), ('ready', ('sent','pending'), 'pending'),
    ('ready', ('sent','uncertain'), 'blocked'), ('ready', ('sent','cancelled'), 'cancelled'),
])
def test_projection_uses_media_and_whole_bundle_receipts_for_every_album_member(tmp_path, package_state, deliveries, expected):
    from log.telegram_view import TelegramView
    cfg, butler, path = fixture(tmp_path, package_state, deliveries)
    before = hashlib.sha256(path.read_bytes()).digest()
    result = TelegramView(cfg, butler).read()
    assert result['status'] == 'ok'
    assert [row['state'] for row in result['rows']] == [expected, expected]
    assert all(row['package_key'] == 'chat:12:album:album' for row in result['rows'])
    assert all(row['media_state'] == package_state for row in result['rows'])
    assert hashlib.sha256(path.read_bytes()).digest() == before


def test_failed_image_is_issue_with_preparation_event_and_operator_error(tmp_path):
    from log.telegram_view import TelegramView
    cfg, butler, path = fixture(tmp_path, 'media_failed', ())
    view = TelegramView(cfg, butler)
    result = view.read(scope='issues')
    assert result['page']['total'] == 2
    assert all('图片下载失败' in row['error'] for row in result['rows'])
    messages = view.workflow()['messages']
    assert all(row['scope'] == 'issues' and not row['terminal'] for row in messages)
    assert all(any(e['stage'] == 'telegram_media' and e['status'] == 'media_failed' for e in row['events']) for row in messages)


def test_bundle_recipient_filter_uses_members_package_identity(tmp_path):
    from log.telegram_view import TelegramView
    cfg, butler, path = fixture(tmp_path)
    result = TelegramView(cfg, butler).read(contact='A')
    assert result['page']['total'] == 2
    for row in result['rows']:
        assert row['targets'] == 'A'
        task = row['deliveries'][0]
        assert task['kind'] == 'bundle' and task['request_id'] == 'source-1'
        assert task['package_key'] == 'chat:12:album:album'


def test_cli_exposes_media_preparation_and_actual_package_delivery(tmp_path):
    from butler.telegram_bot.__main__ import status
    cfg, butler, path = fixture(tmp_path, 'ready', ('sent',))
    before = path.read_bytes()
    result = status(cfg)
    assert result['news_package'][0]['state'] == 'ready'
    assert result['news_bundle_delivery'][0]['state'] == 'sent'
    assert result['news_bundle_delivery'][0]['package_key'] == result['news_package'][0]['package_key']
    assert path.read_bytes() == before


def test_legacy_database_projection_and_cli_remain_read_only(tmp_path):
    from butler.telegram_bot.__main__ import status
    from log.telegram_view import TelegramView
    cfg, butler, path = fixture(tmp_path, legacy=True)
    before = path.read_bytes()
    result = TelegramView(cfg, butler).read()
    assert result['status'] == 'ok'
    assert {row['state'] for row in result['rows']} == {'sent','skipped'}
    cli = status(cfg)
    assert cli['news_package'] == [] and cli['news_bundle_delivery'] == []
    assert path.read_bytes() == before


def test_late_album_member_does_not_inherit_sent_receipt_of_earlier_images(tmp_path):
    from log.telegram_view import TelegramView
    cfg, butler, path = fixture(tmp_path, 'ready', ('sent',))
    with sqlite3.connect(path) as db:
        body = {'message': {'message_id': 3, 'date': 1700000000, 'from': {'id': 12},
                'chat': {'id': 12}, 'media_group_id': 'album', 'photo': [{'file_id': 'late'}]}}
        db.execute("INSERT INTO pending(bot,uid,payload,state) VALUES(99,3,?,'received')", (json.dumps(body),))
        db.execute('INSERT INTO news_plan VALUES(99,3,?)', ('图集迟到或重复成员，需人工核对；不自动重发',))
    result = TelegramView(cfg, butler).read(scope='issues')
    assert len(result['rows']) == 1
    late = result['rows'][0]
    assert late['update_id'] == 3 and late['state'] == 'blocked'
    assert late['package_key'] == 'chat:12:album:album'
    assert late['deliveries'] == []


@pytest.mark.parametrize('album', [True,False])
def test_source_identity_and_persisted_album_alias_project_canonical_package(tmp_path, album):
    from log.telegram_view import TelegramView
    cfg, butler, path = fixture(tmp_path)
    canonical = 'source:album:canonical' if album else 'source:-100123:message:42'
    with sqlite3.connect(path) as db:
        db.execute('UPDATE news_package SET package_key=?', (canonical,))
        db.execute('UPDATE news_bundle_delivery SET package_key=?', (canonical,))
        if album:
            db.execute('INSERT INTO news_package_alias VALUES(99,?,?)', ('chat:12:album:album',canonical))
        for uid, payload in db.execute('SELECT uid,payload FROM pending').fetchall():
            body = json.loads(payload)
            body['message']['forward_origin'] = {'type':'channel','chat':{'id':-100123},'message_id':42}
            if not album:
                del body['message']['media_group_id']
            db.execute('UPDATE pending SET payload=? WHERE uid=?', (json.dumps(body),uid))
    result = TelegramView(cfg, butler).read()
    assert result['status'] == 'ok'
    assert all(row['state']=='pending' and row['package_key']==canonical for row in result['rows'])
