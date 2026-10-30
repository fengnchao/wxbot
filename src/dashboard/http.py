#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP 传输层：请求解析、鉴权确认、静态文件、异常包装与路由分发。

业务逻辑在 dashboard.api.*，路由表在 dashboard.routes；
本模块只管「把一个请求变成一次 (status, body) 调用，再写回 socket」。
"""
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from common.paths import REPO_ROOT
from dashboard import routes
from dashboard.api.support import HERMES_HOME


class RequestContext:
    """一次请求的上下文：参数解析 + 服务函数解析。

    `one / num / flag / body` 只做参数解析；业务函数（配置、数据源、代理请求）
    一律从 Handler 的 `_service_namespace()` 按名解析 —— 这样测试 monkeypatch
    `dashboard.server`（含按文件路径加载出来的副本）依然生效。
    """

    __slots__ = ("handler", "method", "path", "query", "url")

    def __init__(self, handler, method, path, query, url):
        self.handler = handler
        self.method = method
        self.path = path
        self.query = query
        self.url = url

    # ------------------------------------------------------------ 请求本身
    @property
    def home(self):
        return self.handler.home

    def one(self, key, default=""):
        values = self.query.get(key)
        return values[0] if values else default

    def num(self, key, default):
        try:
            return int(self.one(key, str(default)))
        except Exception:
            return default

    def flag(self, key):
        return self.one(key, "") in ("1", "true", "yes", "on")

    def body(self):
        return self.handler._body()

    def confirm(self, header):
        """写操作的「同源 + 自定义确认头」校验。"""
        return self.handler._confirmed_origin(header)

    def config_view(self):
        return self.handler._config_view()

    def contact_admin(self):
        return self.handler._contact_admin()

    def relay_admin(self):
        return self.handler._relay_admin()

    def load_butler_config(self):
        """`_load_butler_config` 的可读别名，走同一条解析路径。"""
        return self.__getattr__('_load_butler_config')()

    def __getattr__(self, name):
        namespace = self.handler._service_namespace()
        try:
            return namespace[name]
        except KeyError:
            raise AttributeError(name) from None


class BaseHandler(BaseHTTPRequestHandler):
    server_version = "WeChatInbox/1.0"
    home = HERMES_HOME
    WEBAPP_DIR = os.path.join(str(REPO_ROOT), 'web', 'dist')
    WEBAPP_TYPES = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
                    '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml',
                    '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon',
                    '.woff2': 'font/woff2', '.map': 'application/json; charset=utf-8'}

    def log_message(self, fmt, *args):
        pass

    def _service_namespace(self):
        """服务函数所在命名空间；由 dashboard.server.Handler 覆盖为本模块 globals。"""
        return {}

    def _svc(self, name):
        return self._service_namespace()[name]

    # ------------------------------------------------------------ 写响应
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str))

    def _body(self):
        """读 JSON 请求体（POST 用）；读不出就回空 dict（校验层再拒）。"""
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > (1 << 20):
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8", "replace"))
        except Exception:
            return {}

    def _confirmed_origin(self, header):
        host = self.headers.get('Host', '').lower()
        try:
            target = urlparse('//' + host)
            local = {'localhost', '127.0.0.1', '::1', self.connection.getsockname()[0].lower()}
            port = target.port if target.port is not None else 80
            origin = self.headers.get('Origin')
            valid_origin = (not origin or (urlparse(origin).scheme in {'http', 'https'}
                                           and urlparse(origin).netloc.lower() == host))
            return (target.hostname in local and port == self.server.server_port and valid_origin and
                    self.headers.get(header) == '1' and
                    self.headers.get('Content-Type', '').split(';')[0].strip().lower() == 'application/json')
        except ValueError:
            return False

    # ------------------------------------------------------------ 服务入口
    def _config_view(self):
        return self._svc('ConfigView')(
            self._svc('wxbot_config_path')(), self._svc('butler_config_path')(), self.home,
            groups_override=self._svc('group_file_path')(self.home),
            log_config_path=self._svc('log_config_path')(),
            log_runtime={'host': self.server.server_address[0],
                         'port': self.server.server_address[1],
                         'overrides': {k: os.environ[k] for k in
                                       ('HERMES_HOME', 'WXBOT_CONFIG',
                                        'BUTLER_CONFIG', 'BUTLER_GROUP_FILE')
                                       if os.environ.get(k)}})

    def _relay_admin(self):
        from butler.config import load as load_butler
        cfg = load_butler(self._svc('butler_config_path')())
        return self._svc('TelegramRelayAdmin')(
            cfg.resolve_path('config.telegram-relay.toml'),
            cfg.data_path() / 'telegram-relay' / 'desktop-status.json')

    def _contact_admin(self):
        from butler.contact_admin import ContactAdmin
        from butler.directory import directory_path

        def validate(route, policy):
            skills = self._svc('fetch_hermes_skills')(route, self._svc('_load_butler_config')())
            is_role = self._svc('is_butler_role_skill')
            roles = {s['name'] for s in skills if is_role(s)}
            tools = {s['name'] for s in skills if not is_role(s)}
            if policy['role_skill'] not in roles:
                raise ValueError('角色 Skill 不存在或缺少 butler-role 标签')
            if not set(policy['allowed_skills']) <= tools:
                raise ValueError('工具白名单包含目录中不存在的 Skill')

        return ContactAdmin(directory_path(self._svc('butler_config_path')()),
                            policy_validator=validate)

    def _serve_webapp(self, relative):
        """管理台挂在 /app/；未构建时只给出构建提示。"""
        index = os.path.join(self.WEBAPP_DIR, 'index.html')
        if not os.path.isfile(index):
            self._send(200, '<!doctype html><meta charset="utf-8"><title>管理台尚未构建</title>'
                            '<body style="font:14px/1.8 system-ui;padding:40px;max-width:720px;background:#101419;color:#e4eaf0">'
                            '<h1>管理台尚未构建</h1>'
                            '<p>在 <code>web</code> 执行 <code>npm install &amp;&amp; npm run build</code> 后刷新此页。</p></body>',
                       'text/html; charset=utf-8')
            return
        if relative.startswith('assets/'):
            root = os.path.join(self.WEBAPP_DIR, 'assets') + os.sep
            target = os.path.normpath(os.path.join(self.WEBAPP_DIR, relative))
            if not target.startswith(root) or not os.path.isfile(target):
                self._send(404, 'Not found', 'text/plain; charset=utf-8')
                return
            with open(target, 'rb') as fh:
                body = fh.read()
            self._send(200, body, self.WEBAPP_TYPES.get(os.path.splitext(target)[1].lower(),
                                                        'application/octet-stream'))
            return
        with open(index, 'rb') as fh:
            self._send(200, fh.read(), 'text/html; charset=utf-8')

    # ------------------------------------------------------------ 分发
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        ctx = RequestContext(self, method, path, parse_qs(url.query), url)
        try:
            if routes.gated(method, path) and ctx.dashboard_mode() != 'local':
                self._json({'error': '当前接入方式的业务功能由对端管理台维护', 'available': False}, 503)
                return
            if method == "GET" and path == "/":
                self._send(302, '', 'text/plain; charset=utf-8',
                           {'Location': '/app/' + ('?' + url.query if url.query else '')})
                return
            if method == "GET" and (path == '/app' or path.startswith('/app/')):
                self._serve_webapp(path[len('/app/'):] if path.startswith('/app/') else '')
                return
            handler = routes.match(method, path)
            if handler is None:
                self._json({"error": "not found", "path": path}, 404)
                return
            status, payload = handler(ctx)
            self._json(payload, status)
        except Exception as exc:
            self._json({"error": type(exc).__name__, "detail": str(exc)}, 500)
