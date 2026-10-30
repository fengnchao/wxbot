"""Non-streaming, complete-result-only OpenAI-compatible conversation transport."""
import hashlib
import uuid
import sqlite3
from pathlib import Path
import requests
from common.model_stream import bind,emit,answer,json_frames,TrimmedAnswer
from .base import Processor
from ..reply import Reply


class OpenAICompatProcessor(Processor):
    def __init__(self, mcfg: dict, *, raise_errors=False):
        self.raise_errors = raise_errors
        self.backend = mcfg.get('backend', 'openai')
        self.provider = mcfg.get('provider') or self.backend
        self.url = mcfg.get('url', 'http://127.0.0.1:8642/v1/chat/completions')
        self.model = mcfg.get('model', 'hermes-agent')
        self.agent = mcfg.get('agent', 'default')
        self.api_key = mcfg.get('api_key', '')
        self.timeout = mcfg.get('timeout', 300)
        self.max_history = max(1, int(mcfg.get('max_history', 10)))
        self.system_prompt = mcfg.get('system_prompt', '')
        self.histories = {}
        self.epochs = {}
        self.session_ids = {}
        self.session_state = mcfg.get('session_state') if self.backend in ('hermes', 'openclaw') else None

    def _state_id(self, key):
        return hashlib.sha256(repr((self.backend, self.url, self.agent, key)).encode('utf-8')).hexdigest()

    def _state(self, key, *, save=False):
        if not self.session_state:
            return
        path = Path(self.session_state)
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=30) as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (scope TEXT PRIMARY KEY, epoch TEXT NOT NULL, sid TEXT NOT NULL)')
            if save:
                db.execute('INSERT INTO sessions VALUES (?, ?, ?) ON CONFLICT(scope) DO UPDATE SET epoch=excluded.epoch,sid=excluded.sid',
                           (self._state_id(key), self.epochs.get(key, ''), self.session_ids.get(key, '')))
            else:
                row = db.execute('SELECT epoch,sid FROM sessions WHERE scope=?', (self._state_id(key),)).fetchone()
                if row:
                    self.epochs[key] = row[0]
                    if row[1]:
                        self.session_ids[key] = row[1]
                    else:
                        self.session_ids.pop(key, None)

    def _key(self, contact, channel_type):
        return (channel_type, contact)

    def _memory_scope(self, key):
        digest = hashlib.sha256(key[1].encode('utf-8')).hexdigest()
        return f'wxbot:{key[0]}:{digest}'

    def _session(self, key):
        self._state(key)
        return self._memory_scope(key) + self.epochs.get(key, '')

    def reset(self, contact, *, channel_type='dm', member_key='', **kwargs):
        key = self._key(contact, channel_type)
        self.histories.pop(key, None)
        self.session_ids.pop(key, None)
        self.epochs[key] = ':' + uuid.uuid4().hex
        self._state(key, save=True)

    def handle(self, contact, text):
        return self.handle_reply(contact, text).text

    def _request(self, messages, key, request_id):
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        model = self.model
        if self.backend == 'openclaw':
            model = f'openclaw/{self.agent}'
            headers.update({'x-openclaw-agent-id': self.agent,
                            'x-openclaw-session-key': self._session(key)})
        elif self.backend == 'hermes':
            headers['X-Hermes-Session-Key'] = self._memory_scope(key)
            headers['X-Hermes-Session-Id'] = self.session_ids.get(key, self._session(key))
            if request_id is not None:
                headers['Idempotency-Key'] = hashlib.sha256(
                    (self._session(key) + ':' + str(request_id)).encode()).hexdigest()
        body = {'model': model, 'messages': messages, 'stream': False}
        if self.backend in ('hermes', 'openclaw'):
            body['messages'] = [m for m in messages if m['role'] == 'system'] + [messages[-1]]
        return headers, body

    def _decode(self, data):
        if not isinstance(data, dict) or data.get('error'):
            raise ValueError('Model returned an error')
        choices = data.get('choices')
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError('Expected one complete model choice')
        choice = choices[0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError('Model reply is incomplete')
        message = choice.get('message', {})
        if message.get('tool_calls') or message.get('function_call'):
            raise ValueError('Unresolved model tool request')
        reply = message.get('content')
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError('Model reply has no final text')
        return reply.strip()

    def _stream_decode(self,response):
        pieces=[];finish=None;output=TrimmedAnswer()
        for data in json_frames(response.iter_lines()):
            if data=='[DONE]':
                if finish!='stop' or not ''.join(pieces).strip():raise ValueError('Model stream incomplete')
                return ''.join(pieces).strip()
            if not isinstance(data,dict) or data.get('error'):raise ValueError('Model stream failed')
            for choice in data.get('choices',[]):
                if choice.get('index',0)!=0:raise ValueError('Multiple model choices')
                delta=choice.get('delta') or {}
                if delta.get('tool_calls') or delta.get('function_call'):raise ValueError('Unresolved streaming tool request')
                text=delta.get('content')
                if text is not None:
                    if not isinstance(text,str) or finish is not None:raise ValueError('Invalid model stream delta')
                    pieces.append(text);output.feed(text)
                if choice.get('finish_reason') is not None:
                    finish=choice['finish_reason']
                    if finish!='stop':raise ValueError('Model stream incomplete')
        raise ValueError('Model stream disconnected before completion')

    def handle_reply(self, contact, text, *, request_id=None, member_key='', member_name='',on_event=None, **kwargs):
        streaming=on_event is not None and self.backend not in ('hermes','openclaw')
        with bind(on_event):
            emit('backend',provider=self.provider,model=self.model,streaming=streaming,
                 **({'fallback':'final_composition'} if not streaming else {}))
            try:
                result=self._handle_reply(contact,text,request_id=request_id,member_key=member_key,
                    member_name=member_name,_streaming=streaming,**kwargs)
                if not streaming:answer(result.text)
                emit('complete')
                return result
            except Exception as exc:
                if on_event is not None:exc.retry_safe=False
                emit('error',code=type(exc).__name__,retry_safe=False)
                raise

    def _handle_reply(self, contact, text, *, request_id=None, member_key='', member_name='',_streaming=False, **kwargs):
        key = self._key(contact, 'group' if member_key or kwargs.get('channel_type') == 'group' else 'dm')
        history = self.histories.get(key, [])
        messages = ([{'role':'system','content':self.system_prompt}] if self.system_prompt else []) + history + [{'role':'user','content':text}]
        headers, body = self._request(messages, key, request_id)
        # Errors propagate in every mode: a failed turn must never become a delivered reply.
        if _streaming:body['stream']=True
        response = requests.post(self.url, headers=headers, json=body, timeout=self.timeout,
                                 **({'stream':True} if _streaming else {}))
        try:
            response.raise_for_status()
            if _streaming and 'application/json' in getattr(response,'headers',{}).get('Content-Type','').lower():
                emit('backend',provider=self.provider,model=self.model,streaming=False,fallback='complete_result')
                reply=self._decode(response.json());answer(reply)
            else:
                reply = self._stream_decode(response) if _streaming else self._decode(response.json())
        finally:
            if _streaming:response.close()
        if self.backend == 'hermes':
            echoed = getattr(response, 'headers', {}).get('X-Hermes-Session-Id')
            if echoed:
                self.session_ids[key] = echoed
                self._state(key, save=True)
        self.histories[key] = (history + [{'role':'user','content':text}, {'role':'assistant','content':reply}])[-self.max_history*2:]
        return Reply.from_text(reply)
