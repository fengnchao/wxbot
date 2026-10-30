import json
import tomllib
from pathlib import Path

import pytest


def test_cancel_leaves_installation_empty(tmp_path):
    from butler.runtime.install_wizard import run_wizard
    answers = iter(['codex', '', '', '', '', 'Bot', 'n'])
    result = run_wizard(tmp_path, input_fn=lambda _: next(answers), secret_fn=lambda _: '', output=lambda _: None)
    assert result['cancelled']
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('provider,backend,mode', [
    ('codex', 'butler', 'local'), ('hermes', 'hermes', 'direct'),
    ('openclaw', 'openclaw', 'direct'), ('cursor', 'cursor', 'direct'),
    ('deepseek', 'openai', 'direct'), ('custom', 'responses', 'direct'),
    ('butler', 'butler', 'external'),
])
def test_connection_configs_and_idempotent_install(tmp_path, provider, backend, mode):
    from butler.runtime.install_wizard import install, Connection
    conn = Connection(provider=provider, protocol='responses' if provider=='custom' else '',
                      url='https://agent.example/v1/responses' if provider=='custom' else '',
                      api_key='test-secret', model='test-model')
    result = install(tmp_path, conn, nickname='Bot')
    assert result['ok']
    raw = tomllib.loads((tmp_path/'config.wxbot.toml').read_text(encoding='utf-8'))
    assert raw['model']['backend'] == backend
    assert raw['installation']['mode'] == mode
    assert raw['outbound']['token']
    assert 'test-secret' not in json.dumps(result)
    paths = list(tmp_path.glob('config.*.toml'))
    before = {p: p.read_bytes() for p in paths}
    assert install(tmp_path, Connection(provider='codex'))['preserved_existing']
    assert {p: p.read_bytes() for p in paths} == before


@pytest.mark.parametrize('url', ['ftp://host', 'http://u:p@host', 'http://host:0', 'http://host:99999',
                                'http://host/a?token=secret', 'http://host/a#x'])
def test_reject_invalid_addresses(url):
    from butler.runtime.install_wizard import normalize_url
    with pytest.raises(ValueError): normalize_url(url)


def test_normalization_and_local_listener_validation():
    from butler.runtime.install_wizard import normalize_url, listener
    assert normalize_url('https://host/base/v1/handle/', suffix='/v1/handle') == 'https://host/base'
    assert listener('http://localhost:9876/send', suffix='/send') == ('localhost', 9876, 'http://localhost:9876')
    for url in ['https://localhost:8765', 'http://example.com:8765', 'http://127.0.0.1:8765/base']:
        with pytest.raises(ValueError): listener(url)


def test_install_rollback_on_write_failure(tmp_path, monkeypatch):
    from butler.runtime.install_wizard import install, Connection
    original = Path.open
    def fail(path, mode='r', *a, **kw):
        if path.name=='config.wxbot.toml' and mode=='x': raise OSError('disk failure')
        return original(path, mode, *a, **kw)
    monkeypatch.setattr(Path, 'open', fail)
    with pytest.raises(OSError): install(tmp_path, Connection(provider='codex'))
    assert not list(tmp_path.glob('config.*.toml'))


def test_direct_mode_does_not_require_codex_or_local_butler(tmp_path, monkeypatch):
    from butler.runtime.install_wizard import install, Connection
    from butler.runtime.setup import doctor
    from butler.config import load
    install(tmp_path, Connection(provider='deepseek', api_key='test-key', model='test'))
    result = doctor(load(tmp_path/'config.butler.toml'), check_wechat=False)
    assert 'codex_login' not in result['checks']
    assert 'butler_port' not in result['checks']


def test_codex_key_install_needs_no_chatgpt_login(tmp_path):
    from butler.runtime.install_wizard import install,Connection
    from butler.runtime.setup import doctor
    from butler.config import load
    result=install(tmp_path,Connection(provider='codex',api_key='test-private-key'))
    cfg=load(tmp_path/'config.butler.toml')
    assert cfg.codex_api_key=='test-private-key'
    assert doctor(cfg,check_wechat=False)['checks']['codex_login']['ok']
    assert not any(command.endswith(' login') for command in result['next'])
    assert 'test-private-key' not in json.dumps(result)


def test_minimal_install_supplies_wechat_locator_defaults(tmp_path):
    from butler.runtime.install_wizard import install,Connection
    from wxbot.config import load_config
    install(tmp_path,Connection())
    cfg=load_config(tmp_path/'config.wxbot.toml')['wechat']
    assert cfg['window_class']=='mmui::ChatSingleWindow'
    assert cfg['message_list']=={'control_type':'ListControl','automation_id':'chat_message_list'}
    assert cfg['input']=={'control_type':'EditControl','automation_id':'chat_input_field'}
    assert cfg['text_item']['class_name']=='mmui::ChatTextItemView'


@pytest.mark.parametrize('answers,backend',[
    (['codex','','','','','Bot','y'],'butler'),
    (['cursor','agent','data/cursor','','','','Bot','y'],'cursor'),
    (['deepseek','','test-model','','','Bot','y'],'openai'),
    (['custom','responses','https://api.example/v1/responses','test-model','','','Bot','y'],'responses'),
    (['butler','https://api.example/v1/handle','','','Bot','y'],'butler'),
])
def test_interactive_install_end_to_end_masks_secrets(tmp_path,answers,backend):
    from butler.runtime.install_wizard import run_wizard
    values=iter(answers);shown=[]
    result=run_wizard(tmp_path,input_fn=lambda _:next(values),secret_fn=lambda _:'private-test-value',output=shown.append)
    assert result.get('ok'),result
    wx=tomllib.loads((tmp_path/'config.wxbot.toml').read_text('utf-8'))
    assert wx['model']['backend']==backend
    assert 'private-test-value' not in json.dumps([shown,result])
