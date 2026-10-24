"""Read-only Telegram ingress/news projection; never migrate or recover databases."""
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import tomllib

ISSUES = ('blocked', 'uncertain', 'rejected', 'not_submitted')
TERMINAL = ('sent', 'skipped', 'cancelled')


def timestamp(value):
    if isinstance(value, (int, float)):
        return value
    try:
        value = str(value)
        if '+' not in value and not value.endswith('Z'):
            value += '+00:00'  # SQLite CURRENT_TIMESTAMP is UTC.
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0


class TelegramView:
    def __init__(self, config_path, butler_path):
        self.config_path, self.butler_path = Path(config_path), Path(butler_path)

    def read(self, *, scope='all', state='all', contact='', limit=50, offset=0):
        result = dict(status='ok', error='', database='', rows=[], contacts=[], counts={},
                      page=dict(total=0, offset=0, limit=limit, has_more=False))
        if not self.config_path.exists():
            result.update(status='missing', error='Telegram 机器人尚未配置')
            return result
        try:
            cfg = tomllib.loads(self.config_path.read_text(encoding='utf-8-sig'))['telegram_bot']
            path = (self.config_path.parent / cfg.get('state_dir', 'data/telegram-bot') / 'relay.sqlite3').resolve()
            result['database'] = str(path)
            if not path.is_file():
                result.update(status='missing', error='Telegram 接收队列尚未创建')
                return result
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
                db.row_factory = sqlite3.Row
                db.execute('BEGIN')
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                news = {'news_plan', 'news_delivery'} <= tables
                if news:
                    selection = '''SELECT p.bot,p.uid,p.payload,p.state ingress_state,p.error,
                        COALESCE(n.reason,'') plan_reason,COALESCE(d.targets,'') targets,
                        CASE WHEN p.state='rejected' THEN 'rejected'
                          WHEN p.state!='received' THEN p.state
                          WHEN d.issues>0 THEN 'blocked' WHEN d.sending>0 THEN 'sending'
                          WHEN d.pending>0 THEN 'pending' WHEN d.sent>0 THEN 'sent'
                          WHEN d.total>0 THEN 'cancelled' WHEN n.uid IS NOT NULL THEN 'skipped'
                          ELSE 'received' END state
                        FROM pending p LEFT JOIN news_plan n ON n.bot=p.bot AND n.uid=p.uid
                        LEFT JOIN (SELECT bot,uid,COUNT(*) total,
                          SUM(state IN ('uncertain','not_submitted','rejected','blocked')) issues,
                          SUM(state='sending') sending,SUM(state='pending') pending,SUM(state='sent') sent,
                          GROUP_CONCAT(DISTINCT contact) targets FROM news_delivery GROUP BY bot,uid) d
                          ON d.bot=p.bot AND d.uid=p.uid'''
                else:
                    selection = "SELECT bot,uid,payload,state ingress_state,error,'' plan_reason,'' targets,state FROM pending"
                result['counts'] = dict(db.execute('SELECT state,COUNT(*) FROM ('+selection+') GROUP BY state'))
                # Filters are applied before pagination, using numeric sender identity or target contact.
                filters, args = [], []
                if scope == 'active':
                    filters.append("state NOT IN ('sent','skipped','cancelled')")
                elif scope == 'issues':
                    filters.append("state IN ('blocked','uncertain','rejected','not_submitted')")
                elif scope == 'history':
                    filters.append("state IN ('sent','skipped','cancelled')")
                if state not in ('all', 'active'):
                    filters.append('state=?'); args.append(state)
                elif state == 'active':
                    filters.append("state NOT IN ('sent','skipped','cancelled')")
                if contact:
                    clause = "('Telegram · ' || json_extract(payload,'$.message.from.id')=?"
                    if news:
                        clause += ' OR EXISTS (SELECT 1 FROM news_delivery x WHERE x.bot=v.bot AND x.uid=v.uid AND x.contact=?)'
                        args.extend([contact, contact])
                    else:
                        args.append(contact)
                    filters.append(clause+')')
                where = ' WHERE '+' AND '.join(filters) if filters else ''
                total = db.execute('SELECT COUNT(*) FROM ('+selection+') v'+where, args).fetchone()[0]
                limit = max(1, min(500, int(limit)))
                offset = min(max(0,int(offset)), ((max(total,1)-1)//limit)*limit)
                direction = 'ASC' if scope in ('active', 'issues') else 'DESC'
                rows = db.execute('SELECT * FROM ('+selection+') v'+where+f' ORDER BY uid {direction},bot {direction} LIMIT ? OFFSET ?',
                                  [*args,limit,offset]).fetchall()
                for row in rows:
                    body = json.loads(row['payload']); msg = body['message']
                    sender = str(msg['from']['id']); text = msg.get('text') or msg.get('caption') or '[媒体消息]'
                    token=cfg.get('token')
                    if isinstance(token,str) and token:text=text.replace(token,'[密钥已隐藏]')
                    tasks = [dict(r) for r in db.execute('''SELECT id,contact,part,state,reason,updated
                        FROM news_delivery WHERE bot=? AND uid=? ORDER BY id LIMIT 200''', (row['bot'],row['uid']))] if news else []
                    for task in tasks:
                        task['updated'] = timestamp(task['updated'])
                    problems = [t for t in tasks if t['state'] in ISSUES]
                    error = '；'.join(dict.fromkeys(t['reason'] for t in problems)) or row['error']
                    reason = row['plan_reason'] or ('Butler 已收件，等待新闻任务生成；检查接收器是否已重启加载新闻转发版本' if row['ingress_state']=='received' else '等待提交 Butler 收件接口')
                    for task in tasks:
                        prior = next((t for t in tasks if t['contact']==task['contact'] and t['part']<task['part'] and t['state']!='sent'),None)
                        if task['state']=='pending' and prior:
                            task['blocker_id'] = prior['id']
                            task['reason'] = f"等待前段任务 {prior['id']}（{prior['state']}）：{prior['reason']}"
                    result['rows'].append(dict(id=f"tg:{row['bot']}:{row['uid']}",bot_id=row['bot'],update_id=row['uid'],
                        contact='Telegram · '+sender,uid=sender,source='telegram',state=row['state'],
                        ingress_state=row['ingress_state'],preview=text[:240],characters=len(text),
                        created_at=timestamp(msg.get('date')),received_at=None,error=error,reason=reason,
                        targets=row['targets'],deliveries=tasks,deliveries_truncated=len(tasks)==200,
                        has_media=any(msg.get(k) for k in ('photo','document','video','audio','voice')),actions=[]))
                result['page'] = dict(total=total,offset=offset,limit=limit,has_more=offset+len(rows)<total)
            # Actual Butler receipts are separate evidence, not inferred from polling state.
            from butler.config import load
            receipt_path = load(self.config_path.parent / cfg.get('butler_config', str(self.butler_path.resolve()))).data_path()/'telegram-bot/inbox.sqlite3'
            if receipt_path.is_file():
                with closing(sqlite3.connect(receipt_path.as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
                    for row in result['rows']:
                        receipt = db.execute('SELECT received_at,id FROM inbox WHERE bot_id=? AND update_id=?',
                                             (row['bot_id'],row['update_id'])).fetchone()
                        if receipt:
                            row['received_at'], row['receipt_id'] = timestamp(receipt[0]), receipt[1]
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
            result.update(status='error',error='Telegram 队列不可读取，请检查配置路径、数据库或文件权限')
        return result

    def workflow(self):
        active, history = self.read(scope='active',limit=500), self.read(scope='history',limit=60)
        messages = []
        for row in active['rows']+history['rows']:
            status = row['state']; tasks = row['deliveries']
            terminal = status in TERMINAL
            stage = 7 if status=='sent' else 9 if tasks else 2 if row['ingress_state']=='received' else 8
            at = row['created_at']; received = row['received_at']
            events = [dict(stage='telegram_received',node=8,status='ok',ts=received or at,time_unknown=not bool(received))]
            if row['ingress_state']=='received':
                events.append(dict(stage='telegram_butler',node=2,status='ok',ts=received or at,time_unknown=not bool(received)))
            for task in tasks:
                events.append(dict(stage='telegram_news',node=7 if task['state']=='sent' else 9,
                                   status=task['state'],ts=task['updated'],detail=task['reason'],contact=task['contact']))
            for event in events:
                event['key'] = hashlib.sha256((row['id']+json.dumps(event,sort_keys=True)).encode()).hexdigest()[:24]
            messages.append(dict(id=row['id'],kind='telegram',source='telegram',request_id='',contact=row['contact'],uid=row['uid'],
                label=row['contact'],group=False,members=[],inbox_ids=[],message_count=1,preview=row['preview'],reply_preview='',
                at=at,updated_at=max([at,*[e['ts'] for e in events]]),order=row['update_id'],terminal=terminal,
                scope='issues' if status in ISSUES else 'complete' if terminal else 'active',stage=stage,status=status,state=status,
                reason={'message':row['error'] or row['reason']},error=row['error'],events=events,attempts=0,
                part_count=len(tasks),sent_parts=sum(t['state']=='sent' for t in tasks),retry_at=None,discard_at=None))
        return dict(messages=messages,counts=active['counts'],source=dict(name='Telegram',status=active['status'],
                    error=active['error'],truncated=active['page']['has_more'] or history['page']['has_more']))
