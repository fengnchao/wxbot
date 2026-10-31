"""Butler session adapter over pure, complete-result model transports.

Business tools and permission checks remain in Butler. Remote agent credentials
identify that remote service; no Butler capability is issued to these adapters.
"""
import hashlib
import json
import threading
import uuid

import requests

from butler.agent.hermes import HermesError
from butler.runtime.concurrency import RuntimeLocks
from common.flow_trace import current_request_id
from common.model_stream import answer, emit


DEFAULTS = {
    'openai': ('https://api.openai.com/v1/chat/completions', ''),
    'responses': ('https://api.openai.com/v1/responses', ''),
    'hermes': ('http://127.0.0.1:8642/v1/chat/completions', 'hermes-agent'),
    'openclaw': ('http://127.0.0.1:18789/v1/chat/completions', ''),
    'ollama': ('http://127.0.0.1:11434/api/chat', 'qwen2.5:7b'),
    'cursor': ('', ''),
    'echo': ('', ''),
}

# 接入方式（[model].provider）是产品名时，默认地址跟着产品走。
# 使用者留空 URL 时不能因此打到另一家服务的官方地址。
PRODUCT_ENDPOINTS = {
    'deepseek': ('https://api.deepseek.com/v1/chat/completions', 'deepseek-chat'),
}


class CompatibleBackend:
    def __init__(self, cfg, log=None, *, locks=None):
        self.cfg = cfg
        self.provider = cfg.provider
        self.log = log or (lambda *a, **kw: None)
        self.settings = dict(cfg.model_config)
        # [model].provider 是接入方式（产品名），协议只决定传输实现。
        self.identity = str(self.settings.get('provider') or '').strip() or self.provider
        default_url, default_model = PRODUCT_ENDPOINTS.get(self.identity) or DEFAULTS[self.provider]
        # 空字符串也算未填，否则留空地址会直接打到别的服务。
        if not self.settings.get('url'):self.settings['url'] = default_url
        if not self.settings.get('model'):self.settings['model'] = default_model
        self.settings['backend'] = self.provider
        self.settings['provider'] = self.provider
        self.settings['timeout'] = max(1, float(self.settings.get('timeout', 300)))
        self.settings['max_history'] = max(1, int(self.settings.get('max_history', 10)))
        self.model = self.settings['model']
        self.timeout = self.settings['timeout']
        self.base_system = self.settings.get('system_prompt', '')
        # The file contains only opaque session identifiers, never model messages.
        self.settings['session_state'] = str(cfg.data_path()/'model-sessions.sqlite3')
        self.locks = locks or RuntimeLocks(self.provider + ':' + self.settings['url'])
        self._guard = threading.RLock()
        self._transports = {}
        self._ids = {}
        self.last_error = ''

    def scope(self, contact, policy=None, kind='chat'):
        value = [self.identity, self.settings['url'], self.model, self.settings.get('agent', 'default'),
                 contact.key(), contact.memory_owner, contact.memory_version,
                 contact.binding_version, policy or {}, kind]
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def session_guard(self, contact, *, skill_policy=None, session_kind='chat'):
        return self.locks.session(contact, session_kind=session_kind)

    def _transport(self, scope):
        with self._guard:
            if scope not in self._transports:
                from wxbot.processor.openai_compat import OpenAICompatProcessor
                from wxbot.processor.responses import ResponsesProcessor
                from wxbot.processor.cursor import CursorProcessor
                if self.provider == 'cursor':
                    if not self.settings.get('work_dir'):
                        raise ValueError('Cursor requires a dedicated model.work_dir')
                    self.settings['work_dir'] = str(self.cfg.resolve_path(self.settings['work_dir']))
                cls = {'responses': ResponsesProcessor, 'cursor': CursorProcessor}.get(self.provider, OpenAICompatProcessor)
                self._transports[scope] = cls(dict(self.settings), raise_errors=True)
            return self._transports[scope]

    def session_id(self, contact, *, skill_policy=None, session_kind='chat'):
        scope = self.scope(contact, skill_policy, session_kind)
        with self.session_guard(contact, session_kind=session_kind):
            transport = self._transport(scope)
            key = transport._key(scope, 'dm')
            if self.provider in ('hermes', 'openclaw'):
                transport._state(key)
                return transport.session_ids.get(key) or transport._session(key)
            return self._ids.get(scope, 'new-' + scope)

    def reset(self, contact, *, skill_policy=None, session_kind='chat'):
        scope = self.scope(contact, skill_policy, session_kind)
        with self.session_guard(contact, session_kind=session_kind):
            self._transport(scope).reset(scope)
            self._ids[scope] = uuid.uuid4().hex

    def alive(self, profile='default'):
        # Configured readiness only: no model request or process launch as a probe.
        return self.provider in ('cursor', 'echo') or bool(self.settings['url'])

    def close(self):
        with self._guard:
            self._transports.clear()
            self._ids.clear()

    def chat(self, contact, text, *, extra_system='', timeout=None, skill_policy=None, session_kind='chat'):
        scope = self.scope(contact, skill_policy, session_kind)
        with self.session_guard(contact, session_kind=session_kind):
            transport = self._transport(scope)
            transport.timeout = self.timeout if timeout is None else max(0.001, float(timeout))
            # Use Butler-owned identity wording (the legacy Hermes template refers
            # to remote profile files that generic models must not manipulate).
            transport.system_prompt = '\n'.join(filter(None, [self.base_system, contact.identity(backend='codex'), extra_system]))
            emit('backend', provider=self.identity, model=self.model, streaming=False, fallback='complete_result')
            try:
                if self.provider == 'echo':
                    reply = '收到：' + text
                elif self.provider == 'cursor':
                    reply = transport._handle_cursor(scope, text).text
                elif self.provider == 'ollama':
                    reply = self._ollama(transport, scope, text)
                else:
                    reply = transport._handle_reply(scope, text, request_id=current_request_id()).text
                if not isinstance(reply, str) or not reply.strip():
                    raise ValueError('Model has no complete final reply')
            except Exception as exc:
                # Do not expose request URLs, credentials or remote error bodies.
                self.last_error = type(exc).__name__
                raise HermesError(f'{self.provider} model request failed ({type(exc).__name__})') from None
            self._ids.setdefault(scope, uuid.uuid4().hex)
            self.last_error = ''
            answer(reply)
            return reply

    def _ollama(self, transport, scope, text):
        key = transport._key(scope, 'dm')
        history = transport.histories.get(key, [])
        messages = [{'role': 'system', 'content': transport.system_prompt}] + history + [{'role': 'user', 'content': text}]
        headers = {'Content-Type': 'application/json'}
        if transport.api_key:
            headers['Authorization'] = 'Bearer ' + transport.api_key
        result = requests.post(transport.url, headers=headers,
                               json={'model': self.model, 'messages': messages, 'stream': False}, timeout=transport.timeout)
        try:
            result.raise_for_status()
            data = result.json()
        finally:
            close = getattr(result, 'close', None)
            if close:
                close()
        message = data.get('message') if isinstance(data, dict) else None
        if (not isinstance(data, dict) or data.get('done') is not True or data.get('error') or
                data.get('done_reason') not in (None, 'stop') or not isinstance(message, dict) or
                message.get('tool_calls') or message.get('function_call') or
                not isinstance(message.get('content'), str) or not message['content'].strip()):
            raise ValueError('Ollama has no complete final reply')
        reply = message['content'].strip()
        transport.histories[key] = (history + [{'role': 'user', 'content': text}, {'role': 'assistant', 'content': reply}])[-transport.max_history*2:]
        return reply
