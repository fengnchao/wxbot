from types import SimpleNamespace
import pytest
from butler.config import Config, load
from butler.identity.contacts import Contact
from butler.agent.hermes import HermesError
from test_codex_backend import make_backend, FakeCodex


def test_config_api_key_load_and_repr(tmp_path):
    path=tmp_path/'config.butler.toml'
    path.write_text('[codex]\napi_key="test-api-secret"\n',encoding='utf-8')
    cfg=load(path)
    assert cfg.codex_api_key=='test-api-secret'
    assert 'test-api-secret' not in repr(cfg)


def test_api_key_login_precedes_account_and_stays_out_of_environment(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(FakeCodex,'login_api_key',lambda self,key:calls.append(('login',key)),raising=False)
    def account(self):
        assert calls==[('login','api-test-secret')]
        calls.append(('account',None))
        return SimpleNamespace(account={'type':'apiKey'})
    monkeypatch.setattr(FakeCodex,'account',account)
    b=make_backend(tmp_path); b.cfg.codex_api_key='api-test-secret'
    assert b.alive()
    try:
        assert b.chat(Contact('alice','default','alice'),'hi')=='你好呀'
        client=list(b.workers.values())[0].client
        assert 'api-test-secret' not in repr(client.config)
    finally:b.close()


def test_api_key_error_redacted_and_no_account_or_turn(tmp_path,monkeypatch):
    def login(self,key):raise RuntimeError('rejected '+key)
    monkeypatch.setattr(FakeCodex,'login_api_key',login,raising=False)
    def forbidden(*a,**kw):pytest.fail('account/thread must not run after failed login')
    monkeypatch.setattr(FakeCodex,'account',forbidden)
    b=make_backend(tmp_path); b.cfg.codex_api_key='short-secret'
    try:
        with pytest.raises(HermesError) as error:b.chat(Contact('alice','default','alice'),'hi')
        assert 'short-secret' not in str(error.value)
        assert 'short-secret' not in b.last_error
        assert '[REDACTED]' in b.last_error
        assert FakeCodex.created[-1].closed
    finally:b.close()


def test_account_login_path_unchanged_without_key(tmp_path,monkeypatch):
    def forbidden(*a,**kw):pytest.fail('API login must not run without configured key')
    monkeypatch.setattr(FakeCodex,'login_api_key',forbidden,raising=False)
    b=make_backend(tmp_path)
    try:assert b.chat(Contact('alice','default','alice'),'hi')=='你好呀'
    finally:b.close()
