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
from urllib.parse import urlsplit, parse_qs

from butler.agent import skills
from butler.config import Config, load, masked
from butler.agent.core import Butler
from butler.runtime.heartbeat import HeartbeatScheduler
from butler.identity.groups import parse_int as _as_int

MAX_BODY = 1 << 20


def _log(msg, *args):
    print(("[butler] " + (msg % args if args else msg)), flush=True)


def backend_description(cfg: Config) -> str:
    if cfg.provider=='codex':
        return f"Codex model={cfg.codex_model or '(runtime default)'} home={cfg.codex_home_path()}"
    return f"Hermes {cfg.hermes_url} ({masked(cfg.hermes_key)})"


def make_handler(butler: Butler, cfg: Config, heartbeat: HeartbeatScheduler | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "butler/1.0"

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
            path = urlsplit(self.path)
            if path.path=='/v1/telegram-relay/authorize':
                if not self._authed():return
                from butler.channels.telegram.service import read_subscribers
                query=parse_qs(path.query)
                contact=query.get('contact',[''])[0]
                if set(query)!={'contact'} or len(query['contact'])!=1 or not contact or len(contact)>200:
                    self._send(400,{'error':'无效联系人'});return
                try:allowed=contact in read_subscribers(cfg.group_file_path(),database=getattr(cfg,'contact_database',None))
                except ValueError:
                    self._send(503,{'error':'新闻订阅策略暂不可用'});return
                self._send(200,{'contact':contact,'allowed':allowed});return
            if path.path.startswith('/v1/media/'):
                if not self._authed():return
                from butler.delivery.media import MediaStore
                try:
                    data,metadata=MediaStore(cfg.data_path()/'media').read(path.path[len('/v1/media/'):])
                except FileNotFoundError:
                    self._send(404,{'error':'图片不存在'});return
                except (ValueError,OSError):
                    self._send(400,{'error':'图片标识或缓存无效'});return
                self.send_response(200)
                self.send_header('Content-Type',metadata['mime'])
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store')
                self.end_headers();self.wfile.write(data);return
            if path.path in ('/v1/users', '/v1/users/memory', '/v1/users/audit'):
                if not self._authed(): return
                registry = getattr(butler, 'registry', None)
                if registry is None:
                    self._send(503, {'error': '用户管理仅在 Codex 后端可用'}); return
                from butler.identity.user_api import dispatch_user_get
                try:
                    self._send(200, dispatch_user_get(registry, path.path, parse_qs(path.query)))
                except (ValueError, TypeError) as exc:
                    self._send(400, {'error': str(exc)})
                return
            if self.path == '/v1/skills':
                if not self._authed(): return
                if cfg.provider!='codex':
                    self._send(400,{'error':'Use the configured Hermes catalogue'})
                else:
                    self._send(200,{'object':'list','data':butler.catalogue.list()})
                return
            if self.path == '/v1/runtime':
                if not self._authed(): return
                self._send(200,{'backend':cfg.provider,'protocol_version':1,
                    'reminders':butler.store.reminders(order='due') if butler.store else [],
                    'memory':butler.store.runtime_memory() if butler.store else [],
                    'events':butler.store.events() if butler.store else []})
                return
            if self.path.startswith("/health"):
                if not self._authed():
                    return
                self._send(200, {"ok": True, "hermes": butler.health(),
                                 "contacts": list(cfg.contacts.names())})
                return
            if self.path.startswith("/v1/catalogue"):
                if not self._authed():
                    return
                self._send(200, {"skills": (butler.catalogue.list() if cfg.provider=='codex' else skills.catalogue()),
                                 "hint": '' if cfg.provider=='codex' else skills.HERMES_HINT})
                return
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path=='/v1/jobs/delete':
                if not self._authed():return
                if cfg.provider!='codex' or getattr(butler,'store',None) is None:
                    self._send(503,{'error':'此任务由其他调度器管理，请到对应调度器删除'});return
                from butler.runtime.job_admin import delete_job,JobConflict,JobMissing
                try:self._send(200,delete_job(butler.store,self._body()))
                except JobConflict as exc:self._send(409,{'error':str(exc)})
                except JobMissing as exc:self._send(404,{'error':str(exc)})
                except (ValueError,TypeError) as exc:self._send(400,{'error':str(exc)})
                return
            if self.path=='/v1/media':
                if not self._authed():return
                from butler.delivery.media import MediaStore,MAX_BYTES
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=MAX_BYTES:raise ValueError('image size')
                    data=self.rfile.read(length)
                    if len(data)!=length:raise ValueError('incomplete image')
                    result=MediaStore(cfg.data_path()/'media').put(data)
                except (ValueError,OSError):
                    self._send(400,{'error':'图片大小或内容无效'});return
                self._send(200,result);return
            if self.path=='/v1/push/bundle':
                if not self._authed():return
                from common.media_bundle import validate_items,validate_request_id
                from butler.delivery.media import MediaStore
                from butler.delivery.push import push_bundle_to_wxbot
                try:
                    payload=self._body()
                    if not isinstance(payload,dict) or set(payload)!={'contact','items','request_id'}:raise ValueError('bundle fields')
                    contact=payload['contact']
                    if not isinstance(contact,str) or not contact.strip() or len(contact)>200:raise ValueError('contact')
                    items=validate_items(payload['items']);request_id=validate_request_id(payload['request_id'])
                    for item in items:
                        if item['kind']=='image':MediaStore(cfg.data_path()/'media').read(item['media_id'])
                except (ValueError,FileNotFoundError,OSError):
                    self._send(400,{'ok':False,'error':'图文包或图片无效，未提交'});return
                from butler.channels.telegram.service import read_subscribers
                try:subscribed=contact in read_subscribers(cfg.group_file_path(),database=getattr(cfg,'contact_database',None))
                except ValueError:
                    self._send(503,{'ok':False,'error':'新闻订阅策略暂不可用，未提交'});return
                if not subscribed:
                    self._send(403,{'ok':False,'error':'该联系人未订阅新闻，未提交'});return
                ok,detail=push_bundle_to_wxbot(cfg,contact,items,request_id,log=_log)
                self._send(200,{'ok':ok,'detail':detail,'contact':contact,'request_id':request_id});return
            if self.path=='/v1/telegram-relay/resolve':
                if not self._authed():return
                from butler.channels.telegram.relay.store import RelayStore
                try:
                    payload=self._body()
                    if (not isinstance(payload,dict) or set(payload)!={'id','action','acknowledge'}
                            or payload['acknowledge'] is not True or not isinstance(payload['id'],str)):
                        raise ValueError('必须先核对Telegram实际发送和残留界面')
                    state_path=cfg.data_path()/'telegram-relay'/'desktop.sqlite3'
                    if not state_path.is_file():raise ValueError('转发状态尚不存在')
                    result=RelayStore(state_path).resolve(payload['id'],payload['action'])
                except (ValueError,OSError) as exc:
                    self._send(400,{'error':str(exc)});return
                self._send(200,result);return
            if self.path == '/v1/users/observe':
                if not self._authed(): return
                try:
                    body = self._body()
                    if not isinstance(body,dict) or set(body)-{'contact','channel_type','messages'}:
                        raise ValueError('Invalid user observations')
                    self._send(200,butler.observe_users(body.get('contact'),body.get('channel_type'),body.get('messages')))
                except (ValueError,TypeError):
                    self._send(400,{'error':'Invalid user observations'})
                return
            if self.path == '/v1/group/archive':
                if not self._authed(): return
                if not callable(getattr(butler,'archive_group',None)):
                    self._send(503,{'error':'Group context unavailable'}); return
                try:
                    body=self._body()
                    if not isinstance(body,dict) or set(body)-{'contact','source_id','messages'}:
                        raise ValueError('Invalid group archive')
                    result=butler.archive_group(body.get('contact'),body.get('source_id'),body.get('messages'))
                    self._send(200,result)
                except (ValueError,TypeError):
                    self._send(400,{'error':'Invalid group archive'})
                return
            if urlsplit(self.path).path == '/v1/users':
                if not self._authed(): return
                registry = getattr(butler, 'registry', None)
                if registry is None:
                    self._send(503, {'error': '用户管理仅在 Codex 后端可用'}); return
                from butler.identity.user_api import dispatch_user_post
                from butler.identity.user_registry import VersionConflict
                try:
                    self._send(200, dispatch_user_post(registry, self._body()))
                except VersionConflict as exc:
                    self._send(409, {'error': str(exc), 'code': 'version_conflict'})
                except (ValueError, TypeError) as exc:
                    self._send(400, {'error': str(exc)})
                return
            if self.path == '/v1/telegram/inbox':
                if not self._authed():
                    return
                from butler.channels.telegram.bot.inbox import accept
                try:
                    result = accept(cfg.data_path() / 'telegram-bot' / 'inbox.sqlite3', self._body())
                except (ValueError, TypeError):
                    self._send(400, {'ok': False, 'error': 'invalid Telegram envelope or conflicting update'})
                    return
                except Exception as exc:
                    _log('[Telegram] 收件入库失败 type=%s', type(exc).__name__)
                    self._send(503, {'ok': False, 'error': 'Telegram inbox unavailable'})
                    return
                _log('[Telegram] 收件已持久化 bot=%s update=%s receipt=%s status=%s',
                     result['bot_id'], result['update_id'], result['receipt_id'], result['status'])
                self._send(200, result)
                return
            if self.path == '/mcp':
                if butler.tools is None:
                    self._send(503,{'error':'Codex tools unavailable'}); return
                try:
                    from butler.runtime.mcp_gateway import dispatch
                    origin=self.headers.get('Origin')
                    if origin:
                        if urlsplit(origin).hostname not in ('127.0.0.1','localhost','::1'):
                            self._send(403,{'error':'Invalid origin'}); return
                    auth=self.headers.get('Authorization','')
                    if not auth.startswith('Bearer '): raise PermissionError('Capability required')
                    result=dispatch(butler.tools,self._body(),auth[7:])
                    if result is None:
                        self.send_response(202);self.send_header('Content-Length','0');self.end_headers()
                    else:
                        self._send(200,result)
                except PermissionError:
                    self._send(401,{'error':'Invalid or expired tool capability'})
                except (ValueError,TypeError):
                    self._send(400,{'error':'Invalid MCP request'})
                return
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
            if self.path in ("/v1/handle","/v1/handle-stream"):
                if not self._authed():
                    return
                b = self._body()
                if not isinstance(b,dict):
                    self._send(400,{'error':'请求必须是对象'});return
                contact = str(b.get("contact") or "").strip()
                text = str(b.get("text") or "")
                if not contact:
                    self._send(400, {"error": "缺少 contact（微信窗口标题）"})
                    return
                channel_type = str(b.get("channel_type") or "dm").strip().lower()
                if channel_type not in ("dm", "group"):
                    self._send(400, {"error": "channel_type 只支持 dm / group"})
                    return
                member_key = str(b.get("member_key") or "").strip()
                member_name = str(b.get("member_name") or "").strip()
                avatar = b.get('avatar','')
                boundary = b.get('group_context_seq',0)
                if not isinstance(avatar,str) or len(avatar)>750000 or type(boundary)is not int or boundary<0:
                    self._send(400,{'error':'Invalid avatar or group context sequence'}); return
                streaming=self.path=='/v1/handle-stream'
                def stream_event(event):
                    self.wfile.write(('data: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode('utf-8'))
                    self.wfile.flush()
                if streaming:
                    self.send_response(200)
                    self.send_header('Content-Type','text/event-stream; charset=utf-8')
                    self.send_header('Cache-Control','no-store')
                    self.send_header('Connection','close')
                    self.end_headers()
                    self.close_connection=True
                try:
                    res = butler.handle(contact, text, msg_id=b.get("msg_id"),
                                        channel_type=channel_type,
                                        member_key=member_key, member_name=member_name,
                                        **({'avatar':avatar}if avatar else {}),
                                        **({'group_context_seq':boundary}if boundary else {}),
                                        **({'on_event':stream_event}if streaming else {}))
                except Exception as e:                     # 绝不让异常变成"通道死了"
                    if streaming:
                        try:stream_event({'type':'error','code':type(e).__name__,'retry_safe':False})
                        except (OSError,ValueError):pass
                        return
                    _log("handle 异常: %s: %s", type(e).__name__, e)
                    self._send(500, {"error": f"{type(e).__name__}: {e}"})
                    return
                result=res.as_dict(reply_chunk_chars=cfg.reply_chunk_chars)
                if streaming:stream_event({'type':'result','result':result})
                else:self._send(200,result)
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
                member_key = str(b.get("member_key") or "").strip()
                avatar = b.get('avatar','')
                if not isinstance(avatar,str)or len(avatar)>750000:
                    self._send(400,{'error':'Invalid avatar'}); return
                self._send(200, butler.reset(contact, channel_type=channel_type,
                                             member_key=member_key,**({'avatar':avatar}if avatar else {})).as_dict(reply_chunk_chars=cfg.reply_chunk_chars))
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
                self._send(200, res.as_dict(reply_chunk_chars=cfg.reply_chunk_chars))
                return
            self._send(404, {"error": "not found"})

    return Handler


def serve(cfg: Config) -> int:
    if cfg.provider=='codex' and cfg.host not in ('127.0.0.1','localhost','::1'):
        raise ValueError('Codex Butler must listen on loopback')
    if not cfg.have_token:
        _log("!! server.token 没配 —— 接口会拒绝所有请求。先在 config.toml 里配一个。")
    butler = Butler(cfg, log=_log)
    heartbeat = HeartbeatScheduler(butler, cfg, log=_log)
    reminders=None
    if cfg.provider=='codex':
        from butler.delivery.reminders import ReminderScheduler
        reminders=ReminderScheduler(butler)
    _log("管家启动 → http://%s:%s  |  Profile: %s  |  后端: %s",
         cfg.host, cfg.port, ", ".join(sorted(cfg.contacts.profiles())) or "(无联系人)",
         backend_description(cfg))
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), make_handler(butler, cfg, heartbeat))
    heartbeat.start()
    if reminders: reminders.start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _log("收到 Ctrl+C，退出")
    finally:
        heartbeat.stop()
        if reminders: reminders.stop()
        if cfg.provider=='codex': butler.backend.close()
        httpd.server_close()
    return 0


def status(cfg: Config) -> int:
    _log("配置: %s", cfg.__class__.__name__)
    _log("  接口      http://%s:%s   token=%s", cfg.host, cfg.port, masked(cfg.token))
    _log("  后端      %s", backend_description(cfg))
    _log("  wxbot     %s   token=%s", cfg.wxbot_url, masked(cfg.wxbot_token))
    _log("  流水日志  %s", cfg.flow_log_path() or "(禁用：hermes.root 与 log.flow_file 都未配)")
    _log("  决策层    actions_enabled=%s  script_dir=%s  respond_after=%s",
         cfg.actions_enabled, cfg.script_dir or "(未配)", cfg.respond_after_action)
    _log("  联系人    %s", ", ".join(f"{c.name}→{c.profile}/{c.uid}"
                                    for c in cfg.contacts.by_name.values()) or "(无)")
    rc = 0
    for p in sorted(cfg.contacts.profiles()):
        ok = Butler(cfg, log=_log).hermes.alive(p)
        _log("  %s 探活 profile=%s → %s", cfg.provider, p, "通" if ok else "不通")
        rc = rc or (0 if ok else 1)
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="管家（wxbot 与模型后端之间的编排层）")
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
