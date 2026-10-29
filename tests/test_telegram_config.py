from pathlib import Path

import pytest


def write_config(tmp_path, extra='', enabled='true'):
    path = tmp_path / 'config.telegram.toml'
    path.write_text('[telegram]\nenabled = ' + enabled + '\napi_id = 123\napi_hash = "test-secret"\nsources = ["@zaobaosg"]\n' + extra, encoding='utf-8')
    return path


def test_relative_paths_use_config_directory_and_secrets_are_not_repr(tmp_path, monkeypatch):
    from butler.telegram.config import load
    path = write_config(tmp_path, 'session = "private/account"\nstate_dir = "private/state"\n')
    monkeypatch.chdir(tmp_path.parent)
    cfg = load(path)
    assert cfg.session_path == tmp_path / 'private/account'
    assert cfg.state_path == tmp_path / 'private/state'
    assert cfg.butler_config == tmp_path / 'config.butler.toml'
    assert 'test-secret' not in repr(cfg)
    assert cfg.sources == ('zaobaosg',)


@pytest.mark.parametrize('extra,enabled', [('', '1'), ('scan_interval = 0\n', 'true'), ('scan_interval = true\n', 'true'), ('session = ""\n', 'true')])
def test_invalid_config_is_rejected(tmp_path, extra, enabled):
    from butler.telegram.config import load
    with pytest.raises(ValueError):
        load(write_config(tmp_path, extra, enabled))


def test_invalid_or_empty_source_and_missing_config_are_rejected(tmp_path):
    from butler.telegram.config import load
    path = write_config(tmp_path)
    for value in ('[]', '["../../secret"]', '["https://wrong.example/channel"]', '"zaobaosg"'):
        path.write_text('[telegram]\nsources = ' + value, encoding='utf-8')
        with pytest.raises(ValueError):
            load(path)
    with pytest.raises(ValueError):
        load(tmp_path / 'missing.toml')


def test_generated_defaults_are_disabled_and_contain_no_credentials(tmp_path):
    from butler.telegram.config import load
    import tomlkit
    from butler.defaults import telegram_defaults
    path = tmp_path / 'config.telegram.toml'
    path.write_text(tomlkit.dumps(telegram_defaults()), encoding='utf-8')
    cfg = load(path)
    assert cfg.enabled is False
    assert not cfg.api_id and not cfg.api_hash


def test_proxy_is_explicit_and_redacted(tmp_path):
    from butler.telegram.config import load
    cfg = load(write_config(tmp_path, '\n[proxy]\ntype = "socks5"\nhost = "127.0.0.1"\nport = 1080\npassword = "proxy-secret"\n'))
    assert cfg.proxy['addr'] == '127.0.0.1'
    assert cfg.proxy['port'] == 1080
    assert 'proxy-secret' not in repr(cfg)
