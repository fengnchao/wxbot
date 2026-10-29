"""Administrative reminder deletion; called only after service-token validation."""
import hashlib
import json
import re
import time


class JobConflict(ValueError):
    pass


class JobMissing(LookupError):
    pass


def job_version(row):
    return hashlib.sha256(json.dumps(dict(row),sort_keys=True,ensure_ascii=False,
                                     separators=(',',':')).encode('utf-8')).hexdigest()


def validate_delete_payload(payload):
    if (not isinstance(payload,dict) or set(payload)!={'job_id','version','acknowledge'}
            or payload.get('acknowledge') is not True
            or not isinstance(payload.get('job_id'),str)
            or not re.fullmatch('[0-9a-f]{32}',payload['job_id'])
            or not isinstance(payload.get('version'),str)
            or not re.fullmatch('[0-9a-f]{64}',payload['version'])):
        raise ValueError('请确认要删除的任务，刷新列表后重试')


def delete_job(store,payload):
    validate_delete_payload(payload)
    with store.transaction() as db:
        row=db.execute('SELECT * FROM reminders WHERE id=?',(payload['job_id'],)).fetchone()
        if row is None:raise JobMissing('任务已删除或不存在，请刷新列表')
        if row['status']=='delivering':raise JobConflict('任务正在投递，暂不能删除；请等待发送结果')
        if job_version(row)!=payload['version']:raise JobConflict('任务状态已变化，请刷新后重新确认')
        if row['status'] not in {'scheduled','failed','cancelled','sent'}:
            raise JobConflict('当前任务状态不支持删除，请刷新后核对')
        db.execute('DELETE FROM reminders WHERE id=?',(row['id'],))
        db.execute('INSERT INTO events(at,contact,stage,status,details)VALUES(?,?,?,?,?)',
                   (time.time(),row['contact'],'job_deleted','ok',
                    json.dumps({'job_id':row['id'],'previous_status':row['status']})))
    return {'ok':True,'job_id':payload['job_id']}
