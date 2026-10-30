import json
from types import SimpleNamespace

import pytest
import requests


def cfg():
    return SimpleNamespace(token='private-test-token', host='127.0.0.1', port=8770, wxbot_timeout=120)


def transport(monkeypatch, status=200, payload=None, error=None):
    import butler.delivery.push_client as module
    calls = []
    class Session:
        trust_env = True
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            calls.append((url, kwargs, self.trust_env))
            if error:
                raise error
            response = requests.Response()
            response.status_code = status
            response._content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            return response
    monkeypatch.setattr(module.requests, 'Session', Session)
    return calls


@pytest.mark.parametrize('payload,state', [
    ({'meta': {'ok': True, 'contact': 'A'}}, 'sent'),
    ({'meta': {'ok': 1, 'contact': 'A'}}, 'uncertain'),
    ({'meta': {'ok': True, 'contact': 'B'}}, 'uncertain'),
    ({'meta': {'ok': False, 'contact': 'A'}}, 'uncertain'),
    ({'meta': []}, 'uncertain'), ([], 'uncertain'),
    (b'not-json-with-private-test-token', 'uncertain'),
])
def test_only_confirmed_matching_recipient_is_sent(monkeypatch, payload, state):
    from butler.delivery.push_client import push_news
    calls = transport(monkeypatch, payload=payload)
    result = push_news(cfg(), 'A', 'original')
    assert result['state'] == state
    assert 'private-test-token' not in str(result)
    url, kwargs, trust_env = calls[0]
    assert url == 'http://127.0.0.1:8770/v1/push'
    assert kwargs['json'] == {'type': 1, 'messageType': 1, 'contact': 'A', 'text': 'original'}
    assert kwargs['allow_redirects'] is False
    assert trust_env is False


@pytest.mark.parametrize('status,state', [(400, 'not_submitted'), (401, 'not_submitted'), (403, 'not_submitted'), (404, 'not_submitted'), (429, 'uncertain'), (500, 'uncertain'), (302, 'uncertain')])
def test_http_rejection_vs_unknown(monkeypatch, status, state):
    from butler.delivery.push_client import push_news
    transport(monkeypatch, status, {'meta': {'ok': True, 'contact': 'A'}})
    assert push_news(cfg(), 'A', 'body')['state'] == state


def test_missing_token_does_not_submit_and_timeout_does_not_retry(monkeypatch):
    from butler.delivery.push_client import push_news
    calls = transport(monkeypatch, error=requests.Timeout('private-test-token'))
    empty = cfg()
    empty.token = ''
    assert push_news(empty, 'A', 'body')['state'] == 'not_submitted'
    assert calls == []
    result = push_news(cfg(), 'A', 'body')
    assert result['state'] == 'uncertain'
    assert len(calls) == 1
    assert 'private-test-token' not in str(result)


def test_rss_entry_retains_same_receipt_contract(monkeypatch):
    from butler.news.delivery import push
    transport(monkeypatch, payload={'meta': {'ok': True, 'contact': 'A'}})
    assert push(cfg(), 'A', 'body')['state'] == 'sent'
