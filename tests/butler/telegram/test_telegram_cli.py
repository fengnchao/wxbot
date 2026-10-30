import json
from pathlib import Path

import pytest


def write_config(tmp_path, enabled=False):
    p = tmp_path / 'config.telegram.toml'
    p.write_text('[telegram]\nenabled = ' + str(enabled).lower() + '\napi_id=123\napi_hash="do-not-print-this"\n', encoding='utf-8')
    return p


def test_help_does_not_require_telethon(monkeypatch, capsys):
    import sys
    monkeypatch.setitem(sys.modules, 'telethon', None)
    from butler.channels.telegram.__main__ import main
    with pytest.raises(SystemExit) as result:
        main(['--help'])
    assert result.value.code == 0
    assert 'status' in capsys.readouterr().out


def test_status_without_state_does_not_create_session_or_database(tmp_path, capsys):
    from butler.channels.telegram.__main__ import main
    p = write_config(tmp_path)
    assert main(['status', '--config', str(p)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'not_started'
    assert not (tmp_path / 'data').exists()


def test_disabled_run_does_not_start_or_create_runtime(tmp_path, capsys):
    from butler.channels.telegram.__main__ import main
    p = write_config(tmp_path)
    assert main(['run', '--config', str(p)]) == 1
    assert not (tmp_path / 'data').exists()
    assert 'do-not-print-this' not in capsys.readouterr().out


def test_status_existing_store_is_readonly_and_never_connects(tmp_path, monkeypatch, capsys):
    from butler.channels.telegram.__main__ import main
    from butler.channels.telegram.store import Store
    from butler.channels.telegram.client import TelegramSource
    p = write_config(tmp_path)
    state = tmp_path / 'data/telegram/relay.sqlite3'
    db = Store(state)
    db.bind(9, -100123, 'zaobaosg', 10)
    db.close()
    monkeypatch.setattr(TelegramSource, 'connect', lambda: pytest.fail('status connected'))
    before = state.read_bytes()
    assert main(['status', '--config', str(p)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['sources'][0]['cursor'] == 10
    assert state.read_bytes() == before
    assert not (tmp_path / 'data/telegram/account.session').exists()


def test_login_only_invokes_local_authorization(tmp_path, monkeypatch, capsys):
    import butler.channels.telegram.__main__ as cli
    p = write_config(tmp_path)
    called = []
    async def fake_login(cfg):
        called.append(cfg.session_path)
        return {'status': 'authorized', 'account_id': 9}
    monkeypatch.setattr(cli, 'login', fake_login)
    assert cli.main(['login', '--config', str(p)]) == 0
    assert called == [tmp_path / 'data/telegram/account']
    assert json.loads(capsys.readouterr().out)['status'] == 'authorized'
    assert not (tmp_path / 'data/telegram/relay.sqlite3').exists()


def test_unexpected_error_is_redacted(tmp_path, monkeypatch, capsys):
    import butler.channels.telegram.__main__ as cli
    p = write_config(tmp_path)
    async def broken(cfg):
        raise RuntimeError('do-not-print-this')
    monkeypatch.setattr(cli, 'login', broken)
    assert cli.main(['login', '--config', str(p)]) == 1
    output = capsys.readouterr().out
    assert 'RuntimeError' in output
    assert 'do-not-print-this' not in output
