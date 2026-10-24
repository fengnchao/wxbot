"""
OpenAI 兼容接口处理器：用于 Hermes Agent（hermes gateway 开启 API Server 后），
也适用于任何 /v1/chat/completions 兼容的服务（LM Studio、vLLM、Ollama 的 /v1 等）。
按联系人保存对话上下文（仅内存）。
"""
import requests

from ..log import log
from .base import Processor


class OpenAICompatProcessor(Processor):
    def __init__(self, mcfg: dict, *, raise_errors=False):
        self.raise_errors = raise_errors
        self.url = mcfg.get("url", "http://127.0.0.1:8642/v1/chat/completions")
        self.model = mcfg.get("model", "hermes-agent")
        self.api_key = mcfg.get("api_key", "")
        self.timeout = mcfg.get("timeout", 300)
        self.max_history = mcfg.get("max_history", 10)
        self.system_prompt = mcfg.get("system_prompt", "")
        self.histories: dict[str, list[dict]] = {}

    def reset(self, contact: str, *, channel_type='dm', member_key="") -> None:
        self.histories.pop(contact, None)

    def handle(self, contact: str, text: str) -> str | None:
        history = self.histories.setdefault(contact, [])
        history.append({"role": "user", "content": text})
        messages = ([{"role": "system", "content": self.system_prompt}] if self.system_prompt else []) + history
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.post(
                self.url,
                headers=headers,
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            reply = (resp.json()["choices"][0]["message"].get("content") or "").strip()
        except Exception as e:
            history.pop()
            log.error("智能体调用失败: %s", e)
            if self.raise_errors:
                raise
            return "抱歉，我这边暂时出了点问题，稍后再试。"
        if not reply:
            history.pop()
            return None
        history.append({"role": "assistant", "content": reply})
        del history[:-self.max_history * 2]
        return reply
