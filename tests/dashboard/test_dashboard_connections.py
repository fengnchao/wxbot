import json
from types import SimpleNamespace

import pytest


def test_external_dashboard_routes_credentials_to_configured_service(tmp_path,monkeypatch):
    from butler.runtime.install_wizard import install,Connection
    import dashboard.server as server
    install(tmp_path,Connection(provider='butler',url='https://remote.example/prefix/v1/handle',api_key='remote-secret'))
    monkeypatch.setattr(server,'butler_config_path',lambda:str(tmp_path/'config.butler.toml'))
    monkeypatch.setattr(server,'wxbot_config_path',lambda:str(tmp_path/'config.wxbot.toml'))
    cfg=server._load_butler_config()
    from dashboard.user_admin import request_user_admin
    assert cfg['_connection']['mode']=='external'
    assert request_user_admin(cfg,'/v1/users')[0]==503
    with pytest.raises(ValueError):server.fetch_butler_data(cfg,'/v1/runtime')


def test_direct_dashboard_never_falls_back_to_local_butler(tmp_path,monkeypatch):
    from butler.runtime.install_wizard import install,Connection
    import dashboard.server as server
    install(tmp_path,Connection(provider='deepseek',model='test'))
    monkeypatch.setattr(server,'butler_config_path',lambda:str(tmp_path/'config.butler.toml'))
    monkeypatch.setattr(server,'wxbot_config_path',lambda:str(tmp_path/'config.wxbot.toml'))
    cfg=server._load_butler_config()
    with pytest.raises(ValueError,match='Butler'):server.fetch_butler_data(cfg,'/v1/runtime')


def test_dashboard_contacts_use_shared_directory(tmp_path,monkeypatch):
    from butler.runtime.install_wizard import install,Connection
    from butler.identity.directory import DirectoryStore
    import dashboard.server as server
    install(tmp_path,Connection())
    store=DirectoryStore(tmp_path/'data/business.sqlite3')
    state=store.snapshot()
    state['contacts']=[{'name':'Alice','uid':'old-id','profile':'legacy-profile'}]
    store.save(state,state['version'])
    monkeypatch.setattr(server,'butler_config_path',lambda:str(tmp_path/'config.butler.toml'))
    monkeypatch.setattr(server,'wxbot_config_path',lambda:str(tmp_path/'config.wxbot.toml'))
    contacts,_=server.load_butler_contacts()
    assert contacts[0]['uid']=='old-id'
    assert server.load_wxbot_contacts()[0]['profile']=='legacy-profile'


@pytest.mark.parametrize('backend',['cursor','openclaw','responses'])
def test_dashboard_accepts_new_backend_choices(backend):
    from dashboard.config_schema import validate_value
    validate_value(('model','backend'),backend,'butler')
