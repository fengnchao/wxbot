import pytest
from wxbot.queue_store import Incoming, QueueStore
from wxbot.queue_worker import ModelWorker
from wxbot.reply import Reply


def batch(store):
    store.capture('A', [], [Incoming('question')], now=0)
    store.prepare(quiet=0, max_wait=10, prefix='/', now=1)
    return store.claim_batch(now=1).id


def test_sentence_parser_preserves_closers_code_urls_and_decimal():
    from wxbot.streaming import SentenceBuffer
    parser = SentenceBuffer()
    assert parser.feed('价格3.14，`x!?` https://x.test/a! 好。') == []
    assert parser.feed('”下一句！') == ['价格3.14，`x!?` https://x.test/a! 好。”']
    assert parser.finish() == ['下一句！']


def test_stream_durable_unsealed_then_sealed_and_cancel():
    store = QueueStore(':memory:')
    ident = batch(store)
    store.begin_stream(ident, 'streaming', now=1)
    store.append_stream(ident, '你好。', now=2)
    first = store.claim_delivery(now=2)
    assert first.text == '你好。'
    assert not store.stream_part(first.id)['sealed']
    store.append_stream(ident, '再见', now=3)
    assert store.stream_part(first.id)['sealed']
    store.cancel_stream(ident, now=4)
    assert store.stream_snapshot(ident)['status'] == 'cancelled'
    assert all(r['state'] == 'skipped' for r in store.records('outbox'))


def test_worker_persists_events_in_all_modes_and_full_is_one_part():
    class Router:
        def handle_reply(self, *args, on_event=None, **kwargs):
            on_event({'type': 'summary_delta', 'text': 'public progress'})
            return Reply.from_text('一。二。')
    store = QueueStore(':memory:')
    store.capture('A', [], [Incoming('q')], now=0)
    ModelWorker(store, Router(), quiet=0, clock=lambda: 1, typing_mode='full').process_once()
    rows = store.records('outbox')
    assert [r['text'] for r in rows] == ['一。二。']
    assert store.model_events(rows[0]['batch_id'])[0]['type'] == 'summary_delta'


def test_live_typing_appends_partial_chunk_without_enter_until_sealed(monkeypatch):
    from test_typing import make_chat
    chat, sent = make_chat(monkeypatch)
    clock = [0]
    task = chat.start_send('abc', clock=lambda: clock[0])
    task.update_stream('abc', sealed=False)
    task.step()
    clock[0] = 1
    task.step()
    assert '{Enter}' not in sent
    task.update_stream('abcdef。', sealed=False)
    task.step()
    clock[0] = 2
    task.step()
    task.update_stream('abcdef。', sealed=True)
    assert task.step() == 'submitted'
    assert task.edit.pasted == ['abc', 'def。']


def test_stream_final_mismatch_cancels_without_replay():
    class Router:
        def handle_reply(self, *args, on_event=None, **kwargs):
            on_event({'type':'answer_delta','text':'wrong。','sendable':True})
            return Reply.from_text('different')
    store = QueueStore(':memory:')
    store.capture('A', [], [Incoming('q')], now=0)
    worker = ModelWorker(store, Router(), quiet=0, clock=lambda:1, typing_mode='streaming')
    worker.process_once()
    assert all(r['state']=='skipped' for r in store.records('outbox'))
    assert not worker.process_once()


def test_cancel_and_enter_gate_serialize_and_restart_never_resumes(tmp_path):
    path=tmp_path/'queue.sqlite3'
    store=QueueStore(path,restart_chat_policy='resume')
    ident=batch(store)
    store.begin_stream(ident,'streaming',now=1)
    store.append_stream(ident,'first。second',now=2)
    first=store.claim_delivery(now=2)
    part=store.stream_part(first.id)
    with store.stream_enter_gate(first.id,part['text'],part['version']) as allowed:
        assert allowed
    store.cancel_stream(ident,now=3)
    assert store.get_delivery(first.id)['state']=='uncertain'
    assert store.get_delivery(first.id)['manual_required']==1
    assert store.records('outbox')[1]['state']=='skipped'
    store.close()
    store=QueueStore(path,restart_chat_policy='resume')
    store.recover(now=4)
    assert store.claim_delivery(now=5) is None
    store.close()


def test_cancel_before_enter_gate_and_stale_version_are_denied():
    store=QueueStore(':memory:')
    ident=batch(store)
    store.begin_stream(ident,'streaming',now=1)
    store.append_stream(ident,'hello。next',now=2)
    first=store.claim_delivery(now=2)
    part=store.stream_part(first.id)
    with store.stream_enter_gate(first.id,part['text'],part['version']-1) as allowed:
        assert not allowed
    store.cancel_stream(ident,now=3)
    with store.stream_enter_gate(first.id,part['text'],part['version']) as allowed:
        assert not allowed


def test_sent_sentence_retained_when_generation_fails():
    store=QueueStore(':memory:')
    ident=batch(store)
    store.begin_stream(ident,'streaming',now=1)
    store.append_stream(ident,'sent。draft',now=2)
    first=store.claim_delivery(now=2)
    store.finish_delivery(first.id,'sent',now=3)
    store.cancel_stream(ident,now=4)
    assert [row['state'] for row in store.records('outbox')]==['sent','skipped']


def test_model_event_retention_is_bounded_and_readonly_legacy_tolerates_missing(tmp_path):
    import sqlite3
    store=QueueStore(':memory:')
    for n in range(520):
        store.record_model_event('id',{'type':'tool','tool':str(n),'arguments':'secret'},now=n)
    events=store.model_events('id')
    assert len(events)==512 and events[0]['tool']=='8'
    assert all('arguments' not in event for event in events)
    path=tmp_path/'legacy.sqlite3'
    sqlite3.connect(path).close()
    legacy=QueueStore(path,access='readonly')
    assert legacy.model_events('id')==[]
    assert legacy.stream_snapshot('id') is None
    legacy.close()


def test_delivery_pump_reads_live_draft_and_submits_latest_sealed_text(monkeypatch):
    from test_typing import make_chat
    from wxbot.delivery import DeliveryPump
    from wxbot.wechat.chat_window import Message
    from wxbot.wechat import typing as typing_module
    chat,sent=make_chat(monkeypatch)
    messages=[]
    chat.read_messages=lambda **kwargs:list(messages)
    chat.read_from_window=lambda *args,**kwargs:list(messages)
    native=typing_module.auto.SendKeys
    def send(keys,**kwargs):
        if keys=='{Enter}':
            messages.append(Message('self',sender.active.typing.text))
        native(keys,**kwargs)
    monkeypatch.setattr(typing_module.auto,'SendKeys',send)
    clock=[2]
    store=QueueStore(':memory:')
    ident=batch(store)
    store.begin_stream(ident,'streaming',now=1)
    store.append_stream(ident,'abc',now=2)
    sender=DeliveryPump(store,lambda _:chat,lambda _:True,lambda:None,
        clock=lambda:clock[0],monotonic=lambda:clock[0])
    sender.tick();sender.tick()
    clock[0]+=1
    sender.tick()
    assert sender.active.typing.edit.value=='abc' and '{Enter}' not in sent
    store.append_stream(ident,'def。',now=3)
    sender.tick()
    clock[0]+=1
    sender.tick()
    assert sender.active.typing.edit.value=='abcdef。' and '{Enter}' not in sent
    store.append_stream(ident,'next',now=4)
    sender.tick()
    assert store.records('outbox')[0]['state']=='sent'
    assert sent.count('{Enter}')==1
    assert chat._input_text(sender.get_chat('A')._find(None))==''


def test_full_paste_is_single_clipboard_operation(monkeypatch):
    from test_typing import make_chat
    chat,sent=make_chat(monkeypatch)
    clock=[0]
    task=chat.start_send('1234567890。',clock=lambda:clock[0])
    task.full_paste()
    task.step()
    clock[0]=1
    task.step()
    assert task.edit.pasted==['1234567890。']
    assert sent.count('{Enter}')==1


def test_unsubmitted_retry_can_reuse_batch_without_replaying_answer():
    store=QueueStore(':memory:')
    ident=batch(store)
    store.begin_stream(ident,'chunked',now=1)
    store.begin_stream(ident,'full',now=2)
    assert store.stream_snapshot(ident)['mode']=='full'
    store.append_stream(ident,'answer',now=3)
    with pytest.raises(ValueError):
        store.begin_stream(ident,'streaming',now=4)


def test_direct_typing_respects_configured_full_mode(monkeypatch):
    from test_typing import make_chat
    chat,_=make_chat(monkeypatch)
    chat.wcfg['typing']={'mode':'full'}
    task=chat.start_send('1234567890')
    task.step()
    assert task.edit.pasted==['1234567890']


def test_legacy_admin_recovery_without_auxiliary_tables(tmp_path):
    path=tmp_path/'legacy.sqlite3'
    store=QueueStore(path)
    for table in ('model_stream_events','model_stream_parts','model_stream_batches'):
        store._db.execute('DROP TABLE '+table)
    store.close()
    admin=QueueStore(path,access='admin')
    assert admin.recover(now=1)=={'models_uncertain':0,'deliveries_uncertain':0}
    admin.close()


def test_worker_stop_cancels_live_draft_immediately_without_replay():
    import threading
    entered,release=threading.Event(),threading.Event()
    store=QueueStore(':memory:')
    store.capture('A',[],[Incoming('q')],now=0)
    class Router:
        def handle_reply(self,*args,on_event=None,**kwargs):
            on_event({'type':'answer_delta','text':'draft','sendable':True})
            entered.set()
            assert release.wait(2)
            return Reply.from_text('draft')
    worker=ModelWorker(store,Router(),quiet=0,clock=lambda:1,typing_mode='streaming')
    worker.start()
    try:
        assert entered.wait(2)
        assert worker.stop(timeout=.01) is False
        assert store.records('outbox')[0]['state']=='skipped'
    finally:
        release.set()
        assert worker.stop(timeout=2)
    assert store.records('outbox')[0]['state']=='skipped'


def test_legacy_window_buffers_until_complete_instead_of_dropping_reply():
    from test_delivery_queue import Chat,pump
    store=QueueStore(':memory:')
    ident=batch(store)
    store.begin_stream(ident,'streaming',now=1)
    store.append_stream(ident,'abc',now=2)
    chat,clock=Chat(),[2]
    sender=pump(store,chat,clock)
    sender.tick()
    assert not sender.active
    assert store.records('outbox')[0]['state']=='pending'
    store.append_stream(ident,'def',now=3,final=True)
    clock[0]=3
    sender.tick();sender.tick();sender.tick()
    assert store.records('outbox')[0]['state']=='sent'
    assert chat.remembered==['abcdef']


@pytest.mark.parametrize('mode',['bad',None,True,[],{}])
def test_typing_mode_validation_rejects_invalid(mode):
    from wxbot.config import validate_typing_config
    with pytest.raises(ValueError):
        validate_typing_config({'typing':{'mode':mode}})


def test_enter_gate_blocks_independent_sqlite_cancel_until_native_submit_returns(tmp_path):
    import threading
    path=tmp_path/'q.sqlite3'
    store=QueueStore(path)
    ident=batch(store)
    store.begin_stream(ident,'streaming',now=1)
    store.append_stream(ident,'first。next',now=2)
    delivery=store.claim_delivery(now=2)
    part=store.stream_part(delivery.id)
    admin=QueueStore(path,access='admin')
    started,finished=threading.Event(),threading.Event()
    errors=[]
    def cancel():
        started.set()
        try: admin.cancel_stream(ident,now=3)
        except Exception as exc: errors.append(exc)
        finally: finished.set()
    with store.stream_enter_gate(delivery.id,part['text'],part['version']) as allowed:
        assert allowed
        thread=threading.Thread(target=cancel)
        thread.start()
        assert started.wait(1)
        assert not finished.wait(.05)
    assert finished.wait(2)
    thread.join()
    assert errors==[]
    assert store.get_delivery(delivery.id)['state']=='uncertain'
    admin.close();store.close()


def test_legacy_router_kwargs_wrapper_does_not_imply_base_callback_support():
    calls=[]
    class Base:
        def handle_reply(self,contact,text,*,context='',request_id=None,member_key='',member_name=''):
            calls.append(text)
            return Reply.from_text('ok')
    class Wrapped(Base):
        def handle_reply(self,*args,**kwargs):
            return super().handle_reply(*args,**kwargs)
    store=QueueStore(':memory:')
    store.capture('A',[],[Incoming('q')],now=0)
    ModelWorker(store,Wrapped(),quiet=0,clock=lambda:1).process_once()
    assert calls==['q']
    assert store.records('outbox')[0]['text']=='ok'


@pytest.mark.parametrize('value',['bad',None,True,[]])
def test_typing_mode_requires_wechat_table(value):
    from wxbot.config import validate_typing_mode
    with pytest.raises(ValueError):
        validate_typing_mode(value)


def test_cancelled_stream_delivery_retry_is_explicitly_rejected():
    store=QueueStore(':memory:')
    ident=batch(store)
    store.begin_stream(ident,'streaming',now=1)
    store.append_stream(ident,'draft',now=2)
    delivery=store.claim_delivery(now=2)
    store.save_draft(delivery.id,'draft')
    store.cancel_stream(ident,now=3)
    with pytest.raises(ValueError,match='流式本轮已结束'):
        store.retry(delivery.id,delivery=True,now=4)
    assert store.get_delivery(delivery.id)['state']=='skipped'
