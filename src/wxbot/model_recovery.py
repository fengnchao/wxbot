"""Read-only model failure policy shared by runtime and dashboard projections."""
MODEL_MAX_ATTEMPTS=3
MODEL_RETRY_DELAYS=(5,15)
MODEL_FAILURE_ACTIONS=('model_retryable','model_uncertain')


def model_failure_info(db,row,now,timeout):
    events=[]
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='delivery_events'").fetchone():
        events=db.execute("SELECT action,at FROM delivery_events WHERE record_id=? AND record_kind='batches' "
                          "AND action IN (?,?) ORDER BY seq",(row['id'],*MODEL_FAILURE_ACTIONS)).fetchall()
    first=events[0]['at'] if events else next((row[k] for k in ('finished_at','started_at','created_at') if row[k] is not None),now)
    latest=events[-1]['at'] if events else first
    safe=bool(events and events[-1]['action']=='model_retryable')
    attempts=row['attempts'] or 0
    retry_at=latest+MODEL_RETRY_DELAYS[min(max(attempts-1,0),len(MODEL_RETRY_DELAYS)-1)] if safe and attempts<MODEL_MAX_ATTEMPTS else None
    deadline=first+timeout
    action=('abandon' if now>=deadline or (safe and attempts>=MODEL_MAX_ATTEMPTS) else
            'retry' if retry_at is not None and now>=retry_at else '')
    return {'retry_safe':safe,'retry_at':retry_at,'failed_at':first,'discard_at':deadline,
            'remaining_seconds':max(0,deadline-now),'max_attempts':MODEL_MAX_ATTEMPTS,'auto_action':action}
