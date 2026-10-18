"""管家 HTTP 接口（stdlib，无常依赖）。

  GET  /health                    → 管家活着 + 各 Profile 到 Hermes 通不通
  GET  /v1/catalogue              → 能调的 skill 白名单（给运维看）
  POST /v1/handle  {contact,text} → {"reply":..., "actions":[...], "meta":{...}}
  POST /v1/heartbeat/trigger {contact} → 立即为指定联系人执行心跳
  POST /v1/reset   {contact}      → 开新会话
  POST /v1/push    {contact?,text,type?,messageType?}
      主动推送（不走模型）：记外发日志 + 转发 wxbot 代发。
      type: 1=指定用户发送（用 contact，缺省即 1）/ 2=群发（按 messageType 查「用户分组」字典）
      messageType: 1=新闻消息 2=问候消息 3=其他（群发时必填）

全部要求 `Authorization: Bearer <server.token>`；只绑 127.0.0.1。
启动： python -m butler.server --config config.toml
      python -m butler.server --status        # 探活一次就退出
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import skills
from .config import Config, load, masked
from .core import Butler
from .heartbeat import HeartbeatScheduler
from .groups import parse_int as _as_int

MAX_BODY = 1 << 20


def _log(msg, *args):
    print(("[butler] " + (msg % args if args else msg)), flush=True)


def make_handler(butler: Butler, cfg: Config, heartbeat: HeartbeatScheduler | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "butler/0.1"

        def log_message(self, fmt, *args):        # 默认会写 stderr，太吵
            _log("http " + (fmt % args))

        # ---------- 工具 ----------
        def _send(self, code: int, obj: dict):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authed(self) -> bool:
            if not cfg.token:
                self._send(500, {"error": "server.token 未配置，拒绝服务"})
                return False
            got = self.headers.get("Authorization") or ""
            if got != f"Bearer {cfg.token}":
                self._send(401, {"error": "unauthorized"})
                return False
            return True

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY:
                return {}
            raw = self.rfile.read(n)
            try:
                return json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                return {}

        # ---------- 路由 ----------
        def do_GET(self):
            if self.path.startswith("/health"):
                if not self._authed():
                    return
                self._send(200, {"ok": True, "hermes": butler.health(),
                                 "contacts": list(cfg.contacts.names())})
                return
            if self.path.startswith("/v1/catalogue"):
                if not self._authed():
                    return
                self._send(200, {"skills": skills.catalogue(), "hint": skills.HERMES_HINT})
                return
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path == "/v1/heartbeat/trigger":
                if not self._authed():
                    return
                if heartbeat is None:
                    self._send(503, {"error": "heartbeat scheduler unavailable"})
                    return
                b = self._body()
                contact = str(b.get("contact") or "").strip()
                if not contact:
                    self._send(400, {"error": "缺少 contact（微信窗口标题）"})
                    return
                started, reason = heartbeat.trigger_contact(contact)
                if not started:
                    errors = {
                        "contact_not_configured": (400, "该联系人不在 Butler 配置中"),
                        "policy_missing": (400, "该联系人还没有保存角色和 Skill 配置"),
                        "policy_unavailable": (500, "读取该联系人的角色和 Skill 配置失败"),
                        "busy": (409, "心跳正在执行，请稍后重试"),
                        "start_failed": (500, "无法启动手动心跳"),
                    }
                    code, message = errors.get(reason, (500, "手动心跳启动失败"))
                    self._send(code, {"ok": False, "code": reason, "error": message})
                    return
                self._send(202, {"ok": True, "status": "started", "contact": contact})
                return
            if self.path.startswith("/v1/handle"):
                if not self._authed():
                    return
                b = self._body()
                contact = str(b.get("contact") or "").strip()
                text = str(b.get("text") or "")
                if not contact:
                    self._send(400, {"error": "缺少 contact（微信窗口标题）"})
                    return
                channel_type = str(b.get("channel_type") or "dm").strip().lower()
                if channel_type not in ("dm", "group"):
                    self._send(400, {"error": "channel_type 只支持 dm / group"})
                    return
                try:
                    res = butler.handle(contact, text, msg_id=b.get("msg_id"),
                                        channel_type=channel_type)
                except Exception as e:                     # 绝不让异常变成"通道死了"
                    _log("handle 异常: %s: %s", type(e).__name__, e)
                    self._send(500, {"error": f"{type(e).__name__}: {e}"})
                    return
                self._send(200, res.as_dict())
                return
            if self.path.startswith("/v1/reset"):
                if not self._authed():
                    return
                b = self._body()
                contact = str(b.get("contact") or "").strip()
                if not contact:
                    self._send(400, {"error": "缺少 contact"})
                    return
                channel_type = str(b.get('channel_type') or 'dm').strip().lower()
                if channel_type not in ('dm', 'group'):
                    self._send(400, {'error': 'channel_type 只支持 dm / group'})
                    return
                self._send(200, butler.reset(contact, channel_type=channel_type).as_dict())
                return
            if self.path.startswith("/v1/push"):
                if not self._authed():
                    return
                b = self._body()
                text = str(b.get("text") or "")
                if not text.strip():
                    self._send(400, {"error": "缺少 text"})
                    return
                if b.get("type") is None:
                    push_type = 1                        # 兼容旧请求：不给 type 就是指定用户发送
                else:
                    push_type = _as_int(b.get("type"))
                    if push_type is None:
                        self._send(400, {"error": "type 非法（1=指定用户发送 2=群发）"})
                        return
                if b.get("messageType") is None:
                    msg_type = None
                else:
                    msg_type = _as_int(b.get("messageType"))
                    if msg_type is None:
                        self._send(400, {"error": "messageType 非法（1=新闻消息 2=问候消息 3=其他）"})
                        return
                try:
                    if push_type == 1:
                        contact = str(b.get("contact") or "").strip()
                        if not contact:
                            self._send(400, {"error": "缺少 contact（指定用户发送）"})
                            return
                        res = butler.push(contact, text, push_type=1, message_type=msg_type)
                    elif push_type == 2:
                        if msg_type is None:
                            self._send(400, {"error": "群发需要 messageType（1=新闻消息 2=问候消息 3=其他）"})
                            return
                        res = butler.push_group(msg_type, text)
                    else:
                        self._send(400, {"error": "type 只支持 1(指定用户发送) / 2(群发)"})
                        return
                except Exception as e:                     # 通道异常不能变成 500 以外的崩溃
                    _log("push 异常: %s: %s", type(e).__name__, e)
                    self._send(500, {"error": f"{type(e).__name__}: {e}"})
                    return
                self._send(200, res.as_dict())
                return
            self._send(404, {"error": "not found"})

    return Handler


def serve(cfg: Config) -> int:
    if not cfg.have_token:
        _log("!! server.token 没配 —— 接口会拒绝所有请求。先在 config.toml 里配一个。")
    butler = Butler(cfg, log=_log)
    heartbeat = HeartbeatScheduler(butler, cfg, log=_log)
    _log("管家启动 → http://%s:%s  |  Profile: %s  |  Hermes: %s (%s)",
         cfg.host, cfg.port, ", ".join(sorted(cfg.contacts.profiles())) or "(无联系人)",
         cfg.hermes_url, masked(cfg.hermes_key))
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), make_handler(butler, cfg, heartbeat))
    heartbeat.start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _log("收到 Ctrl+C，退出")
    finally:
        heartbeat.stop()
        httpd.server_close()
    return 0


def status(cfg: Config) -> int:
    _log("配置: %s", cfg.__class__.__name__)
    _log("  接口      http://%s:%s   token=%s", cfg.host, cfg.port, masked(cfg.token))
    _log("  Hermes    %s   key=%s   model=%s   root=%s",
         cfg.hermes_url, masked(cfg.hermes_key), cfg.hermes_model, cfg.hermes_root or "(未配)")
    _log("  wxbot     %s   token=%s", cfg.wxbot_url, masked(cfg.wxbot_token))
    _log("  流水日志  %s", cfg.flow_log_path() or "(禁用：hermes.root 与 log.flow_file 都未配)")
    _log("  决策层    actions_enabled=%s  script_dir=%s  respond_after=%s",
         cfg.actions_enabled, cfg.script_dir or "(未配)", cfg.respond_after_action)
    _log("  联系人    %s", ", ".join(f"{c.name}→{c.profile}/{c.uid}"
                                    for c in cfg.contacts.by_name.values()) or "(无)")
    rc = 0
    for p in sorted(cfg.contacts.profiles()):
        ok = Butler(cfg, log=_log).hermes.alive(p)
        _log("  Hermes 探活 profile=%s → %s", p, "通" if ok else "不通")
        rc = rc or (0 if ok else 1)
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="管家（wxbot ⇄ Hermes 之间的编排层）")
    ap.add_argument("--config", default=None, help="config.toml 路径（默认项目根下 config.toml）")
    ap.add_argument("--status", action="store_true", help="打印配置 + 各 Profile 探活后退出")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    a = ap.parse_args(argv)

    cfg = load(a.config)
    if a.host:
        cfg.host = a.host
    if a.port:
        cfg.port = a.port
    return status(cfg) if a.status else serve(cfg)


if __name__ == "__main__":
    sys.exit(main())
