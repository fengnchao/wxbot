import os
from pathlib import Path


def test_log_relative_sources_follow_loaded_config_not_cwd(tmp_path, monkeypatch):
    from dashboard.settings import load_settings
    root=tmp_path/'install'; root.mkdir()
    path=root/'config.log.toml'
    path.write_text('[sources]\nhome="data"\nwxbot_config="config.wxbot.toml"\nbutler_config="config.butler.toml"\ngroups_file="data/cache/groups.json"\n',encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('LOG_CONFIG',str(path))
    result=load_settings()
    assert result['sources']['home']==str(root/'data')
    assert result['sources']['wxbot_config']==str(root/'config.wxbot.toml')
    assert result['sources']['groups_file']==str(root/'data/cache/groups.json')
    assert 'home="data"' in path.read_text()


def test_empty_log_sources_keep_auto_and_absolute(tmp_path):
    from dashboard.settings import load_settings
    path=tmp_path/'log.toml'
    path.write_text('[sources]\nwxbot_config=""\n',encoding='utf-8')
    assert load_settings(path)['sources']['wxbot_config']==''
    assert load_settings(path)['sources']['home']==str(tmp_path/'data')


def test_edit_lock_lives_in_cache_and_keeps_stable_identity(tmp_path):
    from dashboard.config_editor import config_lock, edit_lock_path
    path=tmp_path/'config.wxbot.toml'
    expected=edit_lock_path(path)
    assert expected.parent==tmp_path/'data/cache/config-locks'
    assert edit_lock_path(tmp_path/'.'/path.name)==expected
    with config_lock(path): assert expected.is_file()
    assert expected.is_file()
    assert not Path(str(path)+'.edit.lock').exists()


def test_upgrade_relativizes_same_targets_and_removes_only_edit_locks(tmp_path):
    import tomlkit
    from butler.runtime.upgrade import upgrade_installation
    from dashboard.settings import load_settings
    (tmp_path/'config.butler.toml').write_text('[agent]\nprovider="codex"\n',encoding='utf-8')
    (tmp_path/'config.wxbot.toml').write_text('[model]\nbackend="echo"\n',encoding='utf-8')
    path=tmp_path/'config.log.toml'
    path.write_text('# keep\n'+tomlkit.dumps({'sources':{'home':str(tmp_path/'data'),'wxbot_config':str(tmp_path/'config.wxbot.toml')}}),encoding='utf-8')
    before=load_settings(path)
    (tmp_path/'config.wxbot.toml.edit.lock').write_bytes(b'\0')
    (tmp_path/'uv.lock').write_text('preserve')
    result=upgrade_installation(tmp_path)
    assert result['ok']
    assert load_settings(path)==before
    assert tomlkit.parse(path.read_text())['sources']['home']=='data'
    assert '# keep' in path.read_text()
    assert not (tmp_path/'config.wxbot.toml.edit.lock').exists()
    assert (tmp_path/'uv.lock').read_text()=='preserve'


def test_busy_edit_lock_is_preserved(tmp_path):
    import pytest
    if os.name!='nt':pytest.skip('Windows locking contract')
    import msvcrt
    from butler.runtime.upgrade import clean_legacy_locks
    path=tmp_path/'config.wxbot.toml.edit.lock'
    path.write_bytes(b'\0')
    with path.open('r+b') as fh:
        msvcrt.locking(fh.fileno(),msvcrt.LK_NBLCK,1)
        try:
            report=clean_legacy_locks(tmp_path)
            assert path.name in report['busy']
            assert path.exists()
        finally:
            fh.seek(0);msvcrt.locking(fh.fileno(),msvcrt.LK_UNLCK,1)
