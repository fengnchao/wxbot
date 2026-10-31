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
    if cfg.provider == 'hermes' and not cfg.model_config:
        from butler.agent.hermes import HermesClient
        return HermesClient(cfg,log,locks=locks)
    from butler.backends.compatible import DEFAULTS
    from butler.backends.models import LocalModelBackend
    if cfg.provider not in DEFAULTS:
        raise ValueError('Unsupported model provider: ' + str(cfg.provider))
    if cfg.provider == 'cursor' and not cfg.model_config.get('work_dir'):
        raise ValueError('Cursor requires a dedicated model.work_dir')
    return LocalModelBackend(cfg,log,locks=locks,store=store,tools=tools)
