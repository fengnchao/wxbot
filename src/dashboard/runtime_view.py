"""Backend-neutral dashboard projections; no model credentials reach the browser."""
from datetime import datetime,timezone


def reminder_jobs(runtime):
    from butler.job_admin import job_version
    users={}
    stats={'active':0,'paused':0,'error':0,'done':0}
    for row in sorted(runtime.get('reminders',[]),key=lambda r:(r['due'],r['id'])):
        state={'scheduled':'active','delivering':'active','failed':'error','cancelled':'done','sent':'done'}.get(row['status'],'error')
        stats[state]+=1
        contact=row['contact']
        job={'job_id':row['id'],'name':row['text'],'profile':'Butler','uid':contact,'uid_key':contact.lower(),
             'ui_state':state,'schedule':row['schedule'],'deliver':contact,'uid_source':'profile','no_agent':True,
             'next_run_at':datetime.fromtimestamp(row['due'],timezone.utc).isoformat() if state=='active' else '',
             'last_status':row['status'],'last_error':row['detail'],'scope':'user',
             'can_delete':row['status'] in {'scheduled','failed','cancelled','sent'},
             'delete_version':job_version(row),
             'delete_reason':'任务正在投递，暂不能删除' if row['status']=='delivering' else ''}
        users.setdefault(contact,[]).append(job)
    out=[{'uid':name.lower(),'uid_display':name,'name':name,'count':len(jobs),
           **{k:sum(j['ui_state']==k for j in jobs) for k in stats},'jobs':jobs} for name,jobs in users.items()]
    return {'backend':runtime.get('backend'),'count':sum(stats.values()),**stats,'users':out}
