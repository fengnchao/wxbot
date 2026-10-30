"""Per-contact forwarding uses temporary data and an ephemeral fake HTTP receiver."""
import json
import threading
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
import tomlkit

from butler.config import load
from dashboard.config_view import ConfigView


@contextmanager
def receiver(status=204):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            received.append((self.path, self.headers['Content-Type'], json.loads(body)))
            self.send_response(status)
            if status == 302:
                self.send_header('Location', '/unexpected')
            self.end_headers()
            if status != 204:
                self.wfile.write(b'not JSON; never a WeChat reply')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1/message', received
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


def route(url, **extra):
    return {'contact': '101', 'url': url, 'code': '101', **extra}


def install_routes(home, tmp_path, rows):
    path = tmp_path / 'routes.toml'
    path.write_text(tomlkit.dumps({'message_routes': rows}), encoding='utf-8')
    # Keep the fake model, pending queue and temporary storage from make_home.
    home.cfg.message_routes = getattr(load(path), 'message_routes', ())


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('status', [200, 204])
@pytest.mark.parametrize('provider', ['codex', 'hermes'])
def test_matched_contact_forwards_exact_body_without_model_or_reply(make_home, tmp_path, streaming, status, provider):
    home = make_home()
    # If forwarding accidentally loads a Codex policy/model, this fake home has
    # neither a Codex catalogue nor an SDK worker and the request will fail.
    home.cfg.provider = provider
    with receiver(status) as (url, received):
        install_routes(home, tmp_path, [route(url)])
        events = []
        result = home.butler.handle('101', '你好\n第二行', msg_id='batch-1',
                                   **({'on_event': events.append} if streaming else {}))
    assert received == [('/v1/message', 'application/json', {'code': '101', 'text': '你好\n第二行'})], result.meta
    assert result.reply is None and result.actions == []
    assert result.meta['forwarded'] is True and result.meta['msg_id'] == 'batch-1'
    assert home.log() == []  # Neither pending recognition nor a model call.
    if streaming:
        assert events[-1]['type'] == 'complete'
        assert not any(e['type'] == 'answer_delta' for e in events)
        assert all(e['provider'] == 'http' for e in events if e['type'] == 'backend')


def test_matching_route_bypasses_butler_reset_command(make_home, tmp_path):
    home = make_home()
    with receiver() as (url, received):
        install_routes(home, tmp_path, [route(url)])
        result = home.butler.handle('101', '/new')
    assert received[0][2] == {'code': '101', 'text': '/new'}
    assert result.reply is None and home.log() == []


def test_forwarding_bypasses_unrelated_legacy_memory_conflict(make_home, tmp_path):
    from butler.backends.codex import owner_key
    from butler.business import BusinessStore
    from butler.identity.user_registry import UserRegistry
    home = make_home()
    registry = UserRegistry(BusinessStore(tmp_path / 'business.sqlite3'))
    user = registry.resolve('101', 'dm')
    legacy_owner = owner_key(home.cfg.contacts.get('101'))
    registry.store.set_memory(legacy_owner, 'preference', '旧资料')
    registry.store.set_memory(user['memory_owner'], 'preference', '新资料')
    home.butler.registry = registry
    home.cfg.provider = 'codex'
    with receiver() as (url, received):
        install_routes(home, tmp_path, [route(url)])
        result = home.butler.handle('101', '你好')
    assert len(received) == 1 and result.meta['forwarded'] is True
    assert registry.memories(user['binding_id'])['items'][0]['value'] == '新资料'
    with registry.store.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM user_legacy_owners').fetchone()[0] == 0
    assert home.log() == []


@pytest.mark.parametrize('mode', ['unmatched', 'disabled', 'group'])
def test_nonmatching_route_preserves_model_path(make_home, tmp_path, mode):
    home = make_home(pending_items=[], replies=['模型回复'])
    with receiver() as (url, received):
        row = route(url)
        if mode == 'unmatched':
            row['contact'] = '别的联系人'
        if mode == 'disabled':
            row['enabled'] = False
        install_routes(home, tmp_path, [row])
        result = home.butler.handle('101', '你好', channel_type='group' if mode == 'group' else 'dm')
    assert received == []
    assert result.reply == '模型回复'
    assert 'chat' in home.log()


@pytest.mark.parametrize('status', [302, 400, 500])
def test_failed_or_redirected_forward_never_calls_model_or_replies(make_home, tmp_path, status):
    home = make_home()
    with receiver(status) as (url, received):
        install_routes(home, tmp_path, [route(url)])
        result = home.butler.handle('101', '你好')
    assert len(received) == 1
    assert result.reply is None and result.meta['forwarded'] is False
    assert result.meta['reply_complete'] is False and result.meta['retry_safe'] is False
    assert result.meta['http_status'] == status
    assert home.log() == []


def test_timeout_is_recorded_without_retry_fallback_or_secret_leak(make_home, tmp_path, monkeypatch):
    home = make_home()
    install_routes(home, tmp_path, [route('http://127.0.0.1:1/v1/message', timeout=0.25)])
    calls = []

    def timeout(url, **kwargs):
        calls.append(kwargs)
        raise requests.Timeout('private-response-secret')

    monkeypatch.setattr(requests, 'post', timeout)
    result = home.butler.handle('101', '你好')
    assert len(calls) == 1 and calls[0]['timeout'] == 0.25
    assert result.reply is None and result.meta['retry_safe'] is False
    assert 'private-response-secret' not in json.dumps(result.as_dict())
    assert home.log() == []


@pytest.mark.parametrize('rows', [
    {}, [route('file:///tmp/message')], [route('http://user:secret@localhost/message')],
    [route('http://localhost/message', contact='')], [route('http://localhost/message', code='')],
    [route('http://localhost/message', code=101)], [route('http://localhost/message', enabled='true')],
    [route('http://localhost/message', timeout=0)], [route('http://localhost/message', timeout=float('inf'))],
    [route('http://localhost/message'), route('http://localhost/other')],
    [route('http://localhost/message', typo='ignored')],
])
def test_invalid_routes_are_rejected_on_load(tmp_path, rows):
    path = tmp_path / 'routes.toml'
    path.write_text(tomlkit.dumps({'message_routes': rows}), encoding='utf-8')
    with pytest.raises(ValueError, match='message_routes'):
        load(path)


def test_dashboard_offers_json_routes_and_validates_before_saving(tmp_path):
    from dashboard.config_editor import ConfigEditor
    wx, bt = tmp_path / 'wx.toml', tmp_path / 'bt.toml'
    wx.write_text('[model]\nbackend="butler"\n', encoding='utf-8')
    bt.write_text('[agent]\nprovider="hermes"\n', encoding='utf-8')
    view = ConfigView(wx, bt, tmp_path, repo_root=tmp_path, log_config_path=tmp_path / 'log.toml')
    data = view.read()
    rows = [r for s in data['sections'] for r in s['rows'] if r.get('key') == 'butler.message_routes']
    assert len(rows) == 1 and rows[0]['widget'] == 'json'

    def patch(value):
        latest = view.read()
        version = next(s['version'] for s in latest['sources'] if s['id'] == 'butler')
        return {'source': 'butler', 'version': version, 'acknowledge': True,
                'changes': [{'path': ['message_routes'], 'op': 'set', 'value': value}]}

    editor = ConfigEditor(view)
    before = bt.read_bytes()
    with pytest.raises(ValueError, match='message_routes'):
        editor.save(patch([route('javascript:invalid')]))
    assert bt.read_bytes() == before
    result = editor.save(patch([route('http://127.0.0.1:8790/v1/message')]))
    assert result['restart'] == ['Butler']
    loaded = load(bt)
    assert loaded.message_routes[0].code == '101'
    editor.save(patch([]))
    assert load(bt).message_routes == ()


@pytest.mark.parametrize('typing_mode', ['chunked', 'full', 'streaming'])
@pytest.mark.parametrize('status', [204, 500])
def test_forwarding_through_butler_transport_and_queue_never_enqueues_wechat_reply(
        make_home, start_server, tmp_path, typing_mode, status):
    from wxbot.processor.butler import ButlerProcessor
    from wxbot.processor.router import Router
    from wxbot.queue_store import Incoming, QueueStore
    from wxbot.queue_worker import ModelWorker
    home = make_home()
    with receiver(status) as (url, received):
        install_routes(home, tmp_path, [route(url)])
        butler_url = start_server(home.butler, home.cfg)
        processor = ButlerProcessor({'url': butler_url, 'token': 't0ken'}, raise_errors=True)
        with closing(QueueStore(':memory:')) as store:
            store.capture('101', [], [Incoming('你好')], now=0)
            worker = ModelWorker(store, Router(processor), quiet=0, max_wait=1,
                                 typing_mode=typing_mode, clock=lambda: 2)
            assert worker.process_once()
            assert store.records('outbox') == []
            batch = store.records('batches')[0]
            assert batch['state'] == ('done' if status == 204 else 'uncertain'), batch
            assert not worker.process_once(), 'a forwarded request must not replay'
    assert len(received) == 1 and home.log() == []
