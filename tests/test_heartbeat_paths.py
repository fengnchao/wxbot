"""Heartbeat administration must keep using installation data from any cwd."""
import json
from pathlib import Path

import pytest

from log.config_view import ConfigView


@pytest.fixture(params=['relative', 'absolute', 'default'])
def heartbeat_dashboard(tmp_path, monkeypatch, request):
    import log.server as server

    root = tmp_path / 'installation'
    home = root / 'data'
    cache = home / 'cache'
    cache.mkdir(parents=True)
    wx = root / 'config.wxbot.toml'
    bt = root / 'config.butler.toml'
    wx.write_text('[model]\nbackend="butler"\n', encoding='utf-8')
    files = {'config_file': cache / 'butler_heartbeat.json',
             'state_file': cache / 'butler_heartbeat_state.json',
             'audit_file': cache / 'butler_heartbeat_audit.jsonl'}
    groups = cache / 'butler_groups.json'
    config = ('[agent]\nprovider="codex"\ndata_dir="data"\n'
              '[[contacts]]\nname="A"\nuid="A"\n'
              '[[contacts]]\nname="B"\nuid="B"\n')
    if request.param != 'default':
        def configured(path):
            return str(path) if request.param == 'absolute' else path.relative_to(root).as_posix()
        config += '[heartbeat]\n' + ''.join(
            f'{key}={json.dumps(configured(path))}\n' for key, path in files.items())
        config += '[groups]\nfile=' + json.dumps(configured(groups)) + '\n'
    bt.write_text(config, encoding='utf-8')
    policy = {'role_skill': 'role', 'allowed_skills': ['tool'], 'heartbeat_enabled': True}
    files['config_file'].write_text(json.dumps({'users': {'A': policy, 'B': policy}}), encoding='utf-8')
    files['state_file'].write_text('{"next_run_at":2000000000}', encoding='utf-8')
    files['audit_file'].write_text('{"at":"2026-10-30T18:00:00+08:00",'
                                   '"event":"push_succeeded","contact":"A"}\n', encoding='utf-8')
    groups.write_text('{"groups":{"1":["A"]}}', encoding='utf-8')
    cwd = root / 'log'
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv('BUTLER_CONFIG', str(bt))
    monkeypatch.setenv('WXBOT_CONFIG', str(wx))
    monkeypatch.setattr(server, 'fetch_hermes_skills', lambda *args: [
        {'name': 'role', 'tags': ['butler-role']}, {'name': 'tool', 'tags': []}])

    def call(method, path, body=None):
        handler = server.Handler.__new__(server.Handler)
        handler.home, handler.path = str(home), path
        replies = []
        handler._json = lambda payload, code=200: replies.append((code, payload))
        handler._body = lambda: body
        getattr(handler, 'do_' + method)()
        code, payload = replies[0]
        assert code == 200, payload
        return payload

    view = ConfigView(wx, bt, home, groups_override=groups, log_config_path=root / 'log.toml')
    return call, view, files, groups, policy, cwd


def test_heartbeat_configuration_reads_saved_roles_from_another_cwd(heartbeat_dashboard):
    call, _, _, _, policy, _ = heartbeat_dashboard
    assert call('GET', '/api/heartbeat-config')['policies'] == {'A': policy, 'B': policy}


def test_heartbeat_status_reads_schedule_and_audit_from_another_cwd(heartbeat_dashboard):
    call, _, _, _, _, _ = heartbeat_dashboard
    status = call('GET', '/api/heartbeat-status')
    assert status['enabled_contacts'] == 2
    assert status['next_run_at'] == 2000000000
    assert status['events'][0]['event'] == 'push_succeeded'


def test_heartbeat_save_updates_original_file_and_preserves_other_contacts(heartbeat_dashboard):
    call, _, files, _, policy, cwd = heartbeat_dashboard
    updated = {**policy, 'heartbeat_enabled': False}
    call('POST', '/api/heartbeat-config', {'contact': 'A', **updated})
    saved = json.loads(files['config_file'].read_text(encoding='utf-8'))
    assert saved['users'] == {'A': updated, 'B': policy}
    assert not (cwd / 'data').exists()


def test_configuration_inventory_uses_the_same_role_and_group_files(heartbeat_dashboard):
    _, view, files, groups, _, _ = heartbeat_dashboard
    data = view.read()
    sources = {source['id']: source for source in data['sources']}
    assert sources['policies']['status'] == 'ok'
    assert Path(sources['policies']['path']) == files['config_file']
    assert Path(sources['groups']['path']) == groups
    assert view._raw['policies']['users']['A']['heartbeat_enabled']
    assert view._raw['groups']['groups'] == {'1': ['A']}
    assert not data['warnings']


@pytest.mark.parametrize('agent', ['', '[agent]\nprovider="hermes"\n'])
def test_legacy_hermes_keeps_paths_shared_with_its_runtime(tmp_path, monkeypatch, agent):
    import log.server as server

    config_dir = tmp_path / 'installation'
    config_dir.mkdir()
    runtime_dir = tmp_path / 'runtime'
    home = runtime_dir / 'data'
    cache = home / 'cache'
    cache.mkdir(parents=True)
    wx, bt = config_dir / 'wx.toml', config_dir / 'bt.toml'
    wx.write_text('', encoding='utf-8')
    bt.write_text(agent + '[hermes]\nroot=' + json.dumps(str(home)) + '\n'
                  '[heartbeat]\nconfig_file="data/cache/butler_heartbeat.json"\n'
                  'state_file="data/cache/butler_heartbeat_state.json"\n'
                  'audit_file="data/cache/butler_heartbeat_audit.jsonl"\n'
                  '[groups]\nfile="data/cache/butler_groups.json"\n', encoding='utf-8')
    policy = {'role_skill': 'role', 'allowed_skills': [], 'heartbeat_enabled': True}
    (cache / 'butler_heartbeat.json').write_text(json.dumps({'users': {'A': policy}}), encoding='utf-8')
    (cache / 'butler_heartbeat_state.json').write_text('{"next_run_at":2000000000}', encoding='utf-8')
    (cache / 'butler_heartbeat_audit.jsonl').write_text('{"event":"push_succeeded"}\n', encoding='utf-8')
    (cache / 'butler_groups.json').write_text('{"groups":{"1":["A"]}}', encoding='utf-8')
    monkeypatch.chdir(runtime_dir)
    monkeypatch.setenv('BUTLER_CONFIG', str(bt))
    monkeypatch.setenv('WXBOT_CONFIG', str(wx))
    config = server._load_butler_config()

    assert server.load_heartbeat_config(server.heartbeat_config_path(home, config)) == {'A': policy}
    status = server.load_heartbeat_status(home, config)
    assert status['next_run_at'] == 2000000000
    assert status['events'][0]['event'] == 'push_succeeded'
    view = ConfigView(wx, bt, home, log_config_path=config_dir / 'log.toml')
    data = view.read()
    assert view._raw['policies']['users'] == {'A': policy}
    assert view._raw['groups']['groups'] == {'1': ['A']}
    assert not data['warnings']
