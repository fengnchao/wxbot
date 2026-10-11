"""本地模型处理器：调用本机 Ollama，按联系人保存对话上下文（仅内存）。"""
import requests

from ..log import log
from .base import Processor


class OllamaProcessor(Processor):
    def __init__(self, mcfg: dict):
        self.url = mcfg.get("url", "http://localhost:11434/api/chat")
        self.model = mcfg.get("model", "qwen2.5:7b")
        self.timeout = mcfg.get("timeout", 120)
        self.max_history = mcfg.get("max_history", 10)
        self.system_prompt = mcfg.get("system_prompt", "")
        self.histories: dict[str, list[dict]] = {}

    def reset(self, contact: str) -> None:
        self.histories.pop(contact, None)

    def handle(self, contact: str, text: str) -> str | None:
        history = self.histories.setdefault(contact, [])
        history.append({"role": "user", "content": text})
        messages = ([{"role": "system", "content": self.system_prompt}] if self.system_prompt else []) + history
        try:
            resp = requests.post(
                self.url,
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            reply = resp.json()["message"]["content"].strip()
        except Exception as e:
            history.pop()
            log.error("本地模型调用失败: %s", e)
            return "抱歉，我这边暂时出了点问题，稍后再试。"
        history.append({"role": "assistant", "content": reply})
        del history[:-self.max_history * 2]
        return reply
