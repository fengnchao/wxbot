"""两条边：管家→Hermes 的线格式，以及管家对 wxbot 暴露的 HTTP 契约。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from butler import hermes as H
from butler.contacts import load_contacts
from butler.hermes import HermesClient

CONTACT = {"name": "101", "profile": "wxbot-101", "uid": "101"}


class _Resp:
    status = 200
    headers = {"X-Hermes-Session-Id": "echoed-id"}

    def read(self):
        return json.dumps({"choices": [{"message": {"content": " 回你一句 "}}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_hermes_wire_format(make_home, monkeypatch):
    """URL / 两个会话头 / 身份注入 / 用户文本不被改写 —— 少一样都会静默劣化。"""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _Resp()

    monkeypatch.setattr(H.urllib.request, "urlopen", fake_urlopen)
    cfg = make_home().cfg
    contact = load_contacts([CONTACT]).get("101")
    client = HermesClient(cfg)
    assert client.chat(contact, "帮我看下明天天气") == "回你一句"

    # 默认扁平接口（config.butler.toml: profile_in_path = false）；命名 Profile 部署才带 /p/{profile} 前缀，
    # 见 test_hermes_wire_format_named_profile。记忆隔离靠 X-Hermes-Session-Key 头，不靠路径。
    assert captured["url"].endswith("/v1/chat/completions")
    assert "/p/" not in captured["url"], "profile_in_path=false 时不该出现 /p/{profile} 前缀"
    h = captured["headers"]
    assert "x-hermes-session-key" in h and "x-hermes-session-id" in h, \
        "少一个 Id 就变成'每条消息一段新对话'"
    assert ":" not in h["x-hermes-session-id"], "冒号会被服务端当成 Windows 盘符 → 400"
    msgs = captured["body"]["messages"]
    assert msgs[0]["role"] == "system" and "user_id=101" in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "帮我看下明天天气"}
    assert client.session_ids["101"] == "echoed-id", "服务端回显的 id 要记住"


def test_hermes_wire_format_named_profile(make_home, monkeypatch):
    """profile_in_path=true 时恢复 /p/{profile}/v1/...（Hermes 侧建了命名 Profile 的部署）。"""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(H.urllib.request, "urlopen", fake_urlopen)
    cfg = make_home().cfg
    cfg.hermes_profile_in_path = True          # config.butler.toml: profile_in_path = true
    contact = load_contacts([CONTACT]).get("101")
    HermesClient(cfg).chat(contact, "在吗")
    assert captured["url"].endswith("/p/wxbot-101/v1/chat/completions")
    assert cfg.hermes_profile_in_path is True


def _call(base, path, payload=None, token="t0ken"):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


@pytest.mark.parametrize("token", ["", "wrong"])
def test_http_requires_token(make_home, start_server, token):
    home = make_home(replies=["x"])
    base = start_server(home.butler, home.cfg)
    assert _call(base, "/v1/handle", {"contact": "101", "text": "hi"}, token=token)[0] == 401


def test_http_handle_and_meta_shape(make_home, start_server):
    home = make_home(replies=["来自管家的回复"], pending_items=[])
    base = start_server(home.butler, home.cfg)
    code, body = _call(base, "/v1/handle", {"contact": "101", "text": "hi"})
    assert code == 200 and body["reply"] == "来自管家的回复"
    assert set(body) >= {"reply", "actions", "meta"}
    assert {"model_silent", "sent", "pending"} <= set(body["meta"])


def test_http_rejects_missing_contact(make_home, start_server):
    home = make_home(replies=["x"])
    base = start_server(home.butler, home.cfg)
    assert _call(base, "/v1/handle", {"text": "没联系人"})[0] == 400


def test_http_health_catalogue_reset(make_home, start_server):
    home = make_home(replies=["x"])
    base = start_server(home.butler, home.cfg)
    code, body = _call(base, "/health")
    assert code == 200 and body["ok"] is True and body["hermes"] == {"wxbot-101": True}
    code, body = _call(base, "/v1/catalogue")
    assert code == 200 and any(s["name"] == "reminder.create" and s["kind"] == "local"
                               for s in body["skills"])
    code, body = _call(base, "/v1/reset", {"contact": "101"})
    assert code == 200 and body["meta"]["reset"] is True
