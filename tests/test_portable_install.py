import json
import tomllib

from butler.setup import initialize, doctor
from butler.config import load


def test_fresh_install_is_idempotent_and_does_not_copy_personal_data(tmp_path):
    root=tmp_path/'中文 安装';root.mkdir()
    initialize(root)
    path=root/'config.butler.toml'
    original=path.read_bytes()
    cfg=load(path)
    assert cfg.provider=='codex'
    assert cfg.contacts.names()==[]
    assert cfg.token and cfg.wxbot_token and cfg.token!=cfg.wxbot_token
    from butler.contact_store import ContactStore, is_unified
    database=root/'data/business.sqlite3'
    assert is_unified(database)
    assert ContactStore(database).policies()=={}
    assert not (root/'data/cache/butler_heartbeat.json').exists()
    assert not (root/'data/cache/butler_groups.json').exists()
    wx=tomllib.loads((root/'config.wxbot.toml').read_text(encoding='utf-8'))
    assert wx['butler']['token']==cfg.token
    assert wx['outbound']['token']==cfg.wxbot_token
    initialize(root)
    assert path.read_bytes()==original
    assert not (cfg.codex_home_path()/'auth.json').exists()
    report=doctor(cfg,check_wechat=False)
    assert report['checks']['codex_login']['ok'] is False
    assert report['checks']['plugin']['ok'] is True


def test_plugin_references_and_protocol_are_self_contained():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'plugins'/'butler-wechat'
    manifest=json.loads((root/'.codex-plugin/plugin.json').read_text(encoding='utf-8'))
    assert (root/manifest['skills']).is_dir()
    assert (root/manifest['mcpServers']).is_file()
    assert json.loads((root/'protocol.json').read_text())['protocol_version']==1


def test_incompatible_plugin_fails_before_runtime_start(tmp_path):
    import pytest
    from butler.core import Butler
    root=tmp_path/'plugin';root.mkdir()
    (root/'protocol.json').write_text('{"protocol_version":99,"minimum_application_version":"1.0.0"}')
    from butler.config import Config
    with pytest.raises(ValueError,match='protocol|协议'):
        Butler(Config(provider='codex',data_dir=str(tmp_path/'data'),codex_plugin=str(root)))


def test_start_normalizes_relative_config_before_changing_child_cwd(tmp_path,monkeypatch):
    import butler.__main__ as entry
    import butler.setup as setup
    root=tmp_path/'中文 安装';root.mkdir()
    initialize(root)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup,'doctor',lambda *a,**k:{'checks':{
        name:{'ok':True} for name in ('butler_port','wxbot_port','log_port')}})
    calls=[]
    class Process:
        returncode=0
        def poll(self):return 0
    def popen(command,**kwargs):
        calls.append((command,kwargs))
        return Process()
    monkeypatch.setattr(entry.subprocess,'Popen',popen)
    assert entry.main(['start','--config',str(root.relative_to(tmp_path)/'config.butler.toml')])==0
    from pathlib import Path
    for command,kwargs in calls:
        assert Path(kwargs['env']['BUTLER_CONFIG']).is_absolute()
        assert Path(kwargs['env']['BUTLER_CONFIG'])==root/'config.butler.toml'
    assert calls[0][0][-1]==str(root/'config.butler.toml')


def test_doctor_checks_configured_service_ports(tmp_path,monkeypatch):
    initialize(tmp_path)
    for name,old,new in [('config.wxbot.toml','port = 8765','port = 8865'),
                         ('config.log.toml','port = 8788','port = 8888')]:
        path=tmp_path/name
        path.write_text(path.read_text(encoding='utf-8').replace(old,new),encoding='utf-8')
    checked=[]
    class Socket:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def bind(self,address):checked.append(address[1])
    monkeypatch.setattr('butler.setup.socket.socket',Socket)
    report=doctor(load(tmp_path/'config.butler.toml'),check_wechat=False)
    assert checked==[8770,8865,8888]
    assert report['checks']['wxbot_port']['port']==8865
