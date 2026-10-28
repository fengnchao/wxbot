from contextlib import closing

import pytest

from wxbot.queue_store import Incoming, QueueStore


def test_selected_message_reads_complete_incoming_and_all_reply_parts_without_changing_queue(tmp_path):
    from log.workflow_content import read_content
    path = tmp_path/'queue.sqlite3'
    text = '收到的长消息🙂\n' * 80 + '收件末尾'
    first, second = '完整回复第一段\n' * 70, '第二段🙂\n' * 70 + '回复末尾'
    with closing(QueueStore(path)) as store:
        ids = store.capture('A', [], [Incoming(text)], now=1)
        store.prepare(quiet=0, max_wait=10, prefix='/', now=2)
        batch = store.claim_batch(now=2)
        store.finish_batch_parts(batch.id, (first, second), reply_text=first+second, now=3)
        before = [store.records(table) for table in ('inbox','batches','outbox')]
        detail = read_content(path, None, batch.id)
        assert detail == {'id':batch.id, 'kind':'batch', 'text':text, 'reply_text':first+second}
        assert read_content(path, None, 'inbox:'+str(ids[0]))['text'] == text
        assert [store.records(table) for table in ('inbox','batches','outbox')] == before


def test_standalone_push_content_is_complete_and_missing_records_do_not_create_a_database(tmp_path):
    from log.workflow_content import read_content
    path = tmp_path/'queue.sqlite3'
    assert read_content(path, None, 'push:missing') is None
    assert not path.exists()
    with closing(QueueStore(path)) as store:
        text = '新闻正文\n' * 100 + '最后一行'
        record_id = store.enqueue_delivery('A', text, now=1)
        assert read_content(path, None, 'push:'+record_id) == {
            'id':'push:'+record_id, 'kind':'push', 'text':text, 'reply_text':''}
        assert read_content(path, None, 'push:missing') is None


def test_telegram_full_caption_is_loaded_by_exact_bot_and_update_id(tmp_path):
    from log.workflow_content import read_content
    from butler.telegram_bot.queue import Queue
    queue = Queue(tmp_path/'telegram'/'relay.sqlite3')
    caption = '图片说明🙂\n' * 80 + '说明末尾 fake-telegram-token'
    queue.ingest(99, {'update_id':7}, {'message_id':1, 'from':{'id':12},
                                    'chat':{'id':12,'type':'private'}, 'caption':caption})
    config = tmp_path/'telegram.toml'
    config.write_text('[telegram_bot]\nstate_dir="telegram"\ntoken="fake-telegram-token"\n', encoding='utf-8')
    before = queue.path.read_bytes()
    assert read_content(tmp_path/'absent.db', config, 'tg:99:7') == {
        'id':'tg:99:7', 'kind':'telegram', 'text':caption.replace('fake-telegram-token','[密钥已隐藏]'), 'reply_text':''}
    assert read_content(tmp_path/'absent.db', config, 'tg:98:7') is None
    assert queue.path.read_bytes() == before


@pytest.mark.parametrize('record_id', ['', 'inbox:abc', 'tg:99:7:extra', 'push:../secret', "x' OR 1=1 --"])
def test_message_content_rejects_non_identifiers_and_never_opens_client_paths(tmp_path, record_id):
    from log.workflow_content import read_content
    with pytest.raises(ValueError):
        read_content(tmp_path/'missing.sqlite3', None, record_id)
    assert list(tmp_path.iterdir()) == []


def test_content_http_route_returns_complete_body_and_clear_missing_result(tmp_path):
    from urllib.parse import urlencode
    from log.config_view import ConfigView
    from log.server import Handler
    path = tmp_path/'queue.sqlite3'
    with closing(QueueStore(path)) as store:
        text = ('完整正文\n' * 100 + 'Title\nhttps://example.com/a?x=中文%20保留\nMore text\nEnd\n'
                'https://user:pass@example.com/?%74oken=secret-value&x=中文#password=private\n'
                'test-config-secret')
        expected = text.replace('user:pass@','***@').replace('secret-value','***').replace('private','***').replace('test-config-secret','***')
        record_id = 'push:'+store.enqueue_delivery('A', text, now=1)
        wxconfig, btconfig = tmp_path/'wxbot.toml', tmp_path/'butler.toml'
        wxconfig.write_text('[queue]\ndatabase="queue.sqlite3"\n', encoding='utf-8')
        btconfig.write_text('[server]\ntoken="test-config-secret"\n', encoding='utf-8')

        def get(identifier):
            handler = Handler.__new__(Handler)
            handler.path = '/api/workflow-content?'+urlencode({'id':identifier})
            handler._config_view = lambda: ConfigView(wxconfig, btconfig, tmp_path/'home',
                repo_root=tmp_path, log_config_path=tmp_path/'log.toml')
            results = []
            handler._json = lambda data, code=200: results.append((code, data))
            handler.do_GET()
            return results[0]

        status, detail = get(record_id)
        assert status == 200 and detail['status'] == 'ok' and detail['text'] == expected
        assert get('push:deleted')[0] == 404
        assert get('inbox:invalid')[0] == 400
