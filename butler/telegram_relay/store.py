"""Durable Desktop observations and per-channel forwarding tasks. No native UI."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid
from datetime import datetime


class RelayStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS channels(key TEXT PRIMARY KEY,baseline TEXT NOT NULL,
                  at REAL NOT NULL,error TEXT NOT NULL DEFAULT '');
              CREATE TABLE IF NOT EXISTS tasks(seq INTEGER PRIMARY KEY,id TEXT UNIQUE,channel TEXT,
                  payload TEXT,state TEXT NOT NULL DEFAULT 'pending',source_id TEXT,submitted INTEGER DEFAULT 0,
                  created REAL,updated REAL,error TEXT NOT NULL DEFAULT '');
              CREATE TABLE IF NOT EXISTS scheduler(key TEXT PRIMARY KEY,value TEXT);''')
            columns={row[1] for row in db.execute('PRAGMA table_info(tasks)')}
            for name,kind in (('submitted_at','REAL'),('source_chat_id','INTEGER'),('source_username',"TEXT NOT NULL DEFAULT ''")):
                if name not in columns:db.execute(f'ALTER TABLE tasks ADD COLUMN {name} {kind}')
            db.execute('DROP INDEX IF EXISTS source_once')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS source_once_v2 ON tasks(channel,source_chat_id,source_username,source_id) WHERE source_id IS NOT NULL')

    def sync_channels(self,channels):
        """Reusing a configuration key for a different source starts a fresh baseline."""
        with self.db() as db:
            for channel in channels:
                key='channel:'+channel.key
                identity=json.dumps([channel.chat_id,channel.username.casefold()])
                previous=db.execute('SELECT value FROM scheduler WHERE key=?',(key,)).fetchone()
                if previous and previous[0]!=identity:
                    db.execute('DELETE FROM channels WHERE key=?',(channel.key,))
                    db.execute("UPDATE tasks SET state='cancelled',error='频道身份已改变',updated=? WHERE channel=? AND state='pending'",(time.time(),channel.key))
                db.execute('INSERT INTO scheduler VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,identity))

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback(); raise
        finally:
            db.close()

    def recover(self):
        with self.db() as db:
            active=db.execute("SELECT id,channel FROM tasks WHERE state='forwarding' ORDER BY seq LIMIT 1").fetchone()
            db.execute("UPDATE tasks SET state=CASE WHEN submitted=1 THEN 'uncertain' ELSE 'blocked' END,"
                       "error='桌面操作中断，需核对后继续',updated=? WHERE state='forwarding'",(time.time(),))
            if active:
                self._hold(db,active['id'],active['channel'],'桌面操作中断，需先核对Telegram界面')
            else:
                owned=db.execute("SELECT value FROM scheduler WHERE key='ui_active'").fetchone()
                if owned:
                    owner=json.loads(owned[0])
                    task=db.execute('SELECT state FROM tasks WHERE id=?',(owner['id'],)).fetchone()
                    hold_id=owner['id'] if task and task['state'] in {'blocked','uncertain'} else 'desktop'
                    self._hold(db,hold_id,owner['channel'],'桌面事务中断，需先核对Telegram残留界面')
            db.execute("DELETE FROM scheduler WHERE key='ui_active'")

    def begin_ui(self,task_id,channel):
        with self.db() as db:
            db.execute("INSERT INTO scheduler VALUES('ui_active',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (json.dumps({'id':task_id,'channel':channel}),))

    def end_ui(self):
        with self.db() as db:db.execute("DELETE FROM scheduler WHERE key='ui_active'")

    @staticmethod
    def _hold(db,task_id,channel,error):
        db.execute("INSERT INTO scheduler VALUES('hold',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (json.dumps({'id':task_id,'channel':channel,'error':str(error)[:300],'updated':time.time()}),))

    def hold(self,task_id,channel,error):
        with self.db() as db:self._hold(db,task_id,channel,error)

    def has_hold(self):
        with self.db() as db:return db.execute("SELECT 1 FROM scheduler WHERE key='hold'").fetchone() is not None

    def resolve(self,task_id,action):
        if action not in {'forwarded','cancelled','retry'}:raise ValueError('无效核对动作')
        with self.db() as db:
            held=db.execute("SELECT value FROM scheduler WHERE key='hold'").fetchone()
            hold=json.loads(held[0]) if held else None
            if task_id=='desktop':
                if action=='forwarded' or not hold or hold['id']!='desktop':raise ValueError('该界面核对记录已变化')
            else:
                row=db.execute('SELECT state FROM tasks WHERE id=?',(task_id,)).fetchone()
                if not row or row['state'] not in {'blocked','uncertain'}:raise ValueError('该任务当前不能人工核对')
                state='pending' if action=='retry' else action
                db.execute('UPDATE tasks SET state=?,submitted=0,submitted_at=NULL,error=?,updated=? WHERE id=?',
                           (state,'管理员已核对：'+action,time.time(),task_id))
            if hold and hold['id']==task_id:db.execute("DELETE FROM scheduler WHERE key='hold'")
        return {'ok':True,'id':task_id,'action':action}

    def capture(self,channel,observations,*,now=None):
        now=time.time() if now is None else now
        if not isinstance(observations,list) or len(observations)>500:
            raise ValueError('无效桌面消息快照')
        keys=[str(item['key']) for item in observations]
        runtime_ids=[item.get('runtime_id') for item in observations]
        snapshot=json.dumps({'keys':keys,'runtime_ids':runtime_ids})
        with self.db() as db:
            row=db.execute('SELECT baseline FROM channels WHERE key=?',(channel,)).fetchone()
            if row is None:
                db.execute('INSERT INTO channels VALUES(?,?,?,?)',(channel,snapshot,now,''))
                return 0
            previous=json.loads(row[0])
            previous_ids=previous.get('runtime_ids') if isinstance(previous,dict) else None
            previous=previous['keys'] if isinstance(previous,dict) else previous
            if keys==previous:
                error='snapshot_ambiguous：同文行身份已变化，不能认定为旧消息，待核对' if previous_ids is not None and previous_ids!=runtime_ids else ''
                db.execute('UPDATE channels SET at=?,error=?,baseline=? WHERE key=?',
                           (now,error,row[0] if error else snapshot,channel)); return 0
            end=0 if not previous else None
            for size in range(min(len(previous),len(keys)),0,-1):
                for index in range(size,len(keys)+1):
                    if previous[-size:]==keys[index-size:index]:
                        if previous_ids is not None and previous_ids[-size:]!=runtime_ids[index-size:index]:
                            db.execute("UPDATE channels SET at=?,error='snapshot_ambiguous：历史锚点行身份已变化，待核对' WHERE key=?",(now,channel))
                            return 0
                        end=index; break
                if end is not None:break
            if end is None:
                db.execute("UPDATE channels SET at=?,error='snapshot_gap：历史锚点不在加载区，待核对' WHERE key=?",(now,channel))
                return 0
            for item in observations[end:]:
                if len(json.dumps(item,ensure_ascii=False))>100000:
                    raise ValueError('桌面消息描述过大')
                db.execute('INSERT INTO tasks(id,channel,payload,created,updated)VALUES(?,?,?,?,?)',
                           (uuid.uuid4().hex,channel,json.dumps(item,ensure_ascii=False),now,now))
            db.execute('UPDATE channels SET baseline=?,at=?,error=? WHERE key=?',(snapshot,now,'',channel))
            return len(observations)-end

    def claim(self,channels):
        if not channels:return None
        with self.db() as db:
            row=db.execute("SELECT value FROM scheduler WHERE key='last'").fetchone()
            previous=row[0] if row else None
            order=list(channels)
            if previous in order:
                split=order.index(previous)+1; order=order[split:]+order[:split]
            for channel in order:
                row=db.execute("SELECT * FROM tasks WHERE channel=? AND state IN ('pending','forwarding','awaiting_bot','blocked','uncertain') ORDER BY seq LIMIT 1",(channel,)).fetchone()
                if row is None or row['state']!='pending':continue
                db.execute("UPDATE tasks SET state='forwarding',updated=? WHERE id=?",(time.time(),row['id']))
                db.execute("INSERT INTO scheduler VALUES('last',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(channel,))
                result=dict(row);result['payload']=json.loads(result['payload']);return result
        return None

    def mark_submitted(self,task_id):
        with self.db() as db:
            now=time.time()
            db.execute('UPDATE tasks SET submitted=1,submitted_at=COALESCE(submitted_at,?),updated=? WHERE id=?',(now,now,task_id))

    def bind_source(self,task_id,source_id,*,source_chat_id=0,source_username=''):
        if not isinstance(source_id,str) or not source_id.isdigit() or int(source_id)<1:
            raise ValueError('来源消息标识无效')
        with self.db() as db:
            task=db.execute('SELECT channel FROM tasks WHERE id=?',(task_id,)).fetchone()
            if task is None:raise ValueError('转发任务不存在')
            existing=db.execute('SELECT id FROM tasks WHERE channel=? AND source_id=? AND source_chat_id=? AND source_username=?',
                                (task[0],source_id,source_chat_id,source_username.casefold())).fetchone()
            if existing and existing[0]!=task_id:
                db.execute("UPDATE tasks SET state='duplicate',error='来源消息已建任务',updated=? WHERE id=?",(time.time(),task_id));return False
            db.execute('UPDATE tasks SET source_id=?,source_chat_id=?,source_username=? WHERE id=?',
                       (source_id,source_chat_id,source_username.casefold(),task_id));return True

    def reconcile_receipts(self,receipts,*,now=None):
        """Positive Bot ingress evidence confirms submission; timeouts never replay it."""
        now=time.time() if now is None else now
        with self.db() as db:
            for task in db.execute("SELECT * FROM tasks WHERE state IN ('awaiting_bot','uncertain') AND submitted=1").fetchall():
                matched=False
                for receipt in receipts:
                    try:
                        at=datetime.fromisoformat(receipt['received_at']).timestamp()
                        same_source=(receipt.get('source_chat_id')==task['source_chat_id'] if task['source_chat_id']
                                     else bool(task['source_username']) and str(receipt.get('source_username','')).casefold()==task['source_username'])
                        if same_source and str(receipt['source_message_id'])==task['source_id'] and at>=task['submitted_at']:
                            matched=True;break
                    except (KeyError,ValueError,TypeError):continue
                if matched:
                    held=db.execute("SELECT value FROM scheduler WHERE key='hold'").fetchone()
                    requires_review=bool(held and json.loads(held[0]).get('id')==task['id'])
                    if requires_review:
                        db.execute("UPDATE tasks SET error='机器人已收件，仍需清理残留界面并人工核对' WHERE id=?",(task['id'],))
                    else:db.execute("UPDATE tasks SET state='forwarded',error='',updated=? WHERE id=?",(now,task['id']))
                elif task['state']=='awaiting_bot' and now-task['updated']>60:
                    db.execute("UPDATE tasks SET state='uncertain',error='机器人收件尚未确认，需人工核对，不自动重发',updated=? WHERE id=?",(now,task['id']))

    def finish(self,task_id,state,error=''):
        if state not in {'awaiting_bot','forwarded','blocked','uncertain','duplicate','cancelled'}:raise ValueError('无效转发状态')
        with self.db() as db:
            db.execute('UPDATE tasks SET state=?,error=?,updated=? WHERE id=?',(state,str(error)[:300],time.time(),task_id))

    def status(self):
        with self.db() as db:
            counts=dict(db.execute('SELECT state,count(*) FROM tasks GROUP BY state'))
            channels=[dict(row) for row in db.execute('SELECT key,at,error FROM channels ORDER BY key')]
            recent=[{k:row[k] for k in ('id','channel','state','source_id','submitted','updated','error')}
                    for row in db.execute('SELECT * FROM tasks ORDER BY seq DESC LIMIT 50')]
            row=db.execute("SELECT value FROM scheduler WHERE key='hold'").fetchone()
            hold=json.loads(row[0]) if row else None
            if hold and hold['id']=='desktop':recent.insert(0,{**hold,'state':'blocked','source_id':None,'submitted':False})
        return {'counts':counts,'channels':channels,'tasks':recent,'ui_hold':bool(hold)}


def read_status(path):
    try:
        path=Path(path)
        if path.stat().st_size>262144:raise ValueError('status too large')
        data=json.loads(path.read_text(encoding='utf-8'))
        return {key:data[key] for key in ('enabled','at','current','phase','error','counts','channels','tasks','ui_hold') if key in data}
    except (OSError,ValueError,TypeError):return {'state':'unavailable'}
