"""Join durable queue facts and exact request IDs without guessing service success."""
import json
import math
from pathlib import Path
import sqlite3
import time

from common.flow_trace import EVENT_FIELDS
from .queue_view import QueueView


STAGES = {'wxbot_model','wxbot_butler','butler_received','butler_session','hermes_request',
          'hermes_tool','hermes_status','hermes_approval','hermes_generating','hermes_result',
          'butler_action','butler_result','wxbot_result'}
MILESTONES = ('wxbot_butler','butler_received','hermes_request','hermes_result','wxbot_result','wechat_delivery')


def read_trace(path):
    source = {'path':str(path),'status':'ok','truncated':False}
    events=[]
    try:
        with Path(path).open('rb') as fh:
            size = fh.seek(0,2)
            source['truncated'] = size>4*1024*1024
            fh.seek(max(0,size-4*1024*1024))
            if source['truncated']:
                fh.readline()
            for raw in fh:
                if len(raw)>16384 or not raw.endswith(b'\n'):
                    continue
                try:
                    event=json.loads(raw)
                    if not isinstance(event,dict) or event.get('stage') not in STAGES:
                        continue
                    if (not isinstance(event.get('ts'),(int,float)) or not math.isfinite(event['ts']) or
                            not all(isinstance(event.get(k),str) for k in ('request_id','contact','status'))):
                        continue
                    allowed = EVENT_FIELDS | {'event_id','ts','contact','request_id','stage','status'}
                    events.append({k:v for k,v in event.items() if k in allowed and isinstance(v,(str,int,float,bool))})
                except (ValueError,TypeError,UnicodeError):
                    continue
    except FileNotFoundError:
        source['status']='missing'
    except OSError as exc:
        source.update(status='error',error=type(exc).__name__)
    return events,source


class FlowView:
    def __init__(self, queue_options, trace_paths):
        self.queue = QueueView(**queue_options)
        self.trace_paths = [Path(p) for p in trace_paths if p]

    def read(self, *, contact='', limit=50, offset=0, now=None, order='desc'):
        limit,offset=max(1,min(100,int(limit))),max(0,int(offset))
        now=time.time() if now is None else now
        result={'read_only':True,'status':'ok','at':now,'flows':[],'contacts':[],'sources':[],
                'total':0,'offset':offset,'limit':limit,'has_more':False,'error':''}
        traces={}
        for path in self.trace_paths:
            events,source=read_trace(path)
            result['sources'].append(source)
            for event in events:
                traces.setdefault((event['contact'],event['request_id']),[]).append(event)
        path=Path(self.queue.path)
        if self.queue.path==':memory:' or not path.is_file():
            result.update(status='missing',error='没有可读取的磁盘队列，无法确认 wxbot 收件')
            return result
        db=None
        try:
            db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
            db.row_factory=sqlite3.Row
            db.execute('BEGIN')
            names=[r[0] for r in db.execute('SELECT contact FROM inbox UNION SELECT contact FROM batches UNION SELECT contact FROM outbox')]
            reasons={name:self.queue._reason(db,name,now) for name in names}
            result['contacts']=[{'contact':name,'reason':reasons[name]} for name in names]
            where=' AND contact=?' if contact else ''
            selection=("SELECT 'inbox' kind,id,contact,received_at at FROM inbox WHERE batch_id IS NULL"+where+
                       " UNION ALL SELECT 'batch' kind,id,contact,created_at at FROM batches WHERE 1=1"+where)
            args=[contact,contact] if contact else []
            result['total']=db.execute('SELECT COUNT(*) FROM ('+selection+')',args).fetchone()[0]
            direction='ASC' if order=='asc' else 'DESC'
            rows=db.execute(selection+f' ORDER BY at {direction},id {direction} LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
            for row in rows:
                result['flows'].append(self._flow(db,row,reasons[row['contact']],traces))
            result['has_more']=offset+len(rows)<result['total']
        except (sqlite3.Error,ValueError,OSError) as exc:
            result.update(status='error',error='流转记录读取失败（'+type(exc).__name__+'）',flows=[],contacts=[])
        finally:
            if db is not None:
                db.close()
        return result

    def _flow(self,db,row,reason,traces):
        is_batch=row['kind']=='batch'
        table='batches' if is_batch else 'inbox'
        item=db.execute(f'SELECT * FROM {table} WHERE id=?',(row['id'],)).fetchone()
        flow={'id':str(row['id']) if is_batch else 'inbox:'+str(row['id']),
              'request_id':str(row['id']) if is_batch else '', 'contact':row['contact'],
              'preview':item['text'][:240],'at':row['at'],'state':item['state'] if is_batch else 'unbatched',
              'reason':reason,'events':[],'message_count':1,'inbox_ids':[]}
        def add(stage,status,ts,**extra):
            flow['events'].append({'stage':stage,'status':status,'ts':ts,'source':'queue',**extra})
        incoming=db.execute('SELECT id,received_at FROM inbox WHERE batch_id=? ORDER BY id',(row['id'],)).fetchall() if is_batch else [item]
        flow['inbox_ids']=[r['id'] for r in incoming]
        flow['message_count']=len(incoming)
        add('wxbot_received','ok',min((r['received_at'] for r in incoming),default=row['at']),characters=len(item['text']))
        if is_batch:
            add('wxbot_merge','ok',row['at'])
            flow['events'].extend(traces.get((row['contact'],str(row['id'])),[]))
            if item['started_at'] is not None and not any(e['stage']=='wxbot_model' for e in flow['events']):
                add('wxbot_model','started',item['started_at'])
            deliveries=db.execute('SELECT * FROM outbox WHERE batch_id=? ORDER BY seq',(row['id'],)).fetchall()
            if reason.get('record_id') not in {str(row['id']),*[r['id'] for r in deliveries]}:
                flow['reason']={'code':item['state'],'message':'此批次状态：'+item['state'],'record_id':row['id'],'error':item['error']}
            for d in deliveries:
                add('wechat_delivery',d['state'],d['finished_at'] or d['submitted_at'] or d['created_at'],
                    detail=d['error'],delivery_id=d['id'],part_seq=d['part_seq'] if 'part_seq' in d.keys() else 1,
                    part_count=len(deliveries))
            if item['state']=='done' and not item['reply_complete'] and item['error'] and not deliveries:
                flow['state']='model_failed'
                flow['reason']={'code':'model_failed','message':'模型失败批次已结束，后续消息可以继续处理',
                                'record_id':row['id'],'error':item['error']}
        else:
            status=reason['code'] if reason['code'] in ('blocked','uncertain') else 'waiting'
            add('wxbot_merge',status,None,detail=reason['message'],blocker_id=reason.get('record_id',''))
        flow['events'].sort(key=lambda e:e.get('ts') if e.get('ts') is not None else float('inf'))
        seen={e['stage'] for e in flow['events']}
        for stage in MILESTONES:
            if stage not in seen:
                add(stage,'unconfirmed' if is_batch else 'not_started',None)
        return flow
