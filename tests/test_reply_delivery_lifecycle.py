from butler.agent.reply import split_reply
from wxbot.queue_store import Incoming, QueueStore


def turn(store, contact='A', parts=('第一句。', '第二句。', '第三句。'), now=0):
    store.capture(contact, [], [Incoming('你好')], now=now)
    store.prepare(quiet=0, max_wait=1, prefix='/', now=now)
    batch = store.claim_batch(now=now)
    store.finish_batch_parts(batch.id, parts, now=now)
    return batch.id


def test_short_reply_is_one_bubble():
    assert split_reply('你好。最近怎样？\n还在呢！') == ['你好。最近怎样？\n还在呢！']


def test_long_reply_preserves_text_and_protected_tokens():
    text = '你好。' * 190 + '\nhttps://example.com/' + 'x' * 520 + '\n```\n' + 'z' * 600 + '\n```'
    parts = split_reply(text)
    assert ''.join(parts) == text
    assert len(parts) > 1
    assert any('https://example.com/' + 'x' * 520 in p for p in parts)
    assert any('```\n' + 'z' * 600 + '\n```' in p for p in parts)


def test_whole_turn_deadline_survives_retry_and_discards_remaining():
    with_store = QueueStore(':memory:', failure_timeout_seconds=180)
    bid = turn(with_store)
    item = with_store.claim_delivery(now=0)
    with_store.finish_delivery(item.id, 'blocked', now=10, error='window')
    with_store.retry(item.id, delivery=True, now=20)
    item = with_store.claim_delivery(now=20)
    with_store.finish_delivery(item.id, 'sent', now=21)
    second = with_store.claim_delivery(now=22)
    with_store.finish_delivery(second.id, 'blocked', now=30, error='window')
    assert with_store.get_delivery(second.id)['failed_at'] == 10
    with_store.expire_failed_deliveries(now=190)
    assert [r['state'] for r in with_store.records('outbox')] == ['sent', 'skipped', 'skipped']
    assert with_store.get_batch(bid)['state'] == 'done'


def test_uncertain_turn_releases_next_incoming_without_resending():
    store = QueueStore(':memory:')
    bid = turn(store)
    item = store.claim_delivery(now=0)
    store.finish_delivery(item.id, 'uncertain', now=1, error='no bubble')
    assert store.get_delivery(item.id)['state'] == 'uncertain'
    assert store.get_delivery(item.id)['detached'] == 1
    assert store.get_batch(bid)['state'] == 'done'
    store.capture('A', [], [Incoming('新问题')], now=2)
    assert store.prepare(quiet=0, max_wait=1, prefix='/', now=2) == 1
    assert store.claim_delivery(now=300) is None
    store.expire_failed_deliveries(now=300)
    assert store.get_delivery(item.id)['state'] == 'uncertain'


def test_restart_stops_chat_replies_but_keeps_push_and_inbox(tmp_path):
    path = tmp_path / 'queue.db'
    store = QueueStore(path)
    bid = turn(store)
    item = store.claim_delivery(now=0)
    store.confirming(item.id, now=1)
    push = store.enqueue_delivery('B', '新闻', now=1)
    store.capture('C', [], [Incoming('新消息')], now=1)
    store.close()
    store = QueueStore(path)
    store.recover(now=2)
    assert store.get_delivery(item.id)['state'] == 'uncertain'
    assert store.get_delivery(item.id)['detached'] == 1
    assert store.get_batch(bid)['state'] == 'done'
    assert store.claim_delivery(now=2).id == push
    assert store.prepare(quiet=0, max_wait=1, prefix='/', now=2) == 1
    store.close()


def test_contacts_rotate_at_block_boundary():
    store = QueueStore(':memory:')
    turn(store, 'A')
    turn(store, 'B')
    first = store.claim_delivery(now=1)
    store.finish_delivery(first.id, 'sent', now=2)
    assert store.claim_delivery(now=2).contact == 'B'


def test_manual_retry_only_selected_uncertain_block(tmp_path):
    store = QueueStore(tmp_path / 'queue.db')
    turn(store)
    first = store.claim_delivery(now=0)
    store.finish_delivery(first.id, 'sent', now=1)
    second = store.claim_delivery(now=1)
    store.finish_delivery(second.id, 'uncertain', now=2, error='unknown')
    store.retry(second.id, delivery=True, now=500)
    assert store.claim_delivery(now=501).id == second.id
    store.finish_delivery(second.id, 'sent', now=502)
    assert [r['state'] for r in store.records('outbox')] == ['sent','sent','skipped']
    store.close()


def test_uncertain_push_detaches_and_keeps_record():
    store = QueueStore(':memory:')
    first = store.enqueue_delivery('A', 'news', now=0)
    store.claim_delivery(now=0)
    store.finish_delivery(first, 'uncertain', now=1)
    later = store.enqueue_delivery('A', 'reminder', now=2)
    assert store.claim_delivery(now=2).id == later
    store.expire_failed_deliveries(now=1000)
    assert store.get_delivery(first)['state']=='uncertain'


def test_draft_hold_survives_timeout_and_has_manual_release(tmp_path):
    from dashboard.queue_view import QueueView
    store = QueueStore(tmp_path/'q.db')
    turn(store)
    first = store.claim_delivery(now=0)
    store.finish_delivery(first.id,'blocked',now=1,error='foreign draft',details={'manual_required':True})
    assert store.retry_failed_deliveries(now=21)==[]
    store.expire_failed_deliveries(now=181)
    next_id=store.enqueue_delivery('A','next',now=182)
    assert store.claim_delivery(now=182) is None
    view=QueueView(store.path).read(scope='issues',now=182)
    assert view['status']=='ok'
    assert view['contacts'][0]['reason']['actions']==['retry','sent','skip']
    assert view['rounds'][0]['parts'][0]['manual_required']==1
    store.resolve(first.id,delivery=True,sent=False,now=183)
    assert store.claim_delivery(now=183).id==next_id
    store.close()


def test_queue_groups_paginate_whole_round_and_hide_owned_draft(tmp_path):
    from dashboard.queue_view import QueueView
    store=QueueStore(tmp_path/'q.db')
    first=turn(store,'A')
    second=turn(store,'B',parts=('hello',))
    delivery=store.claim_delivery(now=1)
    store.save_draft(delivery.id,'secret prefix')
    view=QueueView(store.path).read(scope='all',limit=1,offsets={'rounds':1},now=2)
    assert view['status']=='ok'
    assert view['pages']['rounds']['total']==2
    assert len(view['rounds'])==1 and view['rounds'][0]['id']=='reply:'+first
    assert len(view['rounds'][0]['parts'])==3
    assert 'secret prefix' not in str(view)
    store.close()


def test_input_default_is_twice_as_fast():
    from wxbot.config import validate_typing_config
    assert validate_typing_config({})==(5,0.25)


def test_chunk_size_validation_and_custom_contract():
    import pytest
    from butler.agent.core import Result
    assert len(Result('a'*240).as_dict(reply_chunk_chars=100)['reply_parts'])==3
    for value in (0,True,99,2001,'500'):
        with pytest.raises(ValueError):split_reply('test',value)
