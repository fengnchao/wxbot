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
import math
import os
from pathlib import Path
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 1 << 20


class ButlerMediaClient:
    """Fetch only opaque media IDs from the configured authenticated Butler."""
    def __init__(self, url, token):
        self.url, self.token = url.rstrip('/'), token

    def fetch(self, media_id):
        import requests
        from common.media_bundle import validate_items
        validate_items([{'kind':'image','media_id':media_id}])
        if not self.url or not self.token:
            raise ValueError('Butler 媒体服务未配置')
        with requests.Session() as session:
            session.trust_env=False
            with session.get(self.url+'/v1/media/'+media_id, headers={'Authorization':'Bearer '+self.token},
                             timeout=(5,30),stream=True,allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError('图片下载未成功')
                data=bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data)>20*1024*1024:
                        raise ValueError('图片超过大小上限')
                return bytes(data)


class BundleMediaCache:
    """Network-thread image preparation; callers cannot supply filesystem paths."""
    def __init__(self, root, client):
        self.root, self.client = Path(root).resolve(), client

    def resolve(self, items):
        from common.media_bundle import validate_items
        from butler.media import validate_image
        items=validate_items(items)
        paths={}
        for item in items:
            if item['kind'] != 'image' or item['media_id'] in paths:
                continue
            media_id=item['media_id']
            fetch=getattr(self.client,'fetch',self.client)
            data=fetch(media_id)
            validate_image(data)
            self.root.mkdir(parents=True,exist_ok=True)
            target=self.root/(media_id+'.image')
            if target.is_symlink() or target.resolve().parent != self.root:
                raise ValueError('无效图片缓存位置')
            temporary=self.root/(uuid.uuid4().hex+'.tmp')
            try:
                with temporary.open('xb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary,target)
            finally:
                temporary.unlink(missing_ok=True)
            paths[media_id]=target
        return paths


class OutboundRequest:
    """一次外发请求：带一个 Event 和结果槽，主循环发完 set() 通知等待方。"""

    __slots__ = ("contact", "text", "event", "ok", "detail", "items", "request_id", "media_paths")

    def __init__(self, contact: str, text: str, *, items=None, request_id='', media_paths=None):
        self.contact = contact
        self.text = text
        self.event = threading.Event()
        self.ok = False
        self.detail = ""
        self.items, self.request_id, self.media_paths = items, request_id, media_paths or {}

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

    def submit_bundle(self, contact, items, request_id, *, media_paths):
        from common.media_bundle import validate_items
        req=OutboundRequest(contact,'',items=validate_items(items),request_id=request_id,media_paths=media_paths)
        with self._lock:
            self._q.append(req)
        return req


def make_handler(queue: OutboundQueue, token: str, *, media_cache=None,allow_bundles=True):
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
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except (ValueError,TypeError):
                return {}
            if n <= 0 or n > MAX_BODY:
                return {}
            raw = self.rfile.read(n)
            try:
                return json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                return {}

        def _authed(self) -> bool:
            got = self.headers.get("X-Wxbot-Token") or ""
            if (self.path=='/send-bundle' and not token) or (token and got != token):
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
            if self.path in {'/send','/send-bundle'}:
                if not self._authed():
                    return
                if self.path=='/send-bundle' and not allow_bundles:
                    self._send(400,{'ok':False,'detail':'图文包仅支持主窗口队列模式，not submitted'})
                    return
                b = self._body()
                if not isinstance(b,dict):
                    self._send(400,{'ok':False,'detail':'无效请求'})
                    return
                contact = str(b.get("contact") or "").strip()
                text = str(b.get("text") or "")
                if not contact:
                    self._send(400, {"ok": False, "detail": "缺少 contact（微信窗口标题）"})
                    return
                bundle=self.path == '/send-bundle'
                if not bundle and not text:
                    self._send(400, {"ok": False, "detail": "缺少 text"})
                    return
                wait = bool(b.get("wait", True))
                try:
                    timeout = float(b.get("timeout") or 60)
                except (TypeError, ValueError):
                    timeout = 60.0
                if bundle:
                    try:
                        from common.media_bundle import validate_items, validate_request_id
                        if set(b)-{'contact','items','request_id','wait','timeout'}:
                            raise ValueError('无效包字段')
                        if not isinstance(b.get('contact'),str) or len(contact)>256 or b.get('wait',True) is not True:
                            raise ValueError('图文包必须等待完整回执')
                        if not math.isfinite(timeout) or not 0<timeout<=3600:
                            raise ValueError('无效等待上限')
                        items=validate_items(b.get('items'))
                        request_id=validate_request_id(b.get('request_id'))
                        if any(item['kind']=='image' for item in items) and media_cache is None:
                            raise ValueError('图片服务未配置')
                        paths=media_cache.resolve(items) if media_cache else {}
                        req=queue.submit_bundle(contact,items,request_id,media_paths=paths)
                    except Exception:
                        self._send(400,{'ok':False,'detail':'图文包或图片校验失败，未入队'})
                        return
                else:
                    req = queue.submit(contact, text)
                if not wait:                       # 即发即回，不等结果
                    self._send(200, {"ok": True, "detail": "queued"})
                    return
                done = req.event.wait(timeout)
                if not done:
                    self._send(200, {"ok": False, "detail": "timeout：主循环未在时限内发出"})
                    return
                result={"ok":req.ok,"detail":req.detail}
                if bundle:
                    result.update(contact=contact,request_id=request_id)
                self._send(200, result)
                return
            self._send(404, {"ok": False, "detail": "not found"})

    return Handler


def start_server(host: str, port: int, token: str, queue: OutboundQueue, *, butler_url='',
                 butler_token='',media_cache_dir=None,media_client=None,allow_bundles=True):
    """在守护线程里起外发服务；返回 ThreadingHTTPServer（失败抛异常给调用方）。"""
    cache=(BundleMediaCache(media_cache_dir,media_client or ButlerMediaClient(butler_url,butler_token))
           if media_cache_dir is not None else None)
    httpd = ThreadingHTTPServer((host, int(port)), make_handler(queue, token,media_cache=cache,allow_bundles=allow_bundles))
    t = threading.Thread(target=httpd.serve_forever, name="wxbot-outbound", daemon=True)
    t.start()
    return httpd
