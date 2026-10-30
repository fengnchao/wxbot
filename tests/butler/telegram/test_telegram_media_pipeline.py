from io import BytesIO
import json
from types import SimpleNamespace

from PIL import Image
import pytest
import requests


def image_bytes():
    out = BytesIO()
    Image.new('RGB', (2, 2)).save(out, 'PNG')
    return out.getvalue()


def message(mid=1, group=None, caption=None):
    result = {'message_id': mid, 'date': 1700000000, 'from': {'id': 12},
              'chat': {'id': 12, 'type': 'private'},
              'photo': [{'file_id': 'photo-' + str(mid), 'file_size': 80, 'width': 2, 'height': 2}]}
    if group:
        result['media_group_id'] = group
    if caption:
        result['caption'] = caption
    return result


def setup(tmp_path, *, push=None):
    from butler.channels.telegram.bot.queue import Queue
    from butler.channels.telegram.bot.news import NewsRelay
    groups = tmp_path / 'groups.json'
    groups.write_text('{"groups":{"1":["A","A","B"]}}', encoding='utf-8')
    queue = Queue(tmp_path / 'queue.sqlite3')
    config = SimpleNamespace(group_file_path=lambda: groups)
    calls, prepared = [], []
    def prepare(msg):
        prepared.append(msg['message_id'])
        return [{'kind': 'image', 'media_id': str(msg['message_id']) * 32}]
    def send(cfg, who, items, request_id):
        calls.append((who, items, request_id))
        return push(who) if push else {'state': 'sent', 'reason': 'confirmed'}
    clock = [100.0]
    settings = SimpleNamespace(enabled=True, include_images=True, include_text=True,
        album_quiet_seconds=2, max_album_wait=10)
    relay = NewsRelay(queue, 99, config, (12,), lambda s: None,
                      media=SimpleNamespace(prepare=prepare), bundle_push=send,
                      relay_settings=lambda: settings, clock=lambda: clock[0])
    def ingest(uid, msg):
        queue.ingest(99, {'update_id': uid}, msg, now=clock[0])
        queue.finish(99, uid, 'received')
    return relay, queue, ingest, clock, calls, prepared, groups


def test_photo_only_is_a_real_image_package_and_recipient_list_is_deduplicated(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    ingest(1, message())
    assert relay.expand_once()
    assert relay.deliver_once() and relay.deliver_once()
    assert not relay.deliver_once()
    assert [who for who, _, _ in calls] == ['A', 'B']
    assert all(items[-1] == {'kind': 'image', 'media_id': '1' * 32} for _, items, _ in calls)
    assert prepared == [1]


def test_album_waits_groups_in_message_order_and_never_replays_late_or_duplicate_members(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    ingest(1, message(2, 'album', 'second'))
    assert not relay.expand_once()
    clock[0] += 1
    ingest(2, message(1, 'album', 'first'))
    ingest(3, message(1, 'album', 'first'))
    clock[0] += 2.1
    assert relay.expand_once()
    assert relay.deliver_once() and relay.deliver_once()
    assert prepared == [1, 2]
    items = calls[0][1]
    assert [item['media_id'] for item in items if item['kind'] == 'image'] == ['1' * 32, '2' * 32]
    ingest(4, message(3, 'album', 'late'))
    assert relay.expand_once()
    assert not relay.deliver_once()
    assert len(calls) == 2
    with queue.db() as db:
        assert '迟到' in db.execute('SELECT reason FROM news_plan WHERE uid=4').fetchone()[0]


def test_unknown_package_is_not_replayed_and_unsubscribe_revokes_pending_delivery(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path,
        push=lambda who: {'state': 'uncertain', 'reason': 'timeout'})
    ingest(1, message())
    relay.expand_once()
    assert relay.deliver_once()
    relay.recover()
    groups.write_text('{"groups":{"1":["A"]}}', encoding='utf-8')
    assert relay.deliver_once()
    assert not relay.deliver_once()
    assert [who for who, _, _ in calls] == ['A']


def test_failed_album_image_creates_no_partial_deliveries(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    def bad(msg):
        raise ValueError('bad image')
    relay.media.prepare = bad
    ingest(1, message())
    assert relay.expand_once()
    assert not relay.deliver_once()
    with queue.db() as db:
        assert db.execute('SELECT state FROM news_package').fetchone()[0] == 'media_failed'


def test_media_getfile_checks_path_bytes_and_uploads_only_validated_image():
    from butler.channels.telegram.bot.media import TelegramMedia
    calls = []
    class API:
        def call(self, method, **params):
            assert method == 'getFile' and params == {'file_id': 'photo-1'}
            return {'file_path': 'photos/file_1.png', 'file_size': len(image_bytes())}
        def download(self, path):
            assert path == 'photos/file_1.png'
            return image_bytes()
    client = TelegramMedia(API(), None, upload=lambda data: calls.append(data) or {'media_id': 'a' * 32})
    assert client.prepare(message()) == [{'kind': 'image', 'media_id': 'a' * 32}]
    assert calls == [image_bytes()]


@pytest.mark.parametrize('path', ['../secret', 'http://evil/x', '/absolute', 'photos/../secret', 'photos\\secret'])
def test_media_getfile_rejects_untrusted_paths_before_download(path):
    from butler.channels.telegram.bot.media import TelegramMedia
    class API:
        def call(self, *args, **kwargs):
            return {'file_path': path}
        def download(self, path):
            pytest.fail('untrusted download')
    with pytest.raises(ValueError):
        TelegramMedia(API(), None, upload=lambda data: {}).prepare(message())


def test_bundle_push_requires_recipient_and_package_receipt_and_never_retries(monkeypatch):
    from butler.delivery.push_client import push_news_bundle
    calls = []
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            calls.append(kwargs['json'])
            raise requests.Timeout('private-token')
    monkeypatch.setattr('butler.delivery.push_client.requests.Session', Session)
    cfg = SimpleNamespace(token='private-token', host='127.0.0.1', port=8770, wxbot_timeout=120)
    assert push_news_bundle(cfg, 'A', [{'kind': 'image', 'media_id': 'a' * 32}], 'source1')['state'] == 'uncertain'
    assert calls == [{'contact': 'A', 'items': [{'kind': 'image', 'media_id': 'a' * 32}], 'request_id': 'source1'}]


def test_identity_snapshot_contains_only_confirmed_public_bot_identity(tmp_path):
    from butler.channels.telegram.bot.service import publish_identity
    publish_identity(tmp_path, {'id': 99, 'is_bot': True, 'username': 'CurrentBot', 'token': 'private'})
    result = json.loads((tmp_path / 'bot-identity.json').read_text(encoding='utf-8'))
    assert set(result) == {'bot_id', 'username', 'at'}
    assert result['bot_id'] == 99 and result['username'] == 'CurrentBot'
    with pytest.raises(ValueError):
        publish_identity(tmp_path, {'id': 1, 'is_bot': False, 'username': 'person'})


def test_album_max_wait_does_not_allow_incomplete_butler_ingress_to_look_complete(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    ingest(1, message(1, 'album'))
    queue.ingest(99, {'update_id': 2}, message(2, 'album'), now=100)
    clock[0] = 111
    assert relay.expand_once()
    assert not relay.deliver_once()
    with queue.db() as db:
        assert db.execute('SELECT state FROM news_package').fetchone()[0] == 'media_failed'


def test_album_quiet_wait_uses_all_members_and_does_not_freeze_other_sources(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    ingest(1, message(1, 'album'))
    ingest(2, message(2))
    assert relay.expand_once()
    assert prepared == [2]


def test_recovery_holds_preparing_packages_and_sending_receipts(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    ingest(1, message())
    relay.expand_once()
    with queue.db() as db:
        db.execute("UPDATE news_package SET state='preparing'")
        db.execute("UPDATE news_bundle_delivery SET state='sending'")
    relay.recover()
    assert not relay.deliver_once()
    with queue.db() as db:
        assert db.execute('SELECT state FROM news_package').fetchone()[0] == 'media_failed'
        assert {r[0] for r in db.execute('SELECT state FROM news_bundle_delivery')} == {'uncertain'}


def test_missing_media_setting_retains_legacy_text_path(tmp_path):
    from butler.channels.telegram.bot.news import NewsRelay
    from butler.channels.telegram.bot.queue import Queue
    group = tmp_path / 'groups.json'
    group.write_text('{"groups":{"1":["A"]}}', encoding='utf-8')
    queue = Queue(tmp_path / 'queue.db')
    msg = message(caption='legacy text')
    queue.ingest(99, {'update_id': 1}, msg)
    queue.finish(99, 1, 'received')
    calls = []
    relay = NewsRelay(queue, 99, SimpleNamespace(group_file_path=lambda: group), (12,), lambda s: None,
        push=lambda cfg, who, text: calls.append(text) or {'state': 'sent', 'reason': 'ok'})
    assert relay.expand_once() and relay.deliver_once()
    assert 'legacy text' in calls[0]
    assert '当前仅转发文字和链接' in calls[0]


def test_forward_header_uses_original_channel_publish_time():
    from butler.channels.telegram.bot.news import format_news
    msg = message(caption='news')
    msg['forward_origin'] = {'type': 'channel', 'date': 0,
        'chat': {'id': -1001, 'title': 'Source', 'username': 'source'}, 'message_id': 8}
    parts, _ = format_news(msg, media_enabled=True)
    assert '1970-01-01 08:00' in parts[0]
    assert 'https://t.me/source/8' in parts[0]


@pytest.mark.parametrize('payload,state', [
    ({'ok': True, 'contact': 'A', 'request_id': 'source1'}, 'sent'),
    ({'ok': True, 'contact': 'A', 'request_id': 'wrong'}, 'uncertain'),
    ({'ok': True, 'contact': 'B', 'request_id': 'source1'}, 'uncertain'),
    ({'ok': 1, 'contact': 'A', 'request_id': 'source1'}, 'uncertain'),
    ([], 'uncertain'),
])
def test_bundle_receipt_matches_recipient_and_stable_package(monkeypatch, payload, state):
    from butler.delivery.push_client import push_news_bundle
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert url == 'http://127.0.0.1:8770/v1/push/bundle'
            assert kwargs['allow_redirects'] is False and self.trust_env is False
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(payload).encode()
            return response
    monkeypatch.setattr('butler.delivery.push_client.requests.Session', Session)
    cfg = SimpleNamespace(token='private-token', host='127.0.0.1', port=8770, wxbot_timeout=120)
    assert push_news_bundle(cfg, 'A', [{'kind': 'image', 'media_id': 'a' * 32}], 'source1')['state'] == state


def test_download_stops_stream_at_size_limit_and_never_exposes_token():
    from butler.channels.telegram.bot.service import BotAPI, TelegramError
    from butler.delivery.media import MAX_BYTES
    api = BotAPI(SimpleNamespace(token='private-secret', proxy_url=''))
    class Response:
        status_code = 200
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size):
            yield b'x' * MAX_BYTES
            yield b'x'
            pytest.fail('unbounded download')
    class Session:
        def get(self, url, **kwargs):
            assert kwargs['stream'] is True and kwargs['allow_redirects'] is False
            return Response()
    api.session.close()
    api.session = Session()
    with pytest.raises(ValueError):
        api.download('photos/a.jpg')
    assert 'private-secret' not in str(TelegramError(401, method='download'))


def test_push_bundle_waits_for_whole_matching_wxbot_receipt(monkeypatch):
    from butler.delivery.push import push_bundle_to_wxbot
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"ok":true,"contact":"A","request_id":"source1","detail":"sent"}'
    def opening(request, **kwargs):
        calls.append(json.loads(request.data))
        assert request.full_url == 'http://127.0.0.1:8765/send-bundle'
        return Response()
    monkeypatch.setattr('butler.delivery.push.urllib.request.urlopen', opening)
    cfg = SimpleNamespace(wxbot_url='http://127.0.0.1:8765', wxbot_token='secret', wxbot_timeout=120)
    assert push_bundle_to_wxbot(cfg, 'A', [{'kind': 'image', 'media_id': 'a' * 32}], 'source1') == (True, 'sent')
    assert calls[0]['wait'] is True and calls[0]['request_id'] == 'source1'


def test_disabled_text_does_not_send_header_for_text_only_message(tmp_path):
    from butler.channels.telegram.bot.news import format_news
    msg = message()
    del msg['photo']
    msg['text'] = 'disabled text'
    parts, reason = format_news(msg, media_enabled=True, include_text=False)
    assert parts == [] and reason


def test_unsupported_media_has_explicit_operator_reason(tmp_path):
    from butler.channels.telegram.bot.media import TelegramMedia
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    relay.media = TelegramMedia(None, None)
    msg = message()
    del msg['photo']
    msg['video'] = {'file_id': 'video'}
    ingest(1, msg)
    relay.expand_once()
    with queue.db() as db:
        state, reason = db.execute('SELECT state,reason FROM news_package').fetchone()
    assert state == 'media_failed' and '暂不支持' in reason


def test_binary_registration_is_authenticated_local_and_redacts_network_errors(monkeypatch):
    from butler.channels.telegram.bot.media import TelegramMedia
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def json(self): return {'media_id': 'a' * 32}
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert url == 'http://127.0.0.1:8770/v1/media'
            assert kwargs['data'] == image_bytes()
            assert kwargs['headers']['Authorization'] == 'Bearer private-token'
            assert kwargs['allow_redirects'] is False and self.trust_env is False
            return Response()
    class API:
        def call(self, *args, **kwargs): return {'file_path': 'photos/1.png'}
        def download(self, path): return image_bytes()
    monkeypatch.setattr('butler.channels.telegram.bot.media.requests.Session', Session)
    cfg = SimpleNamespace(token='private-token', host='127.0.0.1', port=8770)
    assert TelegramMedia(API(), cfg).prepare(message()) == [{'kind': 'image', 'media_id': 'a' * 32}]


def test_bot_config_uses_shared_settings_beside_explicit_bot_config(tmp_path):
    from butler.channels.telegram.bot.config import load
    path = tmp_path / 'bot.toml'
    path.write_text('[telegram_bot]\ntoken="123456:abcdefghijklmnopqrstuvwx"\nallowed_user_ids=[12]\n', encoding='utf-8')
    assert load(path).relay_config == tmp_path / 'config.telegram-relay.toml'


def test_shared_text_switch_applies_when_media_capability_is_disabled(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    relay.relay_settings = lambda: SimpleNamespace(include_images=False, include_text=False,
                                                   include_source=True, include_time=True)
    msg = message()
    del msg['photo']
    msg['text'] = 'do not deliver'
    ingest(1, msg)
    assert relay.expand_once()
    assert not relay.deliver_once()
    with queue.db() as db:
        assert db.execute('SELECT count(*) FROM news_delivery').fetchone()[0] == 0


def with_source(msg, source_id=42):
    msg['forward_origin'] = {'type': 'channel', 'chat': {'id': -100123, 'username': 'source'},
                             'message_id': source_id, 'date': 1700000000}
    return msg


def test_same_original_channel_message_relayed_twice_creates_one_recipient_package(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    ingest(1, with_source(message(1)))
    relay.expand_once()
    while relay.deliver_once(): pass
    ingest(2, with_source(message(2)))
    relay.expand_once()
    assert not relay.deliver_once()
    assert [who for who, _, _ in calls] == ['A','B']
    with queue.db() as db:
        assert db.execute('SELECT count(*) FROM news_package').fetchone()[0] == 1


def test_relayed_album_deduplicates_original_members_and_sorts_by_original_message(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    ingest(1, with_source(message(1, 'first-forward'), 42))
    ingest(2, with_source(message(2, 'first-forward'), 41))
    clock[0] += 3
    relay.expand_once()
    while relay.deliver_once(): pass
    assert prepared == [2,1]
    ingest(3, with_source(message(3, 'second-forward'), 41))
    ingest(4, with_source(message(4, 'second-forward'), 42))
    clock[0] += 3
    relay.expand_once()
    assert not relay.deliver_once() and len(calls) == 2
    assert prepared == [2,1]


def test_partially_overlapping_original_album_is_held_without_repeating_known_images(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    ingest(1, with_source(message(1, 'first'), 41))
    ingest(2, with_source(message(2, 'first'), 42))
    clock[0] += 3
    relay.expand_once()
    while relay.deliver_once(): pass
    ingest(3, with_source(message(3, 'partial'), 42))
    ingest(4, with_source(message(4, 'partial'), 43))
    clock[0] += 3
    relay.expand_once()
    assert not relay.deliver_once() and len(calls) == 2
    with queue.db() as db:
        assert db.execute("SELECT count(*) FROM news_package WHERE state='media_failed'").fetchone()[0] == 1


def test_disabling_text_after_expansion_blocks_immutable_caption_package(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    ingest(1, message(caption='previously authorized caption'))
    relay.expand_once()
    with queue.db() as db:
        before = db.execute('SELECT request_id FROM news_bundle_delivery ORDER BY id').fetchall()
        content = db.execute('SELECT items FROM news_package').fetchone()[0]
    relay.relay_settings = lambda: SimpleNamespace(include_images=True, include_text=False)
    assert relay.deliver_once() and relay.deliver_once()
    assert not relay.deliver_once() and calls == []
    with queue.db() as db:
        assert {r[0] for r in db.execute('SELECT state FROM news_bundle_delivery')} == {'blocked'}
        assert db.execute('SELECT request_id FROM news_bundle_delivery ORDER BY id').fetchall() == before
        assert db.execute('SELECT items FROM news_package').fetchone()[0] == content


def test_image_only_policy_at_expansion_can_send_without_any_cached_text(tmp_path):
    relay, queue, ingest, clock, calls, prepared, groups = setup(tmp_path)
    relay.relay_settings = lambda: SimpleNamespace(include_images=True, include_text=False)
    ingest(1, message(caption='disabled caption'))
    relay.expand_once()
    assert relay.deliver_once() and relay.deliver_once()
    assert len(calls) == 2
    assert all(items == [{'kind':'image','media_id':'1'*32}] for _,items,_ in calls)
