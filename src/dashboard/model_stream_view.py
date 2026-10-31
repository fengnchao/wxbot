"""Bounded, read-only model identity and public stream projection."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3


LABELS={'codex':'Codex','hermes':'Hermes','openclaw':'OpenClaw','cursor':'Cursor',
        'deepseek':'DeepSeek','openai':'OpenAI 兼容接口','responses':'Responses 接口',
        'ollama':'Ollama','echo':'Echo','custom':'自定义 API','external':'外部智能体'}


def resolve_model(wx,bt):
    installation=wx.get('installation') or {}
    model=wx.get('model') or {}
    transport=model.get('backend','butler')
    via=transport=='butler'
    if via and installation.get('mode')=='external':
        provider,name='external',''
    elif via:
        provider=(bt.get('agent') or {}).get('provider','hermes')
        settings=(bt.get('codex') or {}) if provider=='codex' else (bt.get('model') or bt.get('hermes') or {})
        name=settings.get('model','')
        provider=settings.get('provider') or provider
    else:
        provider=installation.get('provider') or transport
        name=model.get('model','')
    return {'provider':str(provider)[:64], 'label':str((model.get('display_name') if not via else '') or LABELS.get(provider,'模型'))[:100],
            'model':str(name)[:150],'via_butler':via}


def public_event(event):
    if not isinstance(event,dict):return None
    kind=event.get('type')
    fields={'backend':('provider','model','streaming','fallback'),
            'summary_delta':('text',),'answer_delta':('text','sendable'),
            'tool':('tool','status'),'complete':('status',),'error':('code','message','status')}.get(kind)
    if fields is None:return None
    result={'type':kind}
    for key in fields:
        value=event.get(key)
        if type(value) is bool:result[key]=value
        elif isinstance(value,str):result[key]=value[:8192 if key=='text' else 256]
    return result


def read_stream(path,record_id,*,after=0):
    if (not isinstance(record_id,str) or not re.fullmatch(r'(?:push:|inbox:|tg:)?[A-Za-z0-9:_-]{1,128}',record_id)
            or type(after)is not int or not 0<=after<=2**63-1):raise ValueError('消息标识或读取位置无效')
    result={'id':record_id,'available':False,'cursor':after,'events':[],'reset':False,'more':False}
    path=Path(path)
    if not path.is_file() or ':' in record_id:return result
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
        db.execute('BEGIN')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='model_stream_events'").fetchone():return result
        result['available']=True
        bounds=db.execute('SELECT MIN(seq),MAX(seq) FROM model_stream_events WHERE batch_id=?',(record_id,)).fetchone()
        if bounds[0] is None:return result
        if after and (after<bounds[0]-1 or after>bounds[1]):
            result['reset']=True;after=0
        rows=db.execute('SELECT seq,event FROM model_stream_events WHERE batch_id=? AND seq>? ORDER BY seq LIMIT 300',
                        (record_id,after)).fetchall()
        for seq,raw in rows:
            result['cursor']=seq
            try:event=public_event(json.loads(raw))
            except (ValueError,TypeError):continue
            if event:result['events'].append({'seq':seq,**event})
        result['more']=result['cursor']<bounds[1]
        return result


def latest_model(path,record_id,configured):
    """The event producer reports the backend actually used for this request."""
    path=Path(path)
    if not path.is_file():return configured
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='model_stream_events'").fetchone():return configured
            rows=db.execute('SELECT event FROM model_stream_events WHERE batch_id=? ORDER BY seq DESC LIMIT 300',(record_id,)).fetchall()
        for (raw,) in rows:
            event=public_event(json.loads(raw))
            if event and event['type']=='backend' and event.get('provider'):
                provider=event['provider']
                return {**configured,'provider':provider,'label':LABELS.get(provider,'模型'),
                        'model':event.get('model',''),'streaming':event.get('streaming',False)}
    except (sqlite3.Error,ValueError,OSError):pass
    return configured
