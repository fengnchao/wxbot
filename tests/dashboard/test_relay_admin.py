from pathlib import Path

import pytest

from butler.business import BusinessStore
from butler.agent.catalogue import SkillCatalogue
from butler.channels.telegram.relay.settings import Settings
from butler.agent.tools import ToolService
from support.paths import REPO_ROOT


@pytest.fixture
def admin_service(tmp_path):
    catalogue = SkillCatalogue(REPO_ROOT / 'plugins/butler-wechat/skills')
    service = ToolService(BusinessStore(tmp_path / 'business.sqlite3'), catalogue)
    service.relay_settings = Settings(tmp_path / 'relay.toml')
    state = service.relay_settings.read()
    service.relay_settings.update({'admin_contacts': ['Admin'], 'bot_username': 'test_bot', 'bot_id': 123,
                                  'channels': [{'key': 'news', 'name': 'News', 'username': 'daily_news', 'enabled': True}]},
                                 state['version'])
    return service


def token(service, contact='Admin', read_only=False):
    return service.issue(owner=contact, contact=contact, policy={'role_skill': 'butler-companion',
                         'allowed_skills': ['telegram-relay']}, read_only=read_only, request_id='r1')


def test_skill_discovered_with_only_relay_tools(admin_service):
    item = next(s for s in admin_service.catalogue.list() if s['name'] == 'telegram-relay')
    assert set(item['tools']) == {'telegram_relay_status', 'telegram_relay_pause', 'telegram_relay_resume'}


def test_allowlisted_admin_can_pause_resume_with_idempotency(admin_service):
    cap = token(admin_service)
    assert admin_service.call('telegram_relay_resume', {}, cap, 'resume')['enabled']
    assert not admin_service.call('telegram_relay_pause', {}, cap, 'pause')['enabled']
    assert not admin_service.call('telegram_relay_pause', {}, cap, 'pause')['enabled']
    with pytest.raises(ValueError):
        admin_service.call('telegram_relay_resume', {}, cap, '')


def test_policy_does_not_grant_admin_and_revocation_is_immediate(admin_service):
    cap = token(admin_service, 'Other')
    assert not any(d['name'].startswith('telegram_relay_') for d in admin_service.definitions(cap))
    with pytest.raises(PermissionError):
        admin_service.call('telegram_relay_resume', {}, cap, 'x')
    cap = token(admin_service)
    cfg = admin_service.relay_settings.read()
    admin_service.relay_settings.update({'admin_contacts': []}, cfg['version'])
    with pytest.raises(PermissionError):
        admin_service.call('telegram_relay_status', {}, cap, 's')


def test_heartbeat_is_read_only(admin_service):
    cap = token(admin_service, read_only=True)
    names = {d['name'] for d in admin_service.definitions(cap)}
    assert 'telegram_relay_status' in names and 'telegram_relay_resume' not in names
    assert not admin_service.call('telegram_relay_status', {}, cap, 's')['enabled']
    with pytest.raises(PermissionError):
        admin_service.call('telegram_relay_resume', {}, cap, 'r')


def test_local_admin_view_safe_defaults_version_and_status(tmp_path):
    import json
    from dashboard.telegram_relay_admin import TelegramRelayAdmin
    snapshot = tmp_path / 'desktop-status.json'
    snapshot.write_text(json.dumps({'counts': {'pending': 2}, 'token': 'never-return'}), encoding='utf-8')
    admin = TelegramRelayAdmin(tmp_path / 'relay.toml', snapshot)
    payload = admin.read()
    assert not payload['settings']['enabled']
    assert payload['runtime'] == {'counts': {'pending': 2}}
    assert 'never-return' not in json.dumps(payload)
    changed = admin.update({'settings': {'poll_interval': 7}, 'version': payload['version']})
    assert changed['settings']['poll_interval'] == 7
    with pytest.raises(ValueError):
        admin.update({'settings': {}, 'version': changed['version'], 'path': 'arbitrary'})


def test_status_projects_task_identity_without_message_content(tmp_path):
    import json
    from dashboard.telegram_relay_admin import read_status
    path = tmp_path / 'desktop-status.json'
    path.write_text(json.dumps({'ui_hold': True, 'tasks': [{'id': 'a' * 32, 'channel': 'news', 'state': 'uncertain',
        'source_id': '123', 'submitted': 1, 'updated': 42, 'error': 'review',
        'payload': {'text': 'private news'}, 'token': 'private-token'}]}), encoding='utf-8')
    value = read_status(path)
    assert value['ui_hold'] is True
    assert value['tasks'][0]['channel'] == 'news' and value['tasks'][0]['source_id'] == '123'
    assert 'private' not in json.dumps(value)


def test_resolution_proxy_uses_local_authenticated_request_and_scrubs_token():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from dashboard.telegram_relay_admin import request_resolution
    received = []

    class FakeButler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append((self.path, self.headers.get('Authorization'),
                             json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            body = json.dumps({'ok': True, 'detail': 'server-secret', 'token': 'server-secret'}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeButler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = {'server': {'host': 'attacker.example', 'port': server.server_port, 'token': 'server-secret'}}
    payload = {'id': 'a' * 32, 'action': 'forwarded', 'acknowledge': True}
    try:
        status, result = request_resolution(config, payload)
        assert status == 200 and result['ok']
        assert 'server-secret' not in json.dumps(result)
        assert received == [('/v1/telegram-relay/resolve', 'Bearer server-secret', payload)]
        for invalid in ({**payload, 'acknowledge': False}, {**payload, 'path': 'arbitrary'},
                        {**payload, 'action': 'anything'}, {**payload, 'id': 'bad'},
                        {**payload, 'id': 'desktop', 'action': 'forwarded'}):
            assert request_resolution(config, invalid)[0] == 400
        assert len(received) == 1
        assert request_resolution(config, {**payload, 'id': 'desktop', 'action': 'retry'})[0] == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_http_admin_blocks_cross_origin_and_requires_action_header(tmp_path, monkeypatch):
    import json
    import threading
    from http.server import ThreadingHTTPServer
    import requests
    import dashboard.server as dashboard
    from dashboard.telegram_relay_admin import TelegramRelayAdmin
    admin = TelegramRelayAdmin(tmp_path / 'relay.toml', tmp_path / 'desktop-status.json')
    monkeypatch.setattr(dashboard.Handler, '_relay_admin', lambda self: admin, raising=False)
    monkeypatch.setattr(dashboard, '_load_butler_config', lambda: {'server': {'token': 'local-secret'}})
    resolutions = []
    monkeypatch.setattr(dashboard, 'request_relay_resolution',
                        lambda config, payload: (resolutions.append(payload) or (200, {'ok': True})), raising=False)
    server = ThreadingHTTPServer(('127.0.0.1', 0), dashboard.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(base + '/api/telegram-relay', timeout=3)
        assert response.status_code == 200
        current = response.json()
        body = {'settings': {'poll_interval': 7}, 'version': current['version']}
        headers = {'X-Wxbot-Relay-Action': '1', 'Origin': 'https://attacker.example'}
        assert session.post(base + '/api/telegram-relay', json=body, headers=headers, timeout=3).status_code == 403
        assert session.post(base + '/api/telegram-relay', json=body, timeout=3).status_code == 403
        headers['Origin'] = base
        saved = session.post(base + '/api/telegram-relay', json=body, headers=headers, timeout=3)
        assert saved.status_code == 200 and saved.json()['settings']['poll_interval'] == 7
        stale = session.post(base + '/api/telegram-relay', json=body, headers=headers, timeout=3)
        assert stale.status_code == 409
        assert not session.post(base + '/api/telegram-relay', json={'path': 'x'}, headers=headers, timeout=3).ok
        resolve = {'id': 'a' * 32, 'action': 'retry', 'acknowledge': True}
        assert session.post(base + '/api/telegram-relay/resolve', json=resolve, timeout=3).status_code == 403
        assert resolutions == []
        assert session.post(base + '/api/telegram-relay/resolve', json=resolve, headers=headers, timeout=3).status_code == 200
        assert resolutions == [resolve]
    finally:
        session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
