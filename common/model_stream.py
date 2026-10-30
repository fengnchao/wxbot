"""Public, bounded model observations scoped to one synchronous request.

Adapters explicitly choose public fields; private reasoning and tool arguments
never cross this boundary. Callback errors stop generation rather than allowing
delivery to outrun the durable consumer.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_callback = ContextVar('model_stream_callback', default=None)
_FIELDS = {
    'backend': {'provider','model','streaming','label','fallback','mention_name'},
    'summary_delta': {'text'},
    'tool': {'tool','status'},
    'answer_delta': {'text','sendable'},
    'complete': set(),
    'error': {'code','retry_safe'},
}


@contextmanager
def bind(callback):
    token = _callback.set(callback)
    try:
        yield
    finally:
        _callback.reset(token)


def active():
    return _callback.get() is not None


def emit(kind, **fields):
    callback = _callback.get()
    if callback is None or kind not in _FIELDS:
        return
    event = {'type':kind}
    for key in _FIELDS[kind]:
        value = fields.get(key)
        if isinstance(value,str):
            event[key] = value[:8192 if key=='text' else 300]
        elif type(value) is bool:
            event[key] = value
    callback(event)


def answer(text, *, sendable=True):
    """Do not truncate a complete answer when transporting bounded events."""
    for offset in range(0,len(text or ''),8192):
        emit('answer_delta',text=text[offset:offset+8192],sendable=sendable)


class TrimmedAnswer:
    """Incremental equivalent of str.strip, withholding provisional whitespace."""
    def __init__(self):
        self.started=False;self.pending='';self.text=''

    def feed(self,value):
        value=self.pending+value
        if not self.started:value=value.lstrip()
        stable=value.rstrip()
        self.pending=value[len(stable):]
        if stable:
            self.started=True;self.text+=stable;answer(stable)


def json_frames(lines):
    """Decode bounded SSE JSON; unfinished EOF frames are always invalid."""
    import json
    data=[];size=0;total=0
    for raw in lines:
        line=raw.decode('utf-8') if isinstance(raw,bytes) else raw
        line=line.rstrip('\r\n')
        total+=len(line)
        if total>8*1024*1024 or len(line)>262144:
            raise ValueError('Model stream exceeds size limit')
        if not line:
            if data:
                value='\n'.join(data)
                yield value if value=='[DONE]' else json.loads(value)
            data=[];size=0
        elif line.startswith('data:'):
            value=line[5:].lstrip();size+=len(value)
            if size>262144:raise ValueError('Model stream frame exceeds size limit')
            data.append(value)
    if data:raise ValueError('Model stream ended inside a frame')
