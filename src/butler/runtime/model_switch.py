"""Request-pinned model generations; service identity and storage never reload."""
from collections import ChainMap
from contextlib import contextmanager
from contextvars import ContextVar
from copy import copy, deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit, urlunsplit

from butler.config import load
from butler.agent.hermes import HermesError


MODEL_FIELDS = ('provider', 'model_config', 'codex_model', 'codex_api_key',
                'codex_timeout', 'codex_max_workers', 'codex_idle_seconds',
                'hermes_url', 'hermes_key', 'hermes_model', 'hermes_timeout',
                'send_identity', 'hermes_profile_in_path')


class ModelConfigurationError(HermesError):
    """A request rejected before acquiring or invoking any model backend."""
    retry_safe = True


def _local_hermes_settings(cfg):
    """A Hermes selection in an already-local service selects model transport.

    This normalization is deliberately confined to the reload wrapper. Existing
    legacy Hermes services still initialize their original client and business
    paths, while an active local service retains its own identity and tools.
    """
    url = urlsplit(cfg.hermes_url)
    path = url.path.rstrip('/')
    if not path.endswith('/chat/completions'):
        path += '/chat/completions' if path.endswith('/v1') else '/v1/chat/completions'
    return {'url': urlunsplit((url.scheme, url.netloc, path, url.query, url.fragment)),
            'api_key': cfg.hermes_key, 'model': cfg.hermes_model, 'timeout': cfg.hermes_timeout}


@dataclass(eq=False)
class _Generation:
    cfg: object
    backend: object
    tools: object
    users: int = 0
    retired: bool = False


class ReloadableBackend:
    def __getattr__(self, name):
        # Preserve inspection hooks used by local integrations (workers,
        # last_error, timeout); model calls themselves always use _call.
        gen = self._pinned.get() or self._current
        return getattr(gen.backend, name)

    def __setattr__(self, name, value):
        if not name.startswith('_') and '_current' in self.__dict__:
            gen = self._pinned.get() or self._current
            setattr(gen.backend, name, value)
        else:
            object.__setattr__(self, name, value)

    def __init__(self, cfg, log=None, *, locks=None, store=None, tools=None, factory=None):
        if factory is None:
            from butler.backends import create_backend
            factory = create_backend
        self._base = cfg
        self._factory, self._log = factory, log or (lambda *a, **k: None)
        self._locks, self._store, self._tools = locks, store, tools
        explicit = getattr(cfg, 'config_path', '')
        self._path = Path(explicit) if explicit else (Path(cfg.config_dir)/'config.butler.toml' if cfg.config_dir else None)
        self._guard = RLock()
        self._pinned = ContextVar('butler_model_generation', default=None)
        self._generations = []
        self._closed = False
        self._reload_error = ''
        self._current = self._create(replace(cfg, model_config=deepcopy(cfg.model_config)))

    def _create(self, cfg):
        # Each Codex generation owns its opaque worker-token map, while HTTP MCP
        # verification accepts maps from every still-active generation.
        tools = copy(self._tools) if self._tools is not None else None
        if tools is not None:
            tools.worker_credentials = {}
        backend = self._factory(cfg, self._log, locks=self._locks, store=self._store, tools=tools)
        gen = _Generation(cfg, backend, tools)
        self._generations.append(gen)
        self._credentials()
        return gen

    def _credentials(self):
        if self._tools is not None:
            self._tools.worker_credentials = ChainMap(*(getattr(g.tools, 'worker_credentials', {}) for g in self._generations))

    def _dispose(self, gen):
        if gen.users:
            return
        try:
            close = getattr(gen.backend, 'close', None)
            if close:
                close()
        except Exception:
            self._log('Retired model backend cleanup failed')
        finally:
            self._generations.remove(gen)
            self._credentials()

    def _refresh(self):
        if self._path is None:
            return
        try:
            # Missing or partial files retain the last good generation.
            if not self._path.is_file():
                raise ValueError('configuration unavailable')
            saved = load(self._path)
            fields = {name: deepcopy(getattr(saved, name)) for name in MODEL_FIELDS}
            snapshot = replace(self._base, **fields)
            if snapshot.provider == 'hermes' and not snapshot.model_config:
                snapshot = replace(snapshot, model_config=_local_hermes_settings(snapshot))
            if not snapshot.uses_local_runtime:
                raise ValueError('legacy runtime requires service startup')
            if any(getattr(snapshot, key) != getattr(self._current.cfg, key) for key in MODEL_FIELDS):
                previous = self._current
                self._current = self._create(snapshot)
                previous.retired = True
                self._dispose(previous)
            self._reload_error = ''
        except Exception:
            # Provider libraries and TOML errors may include credentials.
            self._reload_error = 'Saved model settings could not be applied; no model request was sent'

    @contextmanager
    def request(self):
        existing = self._pinned.get()
        if existing is not None:
            yield existing
            return
        with self._guard:
            if self._closed:
                raise RuntimeError('Model runtime is closed')
            self._refresh()
            if self._reload_error:
                raise ModelConfigurationError(self._reload_error, 503)
            gen = self._current
            gen.users += 1
        token = self._pinned.set(gen)
        try:
            yield gen
        finally:
            self._pinned.reset(token)
            with self._guard:
                gen.users -= 1
                if gen.retired:
                    self._dispose(gen)

    @property
    def cfg(self):
        gen = self._pinned.get() or self._current
        return gen.cfg

    def runtime_status(self):
        with self._guard:
            configured = self._current.cfg.provider
            try:
                if self._path is not None:
                    configured = load(self._path).provider
            except Exception:
                configured = None
            cfg = self._current.cfg
            return {'backend': cfg.provider, 'configured_backend': configured,
                    'model': cfg.codex_model if cfg.provider=='codex' else cfg.model_config.get('model', cfg.hermes_model),
                    'reload_error': self._reload_error,
                    'active_requests': sum(g.users for g in self._generations),
                    'retiring_backends': [g.cfg.provider for g in self._generations if g.retired]}

    def _call(self, method, *args, **kwargs):
        with self.request() as gen:
            return getattr(gen.backend, method)(*args, **kwargs)

    def chat(self, *args, **kwargs):
        return self._call('chat', *args, **kwargs)

    def reset(self, *args, **kwargs):
        return self._call('reset', *args, **kwargs)

    def session_id(self, *args, **kwargs):
        return self._call('session_id', *args, **kwargs)

    def alive(self, *args, **kwargs):
        return self._call('alive', *args, **kwargs)

    def scope(self, contact, policy=None, kind='chat'):
        with self.request() as gen:
            scope = getattr(gen.backend, 'scope', None)
            return scope(contact, policy, kind) if scope else contact.key()

    def close(self):
        with self._guard:
            self._closed = True
            for gen in list(self._generations):
                gen.retired = True
                self._dispose(gen)
