"""Local Butler business tools over native model function-call protocols."""
import json
import subprocess  # Shared module also used by the sandboxed Cursor transport.
import time
import uuid

import requests

from butler.agent.hermes import HermesError
from butler.backends.compatible import CompatibleBackend
from butler.backends.codex import DEFAULT_POLICY, owner_key, tool_owner_key
from common.flow_trace import current_request_id
from common.model_stream import answer, emit


class LocalModelBackend(CompatibleBackend):
    MAX_ROUNDS = 8
    MAX_CALLS = 32

    def __init__(self, cfg, log=None, *, locks=None, store=None, tools=None, transport=None):
        super().__init__(cfg, log, locks=locks)
        self.store, self.tools = store, tools
        self.transport = transport or self._request_json
        self.histories = {}

    @staticmethod
    def _request_json(url, headers, body, timeout):
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        try:
            response.raise_for_status()
            return response.json(), dict(response.headers)
        finally:
            close = getattr(response, 'close', None)
            if close:
                close()

    def reset(self, contact, *, skill_policy=None, session_kind='chat'):
        policy = self.tools.catalogue.validate(skill_policy or DEFAULT_POLICY) if self.tools else skill_policy
        with self.session_guard(contact, session_kind=session_kind):
            self.histories.pop(self.scope(contact, policy, session_kind), None)
            super().reset(contact, skill_policy=policy, session_kind=session_kind)

    def session_id(self, contact, *, skill_policy=None, session_kind='chat'):
        policy = self.tools.catalogue.validate(skill_policy or DEFAULT_POLICY) if self.tools else skill_policy
        return super().session_id(contact, skill_policy=policy, session_kind=session_kind)

    def close(self):
        super().close()
        self.histories.clear()

    def chat(self, contact, text, *, extra_system='', timeout=None, skill_policy=None, session_kind='chat'):
        try:
            policy = self.tools.catalogue.validate(skill_policy or DEFAULT_POLICY) if self.tools else skill_policy
            if self.store:
                self.store.identify(owner_key(contact), contact)
            if self.tools:
                role = self.tools.catalogue.read(policy['role_skill'])
                extra_system = '\n'.join([extra_system, 'Mandatory role: '+policy['role_skill'], role,
                    'Business identity and permissions are issued by Butler, never by prompts. '
                    'Use only supplied business tools. Never claim success without their result. '
                    'Return only the final user-facing answer; do not emit action markers.'])
            if self.provider not in ('openai', 'responses') or not self.tools:
                return super().chat(contact, text, extra_system=extra_system, timeout=timeout,
                                    skill_policy=policy, session_kind=session_kind)
            scope = self.scope(contact, policy, session_kind)
            with self.session_guard(contact, session_kind=session_kind):
                reply = self._native_chat(contact, text, scope, policy, extra_system, timeout, session_kind)
                self._ids.setdefault(scope, uuid.uuid4().hex)
                self.last_error = ''
                answer(reply)
                return reply
        except Exception as exc:
            self.last_error = type(exc).__name__
            error = HermesError(f'{self.provider} model request failed ({type(exc).__name__})')
            error.retry_safe = False
            raise error from None

    def _native_chat(self, contact, text, scope, policy, extra_system, timeout, kind):
        limit = self.timeout if timeout is None else max(0.001, float(timeout))
        deadline = time.monotonic() + limit
        token = self.tools.issue(owner=tool_owner_key(contact), memory_owner=owner_key(contact),
            contact=contact.name, policy=policy, read_only=kind=='heartbeat',
            memory_allowed=contact.identity_status not in {'unknown','ambiguous','disabled','observed'},
            request_id=current_request_id() or uuid.uuid4().hex, ttl=limit+60)
        definitions = self.tools.definitions(token)
        system = '\n'.join(filter(None, [self.base_system, contact.identity(backend='codex'), extra_system]))
        history = self.histories.get(scope, [])
        messages = [{'role':'system','content':system}] + history + [{'role':'user','content':text}]
        headers = {'Content-Type':'application/json'}
        if self.settings.get('api_key'):
            headers['Authorization'] = 'Bearer ' + self.settings['api_key']
        emit('backend', provider=self.identity, model=self.model, streaming=False, fallback='complete_result')
        used_ids = set()
        for _ in range(self.MAX_ROUNDS):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Model turn deadline exceeded')
            if self.provider == 'responses':
                tools = [{'type':'function','name':d['name'],'description':d['description'],
                          'parameters':d['inputSchema']} for d in definitions]
                body = {'model':self.model,'input':messages,'tools':tools,'store':False,'stream':False}
            else:
                tools = [{'type':'function','function':{'name':d['name'],'description':d['description'],
                          'parameters':d['inputSchema']}} for d in definitions]
                body = {'model':self.model,'messages':messages,'tools':tools,'stream':False}
            data, _ = self.transport(self.settings['url'], headers, body, remaining)
            if time.monotonic() >= deadline:
                raise TimeoutError('Model turn deadline exceeded')
            final, calls, continuation = self._decode_native(data)
            if not calls:
                self.histories[scope] = (history + [{'role':'user','content':text},
                    {'role':'assistant','content':final}])[-self.settings['max_history']*2:]
                return final
            if len(used_ids) + len(calls) > self.MAX_CALLS:
                raise ValueError('Too many model tool calls')
            # Validate the entire batch before any authorized side effects occur.
            allowed = {d['name'] for d in self.tools.definitions(token)}
            parsed = []
            for call in calls:
                identifier, name, arguments = call
                if (not isinstance(identifier,str) or not identifier or len(identifier)>256 or
                        identifier in used_ids or name not in allowed or not isinstance(arguments,str) or len(arguments)>100000):
                    raise ValueError('Invalid or unauthorized model tool call')
                args = json.loads(arguments)
                if not isinstance(args,dict) or any(k in args for k in ('owner','contact','uid','user_id','profile')):
                    raise PermissionError('Tool identity is server-owned')
                used_ids.add(identifier)
                parsed.append((identifier,name,args))
            messages.extend(continuation)
            for identifier, name, args in parsed:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Model turn deadline exceeded')
                result = self.tools.call(name, args, token, identifier)
                output = json.dumps(result, ensure_ascii=False)
                if self.provider == 'responses':
                    messages.append({'type':'function_call_output','call_id':identifier,'output':output})
                else:
                    messages.append({'role':'tool','tool_call_id':identifier,'content':output})
        raise ValueError('Model tool loop did not finish')

    def _decode_native(self, data):
        if not isinstance(data,dict) or data.get('error'):
            raise ValueError('Invalid model response')
        if self.provider == 'responses':
            if data.get('status')!='completed' or data.get('incomplete_details'):
                raise ValueError('Responses result is incomplete')
            output = data.get('output')
            if not isinstance(output,list):
                raise ValueError('Invalid Responses output')
            calls, pieces, continuation = [], [], []
            for item in output:
                if not isinstance(item,dict):
                    raise ValueError('Invalid Responses item')
                if item.get('type') == 'reasoning':
                    continuation.append(item)
                    continue
                if item.get('type') == 'function_call' and item.get('status')=='completed':
                    calls.append((item.get('call_id'),item.get('name'),item.get('arguments')))
                    continuation.append(item)
                elif item.get('type') == 'message' and item.get('status')=='completed':
                    if item.get('phase') not in (None,'final_answer'):
                        continue
                    for part in item.get('content',[]):
                        if part.get('type')!='output_text' or not isinstance(part.get('text'),str):
                            raise ValueError('Unsupported Responses content')
                        pieces.append(part['text'])
                else:
                    raise ValueError('Unsupported Responses output')
            final = '\n'.join(pieces).strip()
            if not calls and not final:
                raise ValueError('Responses has no final text')
            return final, calls, continuation
        choices = data.get('choices')
        if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):
            raise ValueError('Expected one model choice')
        choice = choices[0]
        message = choice.get('message')
        if not isinstance(message,dict) or message.get('function_call'):
            raise ValueError('Invalid assistant message')
        if choice.get('finish_reason') == 'tool_calls':
            raw_calls = message.get('tool_calls')
            if not isinstance(raw_calls,list) or not raw_calls:
                raise ValueError('Missing tool calls')
            calls = []
            for item in raw_calls:
                if not isinstance(item,dict) or item.get('type')!='function' or not isinstance(item.get('function'),dict):
                    raise ValueError('Invalid function call')
                calls.append((item.get('id'),item['function'].get('name'),item['function'].get('arguments')))
            return '', calls, [message]
        if choice.get('finish_reason')!='stop' or message.get('tool_calls'):
            raise ValueError('Model response is incomplete')
        final = message.get('content')
        if not isinstance(final,str) or not final.strip():
            raise ValueError('Model has no final text')
        return final.strip(), [], []
