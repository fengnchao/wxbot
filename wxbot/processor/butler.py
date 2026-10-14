"""Butler 管家处理器：把消息转给本地 butler 服务（POST /v1/handle）。

butler 是决策编排层：负责投递大模型(Hermes)、判断是否调用 skill、拼装补发，
最终返回 {"reply": ...}。本处理器只做“转发 + 取 reply”，不含任何业务决策。

对应 butler 侧接口（见 butler/README.md）：
    POST /v1/handle {contact, text}  → {"reply": str|null, "actions": [...], "meta": {...}}
    POST /v1/reset  {contact}        → 开新会话
两者都要求 Header: Authorization: Bearer <token>（token = butler 配置的 server.token）。
"""
import requests

from ..log import log
from .base import Processor


class ButlerProcessor(Processor):
    def __init__(self, bcfg: dict):
        self.url = (bcfg.get("url") or "http://127.0.0.1:8770").rstrip("/")
        self.token = bcfg.get("token", "")
        self.timeout = bcfg.get("timeout", 660)   # 管家一轮可能慢跑（要等大模型），给足

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def handle(self, contact: str, text: str) -> str | None:
        try:
            resp = requests.post(self.url + "/v1/handle", headers=self._headers(),
                                 json={"contact": contact, "text": text}, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error("butler 调用失败: %s", e)
            return "抱歉，我这边暂时出了点问题，稍后再试。"
        reply = data.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            return None                          # 管家判定静默 / 不回复
        return reply

    def reset(self, contact: str) -> None:
        try:
            requests.post(self.url + "/v1/reset", headers=self._headers(),
                          json={"contact": contact}, timeout=self.timeout)
        except Exception as e:
            log.error("butler reset 失败: %s", e)
