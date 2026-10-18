"""Append-only, payload-free flow events shared by wxbot and Butler."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
from pathlib import Path
import re
import threading
import time
import uuid


_current = ContextVar('message_flow', default=None)
_write_lock = threading.Lock()
EVENT_FIELDS = {'elapsed_ms', 'http_status', 'error_type', 'error_code', 'profile', 'session_id',
           'tool', 'tool_call_id', 'characters', 'part_count', 'progress_available', 'attempt'}


def queue_trace_path(database):
    return None if str(database)==':memory:' else Path(database).with_suffix('.flow.jsonl')


def butler_trace_path(flow_file):
    return Path(str(flow_file)+'.events.jsonl') if flow_file else None


class FlowTrace:
    def __init__(self, path, log=None):
        self.path = Path(path) if path else None
        self.log = log

    @contextmanager
    def bind(self, contact, request_id):
        token = _current.set((self, str(contact), str(request_id)))
        try:
            yield
        finally:
            _current.reset(token)

    def emit(self, contact, request_id, stage, status, **fields):
        event = {'event_id':uuid.uuid4().hex, 'ts':time.time(), 'contact':str(contact)[:256],
                 'request_id':str(request_id)[:128], 'stage':stage, 'status':status}
        for key,value in fields.items():
            if key in EVENT_FIELDS and isinstance(value,(str,int,float,bool)):
                if key=='tool' and not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,128}',str(value)):
                    continue
                event[key] = value[:256] if isinstance(value,str) else value
        # Never persist prompts, reasoning, tool arguments/results, headers, or raw exceptions.
        try:
            if self.path:
                with _write_lock:
                    self.path.parent.mkdir(parents=True,exist_ok=True)
                    with self.path.open('a',encoding='utf-8') as fh:
                        fh.write(json.dumps(event,ensure_ascii=False)+'\n')
        except Exception:
            pass  # Observability failure must not fail or replay a user's request.
        if self.log:
            try:
                self.log('[流转][%s][%s] %s=%s',contact,request_id,stage,status)
            except Exception:
                pass


def tracing():
    return _current.get() is not None


def record(stage, status, **fields):
    bound = _current.get()
    if bound:
        sink,contact,request_id = bound
        sink.emit(contact,request_id,stage,status,**fields)
