"""Read-only homepage projection. A message occupies exactly one current node."""
from collections import defaultdict
import hashlib
from pathlib import Path
import sqlite3
import time

from .flow_view import FlowView, read_trace


NODES = [
    ('received', 'wxbot · 微信收件', '检测消息并确认入库'),
    ('inbox', '收件队列', 'wxbot · 连续消息合并 / 等待提交'),
    ('butler', 'Butler · 接收与调度', '身份、角色、权限与会话'),
    ('model', '模型处理', '生成回复 / 执行允许的工具'),
    ('result', 'Butler · 完整结果', '只接收完整回复，准备投递'),
    ('outbox', '发件队列', 'wxbot · 按会话顺序等待发送'),
    ('sending', 'wxbot · 微信发送', '选择会话，分批输入'),
    ('confirmed', '发送确认', '确认自己的新消息气泡'),
]
EVENT_NODE = dict(wxbot_received=0, wxbot_inbox=1, wxbot_merge=1, wxbot_model=1, wxbot_butler=2,
                  butler_received=2, butler_session=2, hermes_request=3, hermes_tool=3,
                  hermes_generating=3, hermes_status=3, hermes_approval=3, hermes_result=4,
                  butler_action=4, butler_result=4, wxbot_result=5, wxbot_outbox=5, wechat_submitted=6)
EVENT_NODE.update(butler_identity=2,butler_memory=2,butler_context=2,wxbot_group_context=2,
                  wxbot_group_decision=1,wechat_mention=6)
IGNORED = {'not_started', 'unconfirmed', 'missing'}


def event_node(event):
    if event['stage']=='wxbot_result' and event['status']=='archived':
        return 2
    if event['stage'] == 'wechat_delivery':
        return {'pending':5, 'sending':6, 'confirming':7, 'sent':7}.get(event['status'], 6)
    # An unsuccessful result is still a model failure, not a completed result.
    if event['stage'] == 'hermes_result' and event['status'] not in ('ok', 'completed'):
        return 3
    return EVENT_NODE.get(event['stage'], 2)


class WorkflowView:
    ACTIVE_LIMIT = 500
    HISTORY_LIMIT = 60

    def __init__(self, queue_options, trace_paths, *, contacts=(), backend='codex'):
        self.flow = FlowView(queue_options, trace_paths)
        self.contacts = {c['name']: c for c in contacts if c.get('name')}
        self.backend = backend if backend in ('codex', 'hermes') else 'unknown'

    def read(self, *, now=None):
        now = time.time() if now is None else now
        result = dict(status='ok', read_only=True, at=now, backend=self.backend, messages=[],
                      nodes=[dict(id=i, key=k, label=l, description=d) for i,(k,l,d) in enumerate(NODES)],
                      counts={}, sources=[], active_more=False, history_more=False, error='')
        traces = defaultdict(list)
        for index, path in enumerate(self.flow.trace_paths):
            events, source = read_trace(path)
            result['sources'].append({'name':'wxbot' if index == 0 else 'Butler',
                                      'status':source['status'], 'truncated':source['truncated']})
            for event in events:
                traces[event['contact'], event['request_id']].append(event)
        path = Path(self.flow.queue.path)
        if not path.is_file():
            result.update(status='missing', error='尚无队列数据库。启动 wxbot 并收到消息后显示流转。')
            return result
        db = None
        try:
            db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=2)
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            # Select active rows independently so recent history can never hide a stuck task.
            selection = """SELECT 'inbox' kind, CAST(id AS TEXT) id, contact, received_at at, id seq, 0 terminal
                FROM inbox WHERE batch_id IS NULL
                UNION ALL SELECT 'batch',id,contact,COALESCE(finished_at,created_at),seq,state='done' FROM batches
                UNION ALL SELECT 'push',id,contact,COALESCE(finished_at,created_at),seq,state IN ('sent','skipped')
                FROM outbox WHERE batch_id IS NULL"""
            totals = dict(db.execute('SELECT terminal,COUNT(*) FROM ('+selection+') GROUP BY terminal'))
            rows = db.execute('SELECT * FROM ('+selection+') WHERE terminal=0 ORDER BY seq,kind,id LIMIT ?',
                              (self.ACTIVE_LIMIT,)).fetchall()
            rows += db.execute('SELECT * FROM ('+selection+') WHERE terminal=1 ORDER BY at DESC,seq DESC,id DESC LIMIT ?',
                               (self.HISTORY_LIMIT,)).fetchall()
            reasons = {name: self.flow.queue._reason(db, name, now) for name in {r['contact'] for r in rows}}
            result['messages'] = [self._message(db,r,reasons[r['contact']],traces,now) for r in rows]
            result['active_more'] = totals.get(0,0) > self.ACTIVE_LIMIT
            result['history_more'] = totals.get(1,0) > self.HISTORY_LIMIT
            scalar = lambda sql: db.execute(sql).fetchone()[0]
            result['counts'] = dict(
                active=totals.get(0,0),
                inbox=scalar('SELECT COUNT(*) FROM inbox WHERE batch_id IS NULL'),
                model=scalar("SELECT COUNT(*) FROM batches WHERE state='processing' AND reply_mode NOT IN ('none','emoji')"),
                outbox=scalar("SELECT COUNT(*) FROM outbox WHERE state NOT IN ('sent','skipped')"),
                issues=scalar("SELECT COUNT(*) FROM batches b WHERE state IN ('blocked','uncertain') AND NOT EXISTS (SELECT 1 FROM outbox o WHERE o.batch_id=b.id)")+
                       scalar("SELECT COUNT(*) FROM outbox WHERE state IN ('blocked','uncertain')"),
                sent=scalar("SELECT COUNT(*) FROM outbox WHERE state='sent'"))
        except (sqlite3.Error, ValueError, OSError) as exc:
            result.update(status='error', error='工作流数据读取失败（'+type(exc).__name__+'）', messages=[], counts={})
        finally:
            if db is not None:
                db.close()
        return result

    def _message(self, db, row, reason, traces, now):
        kind = row['kind']
        table = {'inbox':'inbox','batch':'batches','push':'outbox'}[kind]
        item = db.execute(f'SELECT * FROM {table} WHERE id=?', (row['id'],)).fetchone()
        if kind == 'push':
            flow = dict(id='push:'+row['id'], request_id='', contact=row['contact'], preview=item['text'][:240],
                        at=item['created_at'], state=item['state'], reason={}, inbox_ids=[], message_count=0,
                        events=[dict(stage='wechat_delivery',status=item['state'],
                                     ts=item['finished_at'] or item['submitted_at'] or item['created_at'], delivery_id=item['id'])])
            incoming, deliveries = [], [item]
        else:
            flow_row = {**dict(row), 'at':item['created_at'] if kind=='batch' else item['received_at']}
            flow = self.flow._flow(db,flow_row,reason,traces)
            incoming = (db.execute('SELECT * FROM inbox WHERE batch_id=? ORDER BY id',(row['id'],)).fetchall()
                        if kind == 'batch' else [item])
            deliveries = db.execute('SELECT * FROM outbox WHERE batch_id=? ORDER BY seq',(row['id'],)).fetchall() if kind == 'batch' else []
        contact = self.contacts.get(row['contact'], {})
        if incoming:
            flow['events'].append(dict(stage='wxbot_inbox',status='ok',ts=min(r['received_at'] for r in incoming)))
        for delivery in deliveries:
            metadata = dict(delivery_id=delivery['id'], part_seq=delivery['part_seq'], part_count=len(deliveries))
            flow['events'].append(dict(stage='wxbot_outbox',status='ok',ts=delivery['created_at'],**metadata))
            if delivery['submitted_at'] is not None:
                flow['events'].append(dict(stage='wechat_submitted',status='ok',ts=delivery['submitted_at'],**metadata))
        for event in flow['events']:
            if event['stage']=='wechat_delivery' and event['status']=='sending':
                # Queue persists current typing state, but has no typing-start timestamp.
                event['time_unknown'] = True
        flow.update(kind=kind, uid=str(contact.get('uid') or row['contact']),
                    label=str(contact.get('label') or row['contact']),
                    group=contact.get('channel_type')=='group' or any(r['group_mode'] for r in incoming),
                    members=sorted({r['member_key'] for r in incoming if r['member_key']}),
                    terminal=bool(row['terminal']), scope='complete' if row['terminal'] else 'active',
                    attempts=item['attempts'] if kind=='batch' else 0, error='',
                    part_count=len(deliveries), sent_parts=sum(d['state']=='sent' for d in deliveries),
                    retry_at=None, discard_at=None, order=row['seq'])
        clean = []
        for e in flow['events']:
            if e['status'] in IGNORED or e.get('ts') is None:
                continue
            e = {k:v for k,v in e.items() if k not in ('source','blocker_id')}
            e['node'] = event_node(e)
            identity = (flow['id'],e['stage'],e['status'],e['ts'],e.get('delivery_id'),e.get('tool_call_id'))
            e['key'] = str(e.get('event_id') or hashlib.sha256(repr(identity).encode()).hexdigest()[:24])
            clean.append(e)
        clean.sort(key=lambda e:(e['ts'],e['node'],e['key']))
        flow['events'] = clean[-200:]
        flow['events_truncated'] = len(clean)>200
        current = [e for e in clean if kind!='batch' or e['ts']>=(item['started_at'] or 0)]
        progress = [e['node'] for e in current if not (e['stage']=='wxbot_result' and e['status']!='ok')]
        flow['stage'] = max(progress, default=1)
        flow['status'] = flow['state']
        flow['updated_at'] = max([flow['at'],*(e['ts'] for e in clean)])
        if kind == 'inbox' or (kind=='batch' and item['state']=='ready'):
            flow['stage'] = 1
        if deliveries:
            active = next((d for d in deliveries if d['state'] not in ('sent','skipped')), None)
            chosen = active or deliveries[-1]
            flow['stage'] = event_node(dict(stage='wechat_delivery',status=chosen['state']))
            flow['status'] = chosen['state']
            flow['order'] = chosen['seq']
            flow['reply_preview'] = chosen['text'][:240]
            flow['delivery_id'] = chosen['id']
            flow['error'] = chosen['error'] or ''
            if chosen['state'] in ('blocked','uncertain'):
                flow.update(self.flow.queue._deadline(chosen,now,self.flow.queue.failure_timeout_seconds))
                flow['scope'] = 'issues'
            if not active and any(d['state']=='skipped' for d in deliveries):
                flow.update(status='discarded', scope='issues', stage=6,
                            error=next((d['error'] for d in deliveries if d['state']=='skipped' and d['error']), '部分回复已丢弃'))
        elif kind=='batch' and item['state']=='done':
            if flow['state']=='archived':
                flow.update(status='archived',stage=2)
            elif item['reply_complete']:
                flow.update(status='no_reply',stage=4)
            else:
                flow.update(status='model_failed',scope='issues',error=item['error'] or '批次已结束，未生成完整回复')
        if kind=='batch' and not deliveries and item['state'] in ('blocked','uncertain'):
            from wxbot.model_recovery import model_failure_info
            flow.update(model_failure_info(db,item,now,self.flow.queue.failure_timeout_seconds))
            flow.update(scope='issues',error=item['error'])
        elif kind=='inbox' and reason.get('code') in ('blocked','uncertain','state_mismatch'):
            flow.update(scope='issues',status='waiting_blocker',error=reason.get('error') or reason['message'])
            for key in ('retry_at','discard_at'):
                flow[key] = reason.get(key)
        # Do not expose command paths or unrelated historical blockers on the overview.
        flow['reason'] = {k:v for k,v in flow.get('reason',{}).items() if k in ('code','message','record_id','error')}
        return flow
