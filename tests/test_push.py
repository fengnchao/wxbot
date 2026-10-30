"""主动推送链路：butler→wxbot 的线格式、外发流水日志格式、wxbot 8765 外发服务。

对应计划 A/B 两块：
  - butler.push.push_to_wxbot 对假 wxbot 服务（200/401/宕机）
  - flowlog.outbound_queued/sent 写出的行能被看板 log/server.py:parse_wxbot_log 正确解析
  - wxbot.outbound 的 8765 服务：入队可被消费、错误 token 拒绝、wait 阻塞到发完
"""
from __future__ import annotations

import importlib.util
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from butler.config import Config
from butler.runtime.flowlog import FlowLog
from butler.delivery.push import push_to_wxbot
from wxbot.outbound import OutboundQueue, start_server

ROOT = Path(__file__).resolve().parents[1]


def _load_dashboard():
    """看板已是常规包，按文件路径加载以便隔离配置，只为复用 parse_wxbot_log。"""
    spec = importlib.util.spec_from_file_location("_dash_server", ROOT / "src" / "dashboard" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _post(url, body=None, headers=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


# ---------------------------------------------------------------- B: butler → wxbot

class _FakeWxbot(BaseHTTPRequestHandler):
    """假装 wxbot 的 /send：校验 X-Wxbot-Token，正确就回 {ok:true}。"""
    token = "wxbot-tok"

    def log_message(self, *a):
        pass

    def do_POST(self):
        got = self.headers.get("X-Wxbot-Token") or ""
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
        if got != self.token:
            code, obj = 401, {"ok": False, "detail": "unauthorized"}
        elif not payload.get("contact") or not payload.get("text"):
            code, obj = 400, {"ok": False, "detail": "bad body"}
        else:
            self.server.captured = payload                 # 记下但ler 发来的 body 供断言
            code, obj = 200, {"ok": True, "detail": "sent"}
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def fake_wxbot():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _FakeWxbot)
    httpd.captured = None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1], httpd
    httpd.shutdown()
    httpd.server_close()


def test_push_ok(fake_wxbot):
    base, httpd = fake_wxbot
    cfg = Config(wxbot_url=base, wxbot_token="wxbot-tok", wxbot_timeout=10)
    ok, detail = push_to_wxbot(cfg, "101", "定时提醒", log=lambda *a, **k: None)
    assert ok is True
    assert httpd.captured["contact"] == "101" and httpd.captured["text"] == "定时提醒"
    assert httpd.captured["wait"] is True                   # 契约：等主循环发完


def test_push_wrong_token(fake_wxbot):
    base, _ = fake_wxbot
    cfg = Config(wxbot_url=base, wxbot_token="wrong-tok", wxbot_timeout=10)
    ok, detail = push_to_wxbot(cfg, "101", "hi", log=lambda *a, **k: None)
    assert ok is False and "401" in detail


def test_push_server_down():
    # 端口 1 上不会有服务 → 连接失败要如实回 (False, ...)，不抛异常
    cfg = Config(wxbot_url="http://127.0.0.1:1", wxbot_token="x", wxbot_timeout=2)
    ok, detail = push_to_wxbot(cfg, "101", "hi", log=lambda *a, **k: None)
    assert ok is False and detail


# ---------------------------------------------------------------- B: 外发流水日志 ↔ 看板

def test_flowlog_outbound_parsed_by_dashboard(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    log_path = cache / "wxbot.log"
    flow = FlowLog(str(log_path))
    flow.outbound_queued("101", "该喝水啦")
    flow.outbound_sent("101", "该喝水啦")

    dash = _load_dashboard()
    events, path = dash.parse_wxbot_log(str(tmp_path))
    assert path.replace("\\", "/") == str(log_path).replace("\\", "/")
    out = [e for e in events if e["direction"] == "outbound"]
    assert [(e["phase"], e["uid"], e["content"]) for e in out] == [
        ("queued", "101", "该喝水啦"),
        ("sent", "101", "该喝水啦"),
    ]
    # 看板把入队 + 已发出合成一条
    merged = dash.merge_outbound(events)
    m = [e for e in merged if e["direction"] == "outbound"]
    assert len(m) == 1 and m[0]["phase"] == "queued" and m[0].get("sent_ts")


# ---------------------------------------------------------------- A: wxbot 8765 外发服务

@pytest.fixture
def outbound_server():
    q = OutboundQueue()
    httpd = start_server("127.0.0.1", 0, "wxbot-tok", q)
    yield "http://127.0.0.1:%d" % httpd.server_address[1], q, httpd
    httpd.shutdown()
    httpd.server_close()


def test_outbound_health_no_token(outbound_server):
    base, _, _ = outbound_server
    req = urllib.request.Request(base + "/health")
    with urllib.request.urlopen(req, timeout=5) as r:      # 不带 token 也要 200
        assert r.status == 200 and json.loads(r.read())["ok"] is True


def test_outbound_rejects_wrong_token(outbound_server):
    base, _, _ = outbound_server
    code, body = _post(base + "/send", {"contact": "101", "text": "hi", "wait": False},
                       headers={"X-Wxbot-Token": "wrong-tok"})
    assert code == 401 and body["ok"] is False


def test_outbound_enqueue_nowait(outbound_server):
    base, q, _ = outbound_server
    code, body = _post(base + "/send", {"contact": "101", "text": "该喝水啦", "wait": False},
                       headers={"X-Wxbot-Token": "wxbot-tok"})
    assert code == 200 and body["ok"] is True and body["detail"] == "queued"
    reqs = q.drain()                                       # 主循环这一侧能取到
    assert len(reqs) == 1 and reqs[0].contact == "101" and reqs[0].text == "该喝水啦"
    assert q.drain() == []                                 # 取完即空


def test_outbound_wait_blocks_until_finished(outbound_server):
    base, q, _ = outbound_server
    result = {}

    def caller():
        result["resp"] = _post(base + "/send",
                               {"contact": "101", "text": "hi", "wait": True, "timeout": 5},
                               headers={"X-Wxbot-Token": "wxbot-tok"})

    t = threading.Thread(target=caller)
    t.start()
    req = None
    for _ in range(100):                                   # 等 HTTP 线程把请求排进队列
        drained = q.drain()
        if drained:
            req = drained[0]
            break
        threading.Event().wait(0.05)
    assert req is not None
    req.finish(True, "sent")                               # 模拟主循环发完
    t.join(timeout=5)
    assert result["resp"] == (200, {"ok": True, "detail": "sent"})


def test_outbound_missing_fields(outbound_server):
    base, _, _ = outbound_server
    assert _post(base + "/send", {"text": "没联系人", "wait": False},
                 headers={"X-Wxbot-Token": "wxbot-tok"})[0] == 400
    assert _post(base + "/send", {"contact": "101", "wait": False},
                 headers={"X-Wxbot-Token": "wxbot-tok"})[0] == 400


# ---------------------------------------------------------------- B: butler /v1/push 端点

def _call_push(base, payload, token="t0ken"):
    headers = {"Authorization": "Bearer " + token} if token else {}
    return _post(base + "/v1/push", payload, headers=headers)


def test_push_endpoint(make_home, start_server, monkeypatch):
    """POST /v1/push：鉴权 + 校验 + 转发 + 写外发流水（把 wxbot 那一步替掉）。"""
    import butler.agent.core as core
    monkeypatch.setattr(core, "push_to_wxbot",
                        lambda cfg, contact, text, log=None: (True, "sent"))
    home = make_home()
    base = start_server(home.butler, home.cfg)

    assert _call_push(base, {"contact": "101", "text": "hi"}, token="wrong")[0] == 401
    assert _call_push(base, {"contact": "101"}, token="t0ken")[0] == 400      # 缺 text
    assert _call_push(base, {"text": "没联系人"}, token="t0ken")[0] == 400      # 缺 contact

    code, body = _call_push(base, {"contact": "101", "text": "该喝水啦"})
    assert code == 200 and body["reply"] is None
    assert body["meta"]["ok"] is True and body["meta"]["contact"] == "101"

    flow = Path(home.cfg.flow_log_path()).read_text(encoding="utf-8")
    assert "[外发] 入队 → 101: 该喝水啦" in flow
    assert "[外发] 已发出 → 101: 该喝水啦" in flow
