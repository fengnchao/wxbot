"""Offline policy cache tests. Every HTTP operation is an injected fake session."""
import json
import threading
import time
from types import SimpleNamespace

import pytest

from wxbot.relay_authorization import RelayAuthorization


class Response:
    def __init__(self,payload=None,status=200):
        self.status_code=status
        self.data=json.dumps(payload).encode()
        self.closed=False
    def iter_content(self,size):
        yield self.data
    def close(self): self.closed=True


class Session:
    def __init__(self,responses):
        self.responses=list(responses);self.calls=[];self.trust_env=True
        self.started=threading.Event();self.release=threading.Event();self.release.set()
        self.closed=False
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs,threading.get_ident()))
        self.started.set()
        assert self.release.wait(2),'test must release fake request'
        result=self.responses.pop(0)
        if isinstance(result,Exception): raise result
        return result
    def close(self):self.closed=True


def delivery(contact='A',package_id='package'):
    return SimpleNamespace(contact=contact,package_id=package_id)


def eventually(probe,expected,timeout=1):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=probe()
        if result is expected:return
        threading.Event().wait(.002)
    assert result is expected


def test_allowed_never_does_network_in_ui_thread_and_caches_for_half_second():
    clock=[0.0]
    session=Session([Response({'contact':'A','allowed':True}),Response({'contact':'A','allowed':False})])
    session.release.clear()
    policy=RelayAuthorization('http://127.0.0.1:8766','secret',clock=lambda:clock[0],session_factory=lambda:session)
    try:
        assert policy.allowed(delivery()) is None
        assert session.started.wait(1)
        assert len(session.calls)==1 and session.calls[0][2]!=threading.get_ident()
        assert policy.allowed(delivery()) is None
        session.release.set()
        eventually(lambda:policy.allowed(delivery()),True)
        clock[0]=.5
        assert policy.allowed(delivery()) is True and len(session.calls)==1
        clock[0]=.501
        assert policy.allowed(delivery()) is None
        eventually(lambda:policy.allowed(delivery()),False)
        url,kwargs,_=session.calls[-1]
        assert url=='http://127.0.0.1:8766/v1/telegram-relay/authorize'
        assert kwargs['params']=={'contact':'A'}
        assert kwargs['headers']=={'Authorization':'Bearer secret'}
        assert kwargs['allow_redirects'] is False and session.trust_env is False
        assert kwargs['timeout'][0]<=1 and kwargs['timeout'][1]<=1
    finally:
        session.release.set();policy.close()
    assert session.closed


@pytest.mark.parametrize('url,token',[
    ('https://example.com','secret'),('http://127.0.0.1.evil.example','secret'),
    ('http://user:pass@127.0.0.1','secret'),('file:///secret','secret'),
    ('http://127.0.0.1?url=external','secret'),('http://127.0.0.1',''),
    ('http://127.0.0.1/path','secret'),('http://[::ffff:192.168.1.1]','secret'),
])
def test_missing_token_or_non_loopback_never_creates_network_session(url,token):
    policy=RelayAuthorization(url,token,session_factory=lambda:pytest.fail('network must remain disabled'))
    try: assert policy.allowed(delivery()) is None
    finally:policy.close()


@pytest.mark.parametrize('response',[
    Response({'contact':'other','allowed':True}),Response({'contact':'A','allowed':'true'}),
    Response({'contact':'A','allowed':True,'injected':'extra'}),Response({'contact':'A','allowed':True},302),
    OSError('failure containing secret and URL'),Response([{'contact':'A','allowed':True}]),
])
def test_bad_response_or_network_failure_discards_grant_without_claiming_revoked(response):
    clock=[0.0];session=Session([Response({'contact':'A','allowed':True}),response])
    policy=RelayAuthorization('http://127.0.0.1','secret',clock=lambda:clock[0],session_factory=lambda:session)
    try:
        assert policy.allowed(delivery()) is None
        eventually(lambda:policy.allowed(delivery()),True)
        clock[0]=1
        assert policy.allowed(delivery()) is None
        deadline=time.monotonic()+1
        while len(session.calls)<2 and time.monotonic()<deadline:threading.Event().wait(.002)
        assert len(session.calls)==2
        # Wait until the fake request completes before inspecting its result.
        threading.Event().wait(.01)
        assert policy.allowed(delivery()) is None
    finally:policy.close()


def test_nonpackage_legacy_delivery_bypasses_relay_policy_and_invalid_contact_fails_closed():
    policy=RelayAuthorization('http://127.0.0.1','secret',session_factory=lambda:pytest.fail('no fetch'))
    try:
        assert policy.allowed(delivery(package_id=None)) is True
        assert policy.allowed(delivery(contact='')) is None
        assert policy.allowed(delivery(contact=['A'])) is None
    finally:policy.close()


def test_slow_grant_is_not_made_fresh_by_response_arrival():
    clock=[0.0];session=Session([Response({'contact':'A','allowed':True})]);session.release.clear()
    policy=RelayAuthorization('http://127.0.0.1','secret',clock=lambda:clock[0],session_factory=lambda:session)
    try:
        assert policy.allowed(delivery()) is None and session.started.wait(1)
        clock[0]=1;session.release.set()
        threading.Event().wait(.02)
        assert policy.allowed(delivery()) is None
    finally:session.release.set();policy.close()
