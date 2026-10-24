"""Read-only queue diagnostics. Never initialize/recover/migrate a queue."""
import json
from pathlib import Path
import sqlite3
import time

from wxbot.queue_schema import is_latest
from wxbot.queue_store import FAILURE_TIMEOUT_SECONDS,FAILURE_DETAIL_FIELDS
from wxbot.model_recovery import model_failure_info


TERMINAL = ('sent', 'skipped')


class QueueView:
    def __init__(self, path, *, quiet=3, max_wait=10, prefix='/',failure_timeout_seconds=FAILURE_TIMEOUT_SECONDS):
        self.path = str(path)
        self.quiet, self.max_wait, self.prefix = quiet, max_wait, prefix
        from wxbot.config import validate_failure_timeout
        self.failure_timeout_seconds=validate_failure_timeout(failure_timeout_seconds)

    def read(self, *, contact='', state='all', limit=50, offset=0, now=None,
             offsets=None, scope='', order=''):
        limit, offset = max(1, min(200, int(limit))), max(0, int(offset))
        offsets=offsets or {}
        scope=scope if scope in ('all','active','issues','history') else ''
        result = {'read_only': True, 'database': self.path, 'at': time.time() if now is None else now,
                  'status': 'ok', 'contacts': [], 'counts': {}, 'pages': {},
                  'inbox': [], 'batches': [], 'outbox': [], 'events':[], 'error': '',
                  'actions_enabled':False,'failure_timeout_seconds':self.failure_timeout_seconds}
        path = Path(self.path)
        if self.path == ':memory:' or not path.is_file():
            result.update(status='missing', error='没有可读取的磁盘队列（尚未创建或使用内存队列）')
            return result
        db = None
        try:
            db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=2)
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')  # All summaries and rows describe one consistent snapshot.
            result['actions_enabled']=is_latest(db)
            for table in ('inbox', 'batches', 'outbox', 'pending_sessions'):
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    raise ValueError('缺少队列表')
            result['counts'] = {'unbatched': db.execute('SELECT COUNT(*) FROM inbox WHERE batch_id IS NULL').fetchone()[0],
                                'pending_sessions': db.execute('SELECT COUNT(*) FROM pending_sessions').fetchone()[0]}
            for table in ('batches', 'outbox'):
                result['counts'][table] = dict(db.execute(f'SELECT state,COUNT(*) FROM {table} GROUP BY state'))
            names = [r[0] for r in db.execute('''SELECT contact FROM inbox UNION SELECT contact FROM batches
                UNION SELECT contact FROM outbox UNION SELECT contact FROM pending_sessions ORDER BY contact''')]
            for name in names:
                summary = {'contact': name,
                           'unbatched': db.execute('SELECT COUNT(*) FROM inbox WHERE contact=? AND batch_id IS NULL', (name,)).fetchone()[0],
                           'batches': dict(db.execute('SELECT state,COUNT(*) FROM batches WHERE contact=? GROUP BY state', (name,))),
                           'outbox': dict(db.execute('SELECT state,COUNT(*) FROM outbox WHERE contact=? GROUP BY state', (name,)))}
                summary['reason'] = self._reason(db, name, result['at'])
                result['contacts'].append(summary)
            result['contacts'].sort(key=lambda row: (row['reason']['code']=='idle', row['contact']))
            for table in ('inbox', 'batches', 'outbox'):
                terms, args = [], []
                if table == 'inbox':
                    if scope!='all':terms.append('batch_id IS NULL')
                    elif state in ('active','unbatched'):terms.append('batch_id IS NULL')
                    if state not in ('all', 'active', 'unbatched'):
                        terms.append('0')
                elif state == 'active':
                    terms.append("state NOT IN ('done','sent','skipped')")
                elif state != 'all':
                    terms.append('state=?')
                    args.append(state)
                if contact:
                    terms.append('contact=?')
                    args.append(contact)
                if scope and scope!='all':
                    if table=='inbox':
                        if scope!='active':terms.append('0')
                    elif scope=='issues':terms.append("state IN ('blocked','uncertain')")
                    elif scope=='history':terms.append("state IN ('done','sent','skipped')")
                    else:terms.append("state NOT IN ('done','sent','skipped')")
                where = ' WHERE '+' AND '.join(terms) if terms else ''
                total = db.execute(f'SELECT COUNT(*) FROM {table}'+where, args).fetchone()[0]
                stable = 'id' if table == 'inbox' else 'seq'
                direction='DESC' if order=='desc' or (not order and scope in ('all','history')) else 'ASC'
                sorting=f'{stable} {direction}'
                if scope=='issues':
                    columns={r[1] for r in db.execute(f'PRAGMA table_info({table})')}
                    failure='COALESCE(failed_at,created_at)' if 'failed_at' in columns else 'COALESCE(finished_at,created_at)'
                    if table!='inbox':sorting=f'{failure} ASC,{stable} ASC'
                page_offset=max(0,int(offsets.get(table,offset)))
                page_offset=min(page_offset,((max(total,1)-1)//limit)*limit)
                rows = db.execute(f'SELECT * FROM {table}'+where+f' ORDER BY {sorting} LIMIT ? OFFSET ?',
                                  [*args, limit, page_offset]).fetchall()
                result[table] = [self._row(db, table, row,now=result['at'],failure_timeout_seconds=self.failure_timeout_seconds) for row in rows]
                result['pages'][table] = {'total': total, 'offset': page_offset, 'limit': limit,
                                          'has_more': page_offset+len(rows) < total}
            from .reply_rounds import read_rounds
            result['rounds'],result['pages']['rounds']=read_rounds(db,self._row,contact=contact,state=state,
                scope=scope,limit=limit,offset=max(0,int(offsets.get('rounds',0))),now=result['at'],timeout=self.failure_timeout_seconds)
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='delivery_events'").fetchone():
                where=' WHERE contact=?' if contact else ''
                args=[contact] if contact else []
                events=db.execute('SELECT * FROM delivery_events'+where+' ORDER BY seq DESC LIMIT 50',args).fetchall()
                for event in events:
                    data=dict(event)
                    try:
                        details=json.loads(data['details'])
                        data['details']={k:v for k,v in details.items() if k in FAILURE_DETAIL_FIELDS}
                    except (ValueError,TypeError,AttributeError):data['details']={}
                    result['events'].append(data)
        except (sqlite3.Error, ValueError, OSError) as exc:
            result.update(status='error', error='队列不可读取（'+type(exc).__name__+'）',
                          contacts=[], counts={}, pages={}, inbox=[], batches=[], outbox=[],
                          events=[],actions_enabled=False)
        finally:
            if db is not None:
                db.close()
        return result

    def _reason(self, db, name, now):
        modern='detached' in {r[1] for r in db.execute('PRAGMA table_info(outbox)')}
        active=' AND detached=0' if modern else ''
        hold=db.execute('SELECT * FROM outbox WHERE contact=? AND manual_required=1 ORDER BY seq LIMIT 1',(name,)).fetchone() if modern else None
        outgoing = db.execute("SELECT * FROM outbox WHERE contact=? AND state NOT IN ('sent','skipped')"+active+" ORDER BY seq LIMIT 1", (name,)).fetchone()
        problem = db.execute("SELECT * FROM outbox WHERE contact=? AND state IN ('blocked','uncertain')"+active+" ORDER BY seq LIMIT 1", (name,)).fetchone()
        batch = db.execute("SELECT * FROM batches WHERE contact=? AND state!='done' ORDER BY seq LIMIT 1", (name,)).fetchone()
        def reason(code, message, kind='', row=None, **extra):
            data = {'code': code, 'message': message, 'record_kind': kind,
                    'record_id': row['id'] if row else '', 'state': row['state'] if row else '',
                    'error': row['error'] if row else '', **extra}
            if code in ('blocked','uncertain') and row:
                data['commands'] = self._commands(kind, row['id'])
                data['finished_at']=row['finished_at']
                if kind=='batches':data['attempts']=row['attempts']
                data['actions']=self._actions(db,kind,row)
                if kind=='outbox':data.update(self._deadline(row,now,self.failure_timeout_seconds))
            return data
        if hold:
            return reason('blocked','输入框需要人工清理；清理后点击重试或丢弃解除此会话暂停','outbox',hold)
        if problem:
            return reason(problem['state'], '本轮回复发送失败，等待重试或整轮超时结束', 'outbox', problem)
        if batch and batch['state'] in ('blocked','uncertain'):
            if db.execute('SELECT 1 FROM outbox WHERE batch_id=? LIMIT 1', (batch['id'],)).fetchone():
                return reason('state_mismatch', '批次状态与分句状态不一致，请核对运行中的 wxbot 版本及日志')
            info=model_failure_info(db,batch,now,self.failure_timeout_seconds)
            message=('模型初始化失败，等待自动重试' if info['retry_at'] is not None else
                     '模型结果未知，不重放本条；到期结束失败批次并放行后续消息')
            return reason(batch['state'],message,'batches',batch,**info)
        if batch and batch['state'] in ('ready','processing'):
            return reason(batch['state'], '已提交，等待模型完整回复' if batch['state']=='processing' else '待提交模型，等待请求槽位', 'batches', batch)
        if outgoing:
            labels = {'pending':'回复已就绪，等待发送', 'sending':'正在分批键入，界面暂不切换',
                      'confirming':'已回车，等待确认新增自己的消息气泡'}
            return reason(outgoing['state'], labels.get(outgoing['state'], '等待上一条回复结束'), 'outbox', outgoing,
                          wait_seconds=max(0, outgoing['not_before']-now))
        pending = db.execute('SELECT 1 FROM pending_sessions WHERE contact=?', (name,)).fetchone()
        if pending:
            return reason('pending_capture', '还有未读消息等待采集，暂缓合并')
        rows = db.execute('SELECT * FROM inbox WHERE contact=? AND batch_id IS NULL ORDER BY id LIMIT 1000', (name,)).fetchall()
        if rows:
            # Reuse the pure production merge rule; this does not open a QueueStore.
            from wxbot.queue_store import QueueStore
            due, _ = QueueStore._candidate(rows, self.quiet, self.max_wait, self.prefix)
            return reason('merging' if now < due else 'ready_to_merge',
                          '等待连续消息合并' if now < due else '合并条件已满足，等待调度；请核对 wxbot 进程',
                          wait_seconds=max(0, due-now))
        if batch:
            return reason(batch['state'], '等待本轮回复完成', 'batches', batch)
        return reason('idle', '没有待处理任务')

    @staticmethod
    def _row(db, table, row, *, now=None,failure_timeout_seconds=FAILURE_TIMEOUT_SECONDS):
        # No message/confirmation snapshots in the API; bounded message preview only.
        keys = ('id','contact','state','created_at','received_at','started_at','submitted_at','finished_at',
                'not_before','attempts','batch_id','member_key','error','part_seq','reply_complete','failed_at','resolution','detached','manual_required','first_delivery_failure','delivery_resolution')
        result = {key: row[key] for key in keys if key in row.keys()}
        text = row['text'] or ''
        result.update(characters=len(text), preview=text[:240])
        if table == 'inbox':
            result['state'] = 'batched' if row['batch_id'] else 'unbatched'
        elif table == 'batches':
            result['part_count'] = db.execute('SELECT COUNT(*) FROM outbox WHERE batch_id=?', (row['id'],)).fetchone()[0]
            result['sent_parts'] = db.execute("SELECT COUNT(*) FROM outbox WHERE batch_id=? AND state='sent'",(row['id'],)).fetchone()[0]
            result['completed_parts'] = db.execute("SELECT COUNT(*) FROM outbox WHERE batch_id=? AND state IN ('sent','skipped')", (row['id'],)).fetchone()[0]
            complete=row['reply_complete'] if 'reply_complete' in row.keys() else False
            if not complete and not result['part_count']:
                if row['state'] in ('blocked','uncertain'):
                    result.update(model_failure_info(db,row,time.time() if now is None else now,failure_timeout_seconds))
                elif row['state']=='done' and row['error']:result['display_state']='model_failed'
        elif table == 'outbox':
            result['part_seq'] = row['part_seq'] if 'part_seq' in row.keys() else 1
            result['part_count'] = db.execute('SELECT COUNT(*) FROM outbox WHERE batch_id=?', (row['batch_id'],)).fetchone()[0] if row['batch_id'] else 1
            if 'failed_at' in row.keys() and row['state'] not in TERMINAL:
                result.update(QueueView._deadline(row,time.time() if now is None else now,failure_timeout_seconds))
        if result.get('detached') and row['state']=='uncertain':result['display_state']='review'
        elif result.get('resolution')=='restart_discard':result['display_state']='restart_discard'
        elif result.get('resolution')=='timeout':result['display_state']='timeout_discard'
        if result.get('manual_required'):result['display_state']='draft_hold'
        result['actions']=QueueView._actions(db,table,row) if table!='inbox' else []
        return result

    @staticmethod
    def _deadline(row,now,failure_timeout_seconds=FAILURE_TIMEOUT_SECONDS):
        if ('detached' in row.keys() and row['detached']) or ('state' in row.keys() and row['state'] in TERMINAL):return {}
        failed=(row['failed_at'] if 'failed_at' in row.keys() else
                next((row[k] for k in ('finished_at','submitted_at','created_at') if row[k] is not None),None))
        if failed is None:return {}
        return {'failed_at':failed,'discard_at':failed+failure_timeout_seconds,
                'remaining_seconds':max(0,failed+failure_timeout_seconds-now)}

    @staticmethod
    def _actions(db,kind,row):
        if not is_latest(db):return []
        if row['state'] not in ('blocked','uncertain') and not (kind=='outbox' and row['manual_required']):return []
        if kind=='outbox':return ['retry','sent','skip']
        if kind=='batches' and not db.execute('SELECT 1 FROM outbox WHERE batch_id=?',(row['id'],)).fetchone():
            return ['retry','skip']
        return []

    def _commands(self, kind, record_id):
        literal = lambda text: "'"+str(text).replace("'", "''")+"'"
        base = 'python -m wxbot.queue_admin --database '+literal(Path(self.path).resolve())+' '
        suffix = ' --delivery' if kind == 'outbox' else ''
        commands = {'retry':base+'retry '+literal(record_id)+suffix+' --acknowledge',
                    'skip':base+'skip '+literal(record_id)+suffix}
        if kind == 'outbox':
            commands['sent'] = base+'sent '+literal(record_id)
        return commands
