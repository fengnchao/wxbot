"""Offline user administration transport and browser security contracts."""
import importlib.util
import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


@contextmanager
def running(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def request(base, path, payload=None, headers=None):
    req = Request(base + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers or {})
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, json.load(response)


class Registry:
    def list_users(self, **kwargs):
        return {'rows': [], 'total': 0, 'filters': kwargs}

    def create(self, **kwargs):
        return {'user_id': 'fixed-id', 'memory_count': 0, **kwargs}

    def memories(self, binding_id):
        return {'items': [], 'version': 1, 'binding': {'binding_id': binding_id}}

    def change_memory(self, binding_id, key, value, version, delete=False):
        if version != 1:
            from butler.user_registry import VersionConflict
            raise VersionConflict('stale version')
        return {'binding_id': binding_id, 'key': key, 'value': value, 'version': 2, 'delete': delete}

    def audit(self, binding_id, **kwargs):
        return {'rows': [], 'binding_id': binding_id, **kwargs}

    def update_binding(self, binding_id, version, **changes):
        return {'binding_id': binding_id, 'version': version + 1, **changes}


def test_admin_dispatch_filters_typed_actions_and_pagination():
    from butler.user_api import dispatch_user_get, dispatch_user_post
    registry = Registry()
    rows = dispatch_user_get(registry, '/v1/users', {'query': ['Alex'], 'offset': ['50'], 'limit': ['20']})
    assert rows['filters'] == {'query': 'Alex', 'contact': '', 'offset': 50, 'limit': 20}
    assert dispatch_user_get(registry, '/v1/users/memory', {'binding_id': ['b']})['binding']['binding_id'] == 'b'
    result = dispatch_user_post(registry, {'action': 'create', 'channel_type': 'group', 'contact': 'Group', 'nickname': 'Alex', 'avatar': 'image'})
    assert result['user_id'] == 'fixed-id' and result['memory_count'] == 0
    result = dispatch_user_post(registry, {'action': 'memory_delete', 'binding_id': 'b', 'key': 'preference', 'version': 1})
    assert result['delete'] is True


@pytest.mark.parametrize('payload', [[], {'action': 'create', 'contact': ['Group']},
    {'action': 'update', 'binding_id': 'b', 'version': True, 'enabled': True},
    {'action': 'update', 'binding_id': 'b', 'version': 1, 'enabled': 'false'},
    {'action': 'memory_set', 'binding_id': 'b', 'version': 1, 'key': 'a', 'value': {}},
    {'action': 'link', 'binding_id': 'b', 'target_id': 'c', 'version': 1, 'resolutions': {'x': 'replace'}},
    {'action': 'create', 'channel_type': 'dm', 'contact': 'A', 'nickname': 'A', 'avatar': 'x', 'owner': 'victim'}])
def test_invalid_admin_payload_never_reaches_registry(payload):
    from butler.user_api import dispatch_user_post
    with pytest.raises(ValueError):
        dispatch_user_post(object(), payload)


def test_butler_admin_routes_require_server_token_not_tool_capability():
    from butler.server import make_handler
    bot = SimpleNamespace(registry=Registry())
    with running(make_handler(bot, SimpleNamespace(token='server-secret', provider='codex'))) as base:
        for path in ('/v1/users', '/v1/users/memory?binding_id=b', '/v1/users/audit?binding_id=b'):
            assert request(base, path)[0] == 401
            assert request(base, path, headers={'Authorization': 'Bearer tool-capability'})[0] == 401
            assert request(base, path, headers={'Authorization': 'Bearer server-secret'})[0] == 200
        payload = {'action': 'memory_set', 'binding_id': 'b', 'key': 'a', 'value': 'b', 'version': 2}
        assert request(base, '/v1/users', payload, {'Authorization': 'Bearer server-secret'})[0] == 409
        assert request(base, '/v1/users', [], {'Authorization': 'Bearer server-secret'})[0] == 400


def test_log_admin_proxy_requires_same_origin_and_keeps_credentials_server_side(monkeypatch):
    source = Path(__file__).resolve().parents[1] / 'src' / 'dashboard' / 'server.py'
    spec = importlib.util.spec_from_file_location('_user_admin_http', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_load_butler_config', lambda: {'server': {'token': 'never-in-browser'}})
    calls = []
    def proxy(config, path, payload=None):
        calls.append((config, path, payload))
        return 409 if payload else 200, {'error': 'stale'} if payload else {'rows': [], 'total': 0}
    monkeypatch.setattr(module, 'request_user_admin', proxy, raising=False)
    with running(module.Handler) as base:
        valid = {'Content-Type': 'application/json', 'X-Wxbot-User-Action': '1', 'Origin': base}
        payload = {'action': 'memory_delete', 'binding_id': 'b', 'key': 'x', 'version': 1}
        assert request(base, '/api/users', payload)[0] == 403
        assert request(base, '/api/users', payload, {**valid, 'Origin': 'https://bad.example'})[0] == 403
        assert request(base, '/api/users', payload, {**valid, 'Host': 'bad.example:' + base.rsplit(':', 1)[1]})[0] == 403
        assert not calls
        assert request(base, '/api/users', payload, valid)[0] == 409
        status, result = request(base, '/api/users?query=Alex&offset=50')
        assert status == 200 and 'never-in-browser' not in json.dumps(result)
        assert calls[-1][1] == '/v1/users?query=Alex&offset=50'


def test_avatar_and_binding_edit_can_be_applied_atomically():
    from butler.user_api import dispatch_user_post
    result = dispatch_user_post(Registry(), {'action': 'update', 'binding_id': 'b', 'version': 1,
        'nickname': 'Alex2', 'avatar': 'normalized-image'})
    assert result['nickname'] == 'Alex2' and result['avatar'] == 'normalized-image'


def test_real_user_admin_create_memory_link_and_stale_confirmation(tmp_path):
    from butler.business import BusinessStore
    from butler.server import make_handler
    from butler.user_registry import UserRegistry
    from test_user_registry import avatar
    registry = UserRegistry(BusinessStore(tmp_path / 'business.sqlite3'))
    bot = SimpleNamespace(registry=registry)
    auth = {'Authorization': 'Bearer temporary-admin', 'Content-Type': 'application/json'}
    with running(make_handler(bot, SimpleNamespace(token='temporary-admin', provider='codex'))) as base:
        def post(payload):
            return request(base, '/v1/users', payload, auth)
        status, source = post({'action': 'create', 'channel_type': 'group', 'contact': 'Group', 'nickname': 'Alex', 'avatar': avatar()})
        assert status == 200 and source['memory_count'] == 0
        status, target = post({'action': 'create', 'channel_type': 'dm', 'contact': 'Alex', 'nickname': 'Alex', 'avatar': avatar(4)})
        assert status == 200 and target['user_id'] != source['user_id']
        assert post({'action': 'memory_set', 'binding_id': source['binding_id'], 'version': 0, 'key': 'drink', 'value': 'tea'})[0] == 200
        assert post({'action': 'memory_set', 'binding_id': source['binding_id'], 'version': 0, 'key': 'drink', 'value': 'stale'})[0] == 409
        assert post({'action': 'memory_set', 'binding_id': target['binding_id'], 'version': 0, 'key': 'drink', 'value': 'coffee'})[0] == 200
        left = registry.memories(source['binding_id'])
        right = registry.memories(target['binding_id'])
        link = {'action': 'link', 'binding_id': source['binding_id'], 'target_id': target['binding_id'],
            'version': source['version'], 'expected_versions': {'source_memory': left['version'], 'target_memory': right['version'], 'target_binding': target['version']}}
        status, preview = post(link)
        assert status == 200 and preview['requires_confirmation'] and preview['conflicts'][0]['key'] == 'drink'
        registry.change_memory(target['binding_id'], 'drink', 'water', right['version'])
        assert post({**link, 'resolutions': {'drink': 'target'}})[0] == 409
        link['expected_versions']['target_memory'] = registry.memories(target['binding_id'])['version']
        status, linked = post({**link, 'resolutions': {'drink': 'source'}})
        assert status == 200 and linked['user_id'] == target['user_id']
        assert registry.memories(target['binding_id'])['items'][0]['value'] == 'tea'
        assert request(base, '/v1/users/audit?binding_id=' + source['binding_id'], headers=auth)[1]['total'] >= 3


def test_proxy_adds_admin_credential_and_scrubs_upstream_echoes():
    from dashboard.user_admin import request_user_admin
    class Echo(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            assert self.headers['Authorization'] == 'Bearer fixture-secret'
            body = json.dumps({'rows': [], 'token': 'fixture-secret', 'error': 'echo fixture-secret'}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    with running(Echo) as base:
        status, result = request_user_admin({'server': {'port': int(base.rsplit(':', 1)[1]), 'token': 'fixture-secret'}}, '/v1/users')
        assert status == 200 and 'fixture-secret' not in json.dumps(result) and 'token' not in result


def test_proxy_never_forwards_admin_credential_on_redirect():
    from dashboard.user_admin import request_user_admin
    received = []
    class Sink(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            received.append(self.headers.get('Authorization'))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')
    with running(Sink) as destination:
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', destination + '/v1/users')
                self.end_headers()
        with running(Redirect) as base:
            status, _ = request_user_admin({'server': {'port': int(base.rsplit(':', 1)[1]), 'token': 'fixture-secret'}}, '/v1/users')
            assert status >= 400 and not received
