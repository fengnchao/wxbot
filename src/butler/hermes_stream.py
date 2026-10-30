"""Read Hermes progress events while buffering one complete response for wxbot."""
import json
import time

from common.flow_trace import record
from common.model_stream import emit


class StreamError(ValueError):
    def __init__(self,message,code='invalid_stream'):
        super().__init__(message)
        self.code=code


def frames(response, deadline):
    event, data, size = '', [], 0
    while True:
        if time.monotonic()>deadline:
            raise TimeoutError('Hermes stream deadline exceeded')
        raw = response.readline(262145)
        if not raw:
            break
        size += len(raw)
        if len(raw)>262144 or size>8*1024*1024:
            raise StreamError('Hermes stream exceeds size limit')
        line = raw.decode('utf-8').rstrip('\r\n')
        if not line:
            if data:
                yield event, '\n'.join(data)
            event, data = '', []
        elif line.startswith('event:'):
            event = line[6:].lstrip()
        elif line.startswith('data:'):
            data.append(line[5:].lstrip())
    # An unfinished frame at EOF is not a confirmed completion.


def read_complete(response, timeout):
    emit('backend',provider='hermes',streaming=False,fallback='final_composition')
    final_text, completion_id, finish, generating = None, None, None, False
    for event,raw in frames(response,time.monotonic()+timeout):
        if raw=='[DONE]':
            if finish!='stop':
                raise StreamError('Hermes stream ended without a complete response')
            if final_text is None:
                raise StreamError('Hermes 未提供本轮最终正文事件，请更新并重启 Hermes', 'missing_final_response')
            return final_text.strip()
        data = json.loads(raw)
        if not isinstance(data,dict) or data.get('error'):
            raise StreamError('Hermes stream returned an error')
        if event=='hermes.final_response':
            if (not completion_id or data.get('id')!=completion_id or final_text is not None or
                    data.get('completed') is not True or data.get('partial') or data.get('failed') or
                    not isinstance(data.get('content'),str)):
                raise StreamError('Hermes final response is invalid or belongs to another request')
            final_text=data['content']
            continue
        if event=='hermes.tool.progress':
            status = data.get('status')
            if status in ('running','completed','failed'):
                emit('tool',status=status,tool=data.get('tool',''))
                record('hermes_tool',status,tool=data.get('tool',''),tool_call_id=data.get('toolCallId',''))
            continue
        if event=='approval.request':
            record('hermes_approval','waiting')
            continue
        if event=='hermes.status':
            record('hermes_status','running')
            continue
        if event and event!='message':
            continue
        if 'id' in data:
            if not isinstance(data['id'],str) or not data['id'] or (completion_id and data['id']!=completion_id):
                raise StreamError('Hermes completion ID changed within a response')
            completion_id=data['id']
        flags = data.get('hermes') or {}
        if flags.get('completed') is False or flags.get('failed') or flags.get('partial'):
            raise StreamError('Hermes response is incomplete')
        for choice in data.get('choices',[]):
            if choice.get('index',0)!=0:
                continue
            delta = choice.get('delta') or {}
            text = delta.get('content')
            if text is not None:
                if not isinstance(text,str):
                    raise StreamError('Invalid Hermes content delta')
                if text and not generating:
                    record('hermes_generating','running')
                    generating = True
            if choice.get('finish_reason') is not None:
                finish = choice['finish_reason']
                if finish!='stop':
                    raise StreamError('Hermes did not finish normally')
    raise StreamError('Hermes stream disconnected before completion')
