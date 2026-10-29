"""Dismiss finished workflow records without changing delivery or replay receipts."""
import hashlib
import json
import re
import time


class WorkflowConflict(ValueError):
    pass


def version(kind,item,deliveries):
    payload={'kind':kind,'record':dict(item),'deliveries':[dict(row) for row in deliveries]}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def deletable(kind,item,deliveries):
    return ((kind=='batch' and item['state']=='done') or (kind=='push' and item['state'] in {'sent','skipped'})) and all(
        row['state'] in {'sent','skipped'} for row in deliveries)


def failed(kind,item,deliveries):
    if not deletable(kind,item,deliveries):return False
    return any(row['state']=='skipped' for row in deliveries) or (
        kind=='batch' and not deliveries and not item['reply_complete'] and item['reply_mode'] not in {'none','emoji'})


def has_history(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_dismissed'").fetchone())


def visible_selection(db,selection):
    if not has_history(db):return selection
    return """SELECT * FROM ("""+selection+""") q WHERE terminal=0 OR NOT EXISTS(
        SELECT 1 FROM workflow_dismissed h WHERE h.record_id=CASE q.kind WHEN 'push' THEN 'push:'||q.id ELSE q.id END
        AND h.finished_at=COALESCE(q.at,0))"""


def read_record(db,record_id):
    if record_id.startswith('push:'):
        item=db.execute('SELECT * FROM outbox WHERE id=? AND batch_id IS NULL',(record_id[5:],)).fetchone()
        return 'push',item,[item] if item is not None else []
    item=db.execute('SELECT * FROM batches WHERE id=?',(record_id,)).fetchone()
    children=db.execute('SELECT * FROM outbox WHERE batch_id=? ORDER BY seq',(record_id,)).fetchall() if item is not None else []
    return 'batch',item,children


def validate(payload):
    if not isinstance(payload,dict) or payload.get('acknowledge') is not True:raise ValueError('请确认删除工作流记录')
    action=payload.get('action')
    if action=='failed' and set(payload)=={'action','acknowledge'}:return
    if action!='single' or set(payload)!={'action','id','version','acknowledge'}:raise ValueError('删除请求无效')
    if not isinstance(payload['id'],str) or not re.fullmatch(r'(?:push:)?[A-Za-z0-9_-]{1,128}',payload['id']):raise ValueError('消息标识无效')
    if not isinstance(payload['version'],str) or not re.fullmatch('[0-9a-f]{64}',payload['version']):raise ValueError('缺少消息版本，请刷新后重试')


def delete(store,payload,*,now=None):
    validate(payload)
    now=time.time() if now is None else now
    removed=0
    with store._transaction() as db:
        if payload['action']=='single':candidates=[payload['id']]
        else:
            candidates=[row[0] for row in db.execute("SELECT id FROM batches WHERE state='done' UNION ALL SELECT 'push:'||id FROM outbox WHERE batch_id IS NULL AND state='skipped'")]
        snapshots=[]
        for record_id in candidates:
            kind,item,children=read_record(db,record_id)
            if item is None:
                if payload['action']=='single':raise WorkflowConflict('记录不存在，请刷新列表')
                continue
            if not deletable(kind,item,children):
                if payload['action']=='single':raise WorkflowConflict('消息仍在处理或投递，暂不能删除')
                continue
            current=version(kind,item,children)
            if payload['action']=='single' and current!=payload['version']:raise WorkflowConflict('消息状态已变化，请刷新后重新确认')
            if payload['action']=='failed' and not failed(kind,item,children):continue
            snapshots.append((record_id,kind,item,current))
        db.execute('''CREATE TABLE IF NOT EXISTS workflow_dismissed(record_id TEXT PRIMARY KEY,
            version TEXT NOT NULL,finished_at REAL NOT NULL,deleted_at REAL NOT NULL)''')
        for record_id,kind,item,current in snapshots:
            at=item['finished_at'] if item['finished_at'] is not None else item['created_at']
            old=db.execute('SELECT version,finished_at FROM workflow_dismissed WHERE record_id=?',(record_id,)).fetchone()
            if old and old['version']==current and old['finished_at']==(at or 0):continue
            db.execute('INSERT OR REPLACE INTO workflow_dismissed VALUES(?,?,?,?)',(record_id,current,at or 0,now))
            db.execute('''INSERT INTO delivery_events(record_id,record_kind,contact,action,at,state,reason,details,source)
                VALUES(?,?,?,?,?,?,?,?,?)''',(item['id'],'batches' if kind=='batch' else 'outbox',item['contact'],
                'workflow_delete',now,item['state'],'用户删除已结束工作流展示记录','{}','log'))
            removed+=1
    return {'ok':True,'removed':removed}
