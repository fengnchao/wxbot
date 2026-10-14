"""wxbot 外发 HTTP 服务（8765）：接收主动推送请求，交给主循环线程代发。

为什么要有它：
  微信 UI 发送（ChatWindow.send）依赖 uiautomation 的 COM，**必须在主循环线程调用**
  （COM 有线程亲和，HTTP 线程直接调会崩）。所以这里只用一个线程安全队列把请求排队，
  真正的发送由 main.py 的主循环每轮排空队列时完成。

对外契约（与 scripts/wxbot_deliver.py、scripts/wxbot_send.py 已写好的完全一致）：
  GET  /health                    → 200 {"ok": true}（不校验 token；探活把 200/401 都算在线）
  POST /send {contact,text,wait,timeout}
       头 X-Wxbot-Token: <token>  → 校验；不匹配 401
       wait 为真则阻塞等主循环发完（上限 timeout 秒）
       → {"ok": bool, "detail": str}
"""
from __future__ import annotations

import collections
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 1 << 20


class OutboundRequest:
    """一次外发请求：带一个 Event 和结果槽，主循环发完 set() 通知等待方。"""

    __slots__ = ("contact", "text", "event", "ok", "detail")

    def __init__(self, contact: str, text: str):
        self.contact = contact
        self.text = text
        self.event = threading.Event()
        self.ok = False
        self.detail = ""

    def finish(self, ok: bool, detail: str = "") -> None:
        self.ok = bool(ok)
        self.detail = detail or ""
        self.event.set()


class OutboundQueue:
    """线程安全的外发队列。HTTP 线程 submit，主循环线程 drain。"""

    def __init__(self):
        self._q: collections.deque = collections.deque()
        self._lock = threading.Lock()

    def submit(self, contact: str, text: str) -> OutboundRequest:
        req = OutboundRequest(contact, text)
        with self._lock:
            self._q.append(req)
        return req

    def drain(self) -> list:
        """取出并清空当前所有请求（主循环每轮调一次）。"""
        with self._lock:
            items = list(self._q)
            self._q.clear()
        return items


def make_handler(queue: OutboundQueue, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "wxbot-outbound/0.1"

        def log_message(self, fmt, *args):        # 默认写 stderr，太吵
            pass

        # ---------- 工具 ----------
        def _send(self, code: int, obj: dict):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY:
                return {}
            raw = self.rfile.read(n)
            try:
                return json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                return {}

        def _authed(self) -> bool:
            got = self.headers.get("X-Wxbot-Token") or ""
            if token and got != token:
                self._send(401, {"ok": False, "detail": "unauthorized"})
                return False
            return True

        # ---------- 路由 ----------
        def do_GET(self):
            if self.path.startswith("/health"):   # 探活不校验 token
                self._send(200, {"ok": True})
                return
            self._send(404, {"ok": False, "detail": "not found"})

        def do_POST(self):
            if self.path.startswith("/send"):
                if not self._authed():
                    return
                b = self._body()
                contact = str(b.get("contact") or "").strip()
                text = str(b.get("text") or "")
                if not contact:
                    self._send(400, {"ok": False, "detail": "缺少 contact（微信窗口标题）"})
                    return
                if not text:
                    self._send(400, {"ok": False, "detail": "缺少 text"})
                    return
                wait = bool(b.get("wait", True))
                try:
                    timeout = float(b.get("timeout") or 60)
                except (TypeError, ValueError):
                    timeout = 60.0
                req = queue.submit(contact, text)
                if not wait:                       # 即发即回，不等结果
                    self._send(200, {"ok": True, "detail": "queued"})
                    return
                done = req.event.wait(timeout)
                if not done:
                    self._send(200, {"ok": False, "detail": "timeout：主循环未在时限内发出"})
                    return
                self._send(200, {"ok": req.ok, "detail": req.detail})
                return
            self._send(404, {"ok": False, "detail": "not found"})

    return Handler


def start_server(host: str, port: int, token: str, queue: OutboundQueue):
    """在守护线程里起外发服务；返回 ThreadingHTTPServer（失败抛异常给调用方）。"""
    httpd = ThreadingHTTPServer((host, int(port)), make_handler(queue, token))
    t = threading.Thread(target=httpd.serve_forever, name="wxbot-outbound", daemon=True)
    t.start()
    return httpd
