"""Butler 管家处理器：把消息转给本地 butler 服务（POST /v1/handle）。

butler 是决策编排层：负责投递大模型(Hermes)、判断是否调用 skill、拼装补发，
最终返回 {"reply": ...}。本处理器只做“转发 + 取 reply”，不含任何业务决策。

对应 butler 侧接口（见 butler/README.md）：
    POST /v1/handle {contact, text}  → {"reply": str|null, "actions": [...], "meta": {...}}
    POST /v1/reset  {contact}        → 开新会话
两者都要求 Header: Authorization: Bearer <token>（token = butler 配置的 server.token）。
"""
import requests
import time

from common.flow_trace import record

from ..log import log
from .base import Processor
from ..reply import Reply


class ButlerProcessor(Processor):
    def __init__(self, bcfg: dict, *, raise_errors=False):
        self.raise_errors = raise_errors
        self.url = (bcfg.get("url") or "http://127.0.0.1:8770").rstrip("/")
        self.token = bcfg.get("token", "")
        self.timeout = bcfg.get("timeout", 660)   # 管家一轮可能慢跑（要等大模型），给足

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def handle(self, contact: str, text: str) -> str | None:
        return self.handle_reply(contact, text).text

    def handle_reply(self, contact: str, text: str, *, request_id=None, member_key="", member_name="") -> Reply:
        started = time.monotonic()
        record('wxbot_butler','started')
        try:
            channel_type = "group" if member_key else "dm"
            body = {"contact": contact, "text": text, "channel_type": channel_type}
            if member_key:
                body["member_key"] = member_key
                body["member_name"] = member_name
            if request_id is not None:
                body["msg_id"] = request_id
            resp = requests.post(self.url + "/v1/handle", headers=self._headers(),
                                 json=body, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            record('wxbot_butler','error',error_type=type(e).__name__,
                   http_status=getattr(getattr(e,'response',None),'status_code',0),
                   elapsed_ms=round((time.monotonic()-started)*1000))
            log.error("butler 调用失败: %s", type(e).__name__)
            if self.raise_errors:
                raise
            return Reply.from_text("抱歉，我这边暂时出了点问题，稍后再试。")
        try:
            reply = self._decode_reply(data,request_id)
        except Exception as exc:
            record('wxbot_butler','error',error_type=type(exc).__name__,
                   elapsed_ms=round((time.monotonic()-started)*1000))
            raise
        record('wxbot_butler','ok',http_status=getattr(resp,'status_code',200),
               elapsed_ms=round((time.monotonic()-started)*1000))
        return reply

    @staticmethod
    def _decode_reply(data,request_id):
        if not isinstance(data, dict):
            raise ValueError('Butler 回复必须是对象')
        meta = data.get('meta') or {}
        if not isinstance(meta, dict):
            raise ValueError('Butler meta 格式错误')
        if meta.get('reply_complete') is False:
            error=ValueError('Butler 尚未提供完整回复'+('：'+str(meta['error'])[:1000] if meta.get('error') else ''))
            error.retry_safe=meta.get('retry_safe') is True
            raise error
        if request_id is not None and 'msg_id' in meta and meta['msg_id'] != request_id:
            raise ValueError('Butler 返回的请求 ID 不匹配')
        reply = data.get("reply")
        if reply is not None and not isinstance(reply, str):
            raise ValueError('Butler reply 格式错误')
        fallback = Reply.from_text(reply)
        if not fallback.parts:
            return fallback
        parts = data.get('reply_parts')
        if isinstance(parts, list) and parts and all(isinstance(p,str) and p.strip() for p in parts):
            return Reply(reply, tuple(parts))
        if 'reply_parts' in data:
            log.warning('Butler 分句无效，保留完整正文作为单条回复')
        return fallback

    def reset(self, contact: str, *, channel_type='dm', member_key="") -> None:
        try:
            body = {"contact": contact, "channel_type": channel_type}
            if member_key:
                body["member_key"] = member_key
            response = requests.post(self.url + "/v1/reset", headers=self._headers(),
                                     json=body, timeout=self.timeout)
            response.raise_for_status()
        except Exception as e:
            log.error("butler reset 失败: %s", e)
            if self.raise_errors:
                raise
