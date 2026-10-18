import pytest

from wxbot.queue_store import QueueStore


def failed(store, state='blocked', at=10):
    task=store.enqueue_delivery('A','original reply',now=0)
    store.claim_delivery(now=0)
    store.finish_delivery(task,state,now=at,error='foreground changed')
    return task


@pytest.mark.parametrize('state',['blocked','uncertain'])
def test_failure_expires_at_180_seconds_and_preserves_history(state):
    store=QueueStore(':memory:')
    task=failed(store,state)
    later=store.enqueue_delivery('A','next reply',now=11)
    assert store.expire_failed_deliveries(now=189.9)==[]
    assert not store.has_ready_delivery(now=189.9)
    expired=store.expire_failed_deliveries(now=190)
    assert [r['id'] for r in expired]==[task]
    row=store.get_delivery(task)
    assert row['state']=='skipped' and row['resolution']=='timeout'
    assert row['text']=='original reply' and 'foreground changed' in row['error']
    assert store.claim_delivery(now=190).id==later
    assert store.expire_failed_deliveries(now=500)==[]
    events=store.delivery_events()
    assert [e['action'] for e in events]==['failed','timeout_discard']


def test_first_failure_deadline_survives_retry_and_restart(tmp_path):
    path=tmp_path/'q.db'
    store=QueueStore(path)
    task=failed(store,at=10)
    store.retry(task,delivery=True)
    store.claim_delivery(now=20)
    store.finish_delivery(task,'blocked',now=20,error='focus changed')
    store.close()
    store=QueueStore(path)
    assert store.get_delivery(task)['failed_at']==10
    assert [r['id'] for r in store.expire_failed_deliveries(now=190)]==[task]


def test_pending_and_active_tasks_are_not_discarded_by_an_old_failure_deadline():
    store=QueueStore(':memory:')
    task=failed(store)
    store.retry(task,delivery=True)
    assert store.expire_failed_deliveries(now=1000)==[]
    store.claim_delivery(now=1000)
    assert store.expire_failed_deliveries(now=1000)==[]
    store.confirming(task,now=1000)
    assert store.expire_failed_deliveries(now=2000)==[]


def test_manual_actions_reject_stale_page_and_wrong_contact():
    store=QueueStore(':memory:')
    task=failed(store)
    for options in ({'contact':'other'},{'expected_state':'uncertain'},
                    {'expected_finished_at':9}):
        with pytest.raises(ValueError): store.retry(task,delivery=True,**options)
    assert store.get_delivery(task)['state']=='blocked'
    store.resolve(task,delivery=True,sent=True,now=20,contact='A',
                  expected_state='blocked',expected_finished_at=10,source='log')
    assert store.get_delivery(task)['resolution']=='manual_sent'
    assert store.delivery_events()[-1]['source']=='log'


def test_expiring_one_part_does_not_drop_the_rest_of_the_turn():
    from test_queue_migration import batch
    store=QueueStore(':memory:')
    turn=batch(store,'A',['first','second'])
    first=store.claim_delivery(now=0)
    store.finish_delivery(first.id,'blocked',now=0,error='unavailable')
    store.expire_failed_deliveries(now=180)
    assert store.get_batch(turn.id)['state']=='waiting_delivery'
    assert store.claim_delivery(now=180).part_seq==2


def test_failure_details_persist_only_supported_metadata():
    store=QueueStore(':memory:')
    task=store.enqueue_delivery('A','reply',now=0)
    store.claim_delivery(now=0)
    store.finish_delivery(task,'blocked',now=1,error='window changed',details={
        'expected_contact':'A','actual_contact':'B','foreground_hwnd':123,'phase':'input_guard',
        'draft':'private','headers':{'Authorization':'secret'},'token':'secret'})
    details=store.delivery_events()[0]['details']
    assert details=={'expected_contact':'A','actual_contact':'B','foreground_hwnd':123,'phase':'input_guard'}


def test_delivery_pump_expires_failure_and_logs_the_release(caplog):
    import logging
    from test_delivery_queue import Chat,pump
    store=QueueStore(':memory:');clock=[0]
    task=failed(store,at=0)
    later=store.enqueue_delivery('A','next',now=0)
    sender=pump(store,Chat(),clock)
    clock[0]=180
    with caplog.at_level(logging.WARNING):sender.tick(allow_start=False)
    assert store.get_delivery(task)['resolution']=='timeout'
    assert store.get_delivery(later)['state']=='pending'
    assert task in caplog.text and '自动丢弃' in caplog.text


@pytest.mark.parametrize('action',['retry','sent','skip'])
def test_expiry_and_manual_action_serialize_without_double_ending(tmp_path,action):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    store=QueueStore(tmp_path/'race.db')
    task=failed(store,at=0)
    later=store.enqueue_delivery('A','next',now=1)
    admin=QueueStore(tmp_path/'race.db',access='admin')
    barrier=Barrier(2)
    def expire():
        barrier.wait()
        return store.expire_failed_deliveries(now=180)
    def manual():
        barrier.wait()
        opts=dict(delivery=True,contact='A',expected_state='blocked',expected_finished_at=0,now=180)
        try:
            if action=='retry':admin.retry(task,**opts)
            else:admin.resolve(task,sent=action=='sent',**opts)
        except ValueError:return 'stale'
        return 'applied'
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            expiry=pool.submit(expire);human=pool.submit(manual)
            expired,outcome=expiry.result(),human.result()
        assert bool(expired)==(outcome=='stale')
        events=[e['action'] for e in store.delivery_events()]
        assert len(events)==2 and events[0]=='failed'
        row=store.get_delivery(task)
        assert row['state'] in {'sent','skipped','pending'}
        assert store.get_delivery(later)['state']=='pending'
        assert store.claim_delivery(now=180).id==(task if row['state']=='pending' else later)
        assert len(list(store._db.execute('SELECT * FROM delivery_turns'))) == (0 if row['state']=='pending' else 1)
    finally:
        admin.close();store.close()


def test_send_failure_log_contains_safe_diagnostic_metadata(caplog):
    import logging
    from test_delivery_queue import Chat,pump
    store=QueueStore(':memory:');chat=Chat();clock=[0]
    task=store.enqueue_delivery('A','private reply body',now=0)
    sender=pump(store,chat,clock)
    sender.capture_target=lambda contact:False
    chat.send_diagnostics=lambda:{'expected_contact':'A','actual_contact':'B',
        'expected_hwnd':123,'foreground_hwnd':456,'input_focused':False}
    with caplog.at_level(logging.ERROR):sender.start_next()
    assert task in caplog.text and '发送失败' in caplog.text and 'foreground_hwnd' in caplog.text
    assert 'private reply body' not in caplog.text
    assert store.delivery_events()[-1]['details']['phase']=='prepare_target'
