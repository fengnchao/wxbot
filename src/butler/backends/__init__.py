"""Model runtimes behind the existing Butler complete-reply contract."""
from typing import Protocol


class ModelBackend(Protocol):
    def chat(self, contact, text: str, *, extra_system='', timeout=None, skill_policy=None, session_kind='chat') -> str: ...
    def reset(self, contact, *, skill_policy=None, session_kind='chat') -> None: ...
    def session_id(self, contact, *, skill_policy=None, session_kind='chat') -> str: ...
    def alive(self, profile: str) -> bool: ...


def create_backend(cfg, log=None, *, locks=None, store=None, tools=None):
    if cfg.provider == 'codex':
        from butler.backends.codex import CodexBackend
        return CodexBackend(cfg,log,locks=locks,store=store,tools=tools)
    from butler.agent.hermes import HermesClient
    return HermesClient(cfg,log,locks=locks)
