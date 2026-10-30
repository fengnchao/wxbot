"""Offline public group archive boundaries and local no-model decisions."""
from types import SimpleNamespace

import pytest
import requests

from butler.business import BusinessStore
from wxbot.inbox import MainInbox
from wxbot.processor.butler import ButlerProcessor
from wxbot.processor.router import Router
from wxbot.queue_store import Incoming, QueueStore
from wxbot.queue_worker import ModelWorker
from wxbot.reply import Reply


def context_store(tmp_path):
    from butler.identity.group_context import GroupContext
    return GroupContext(BusinessStore(tmp_path / 'business.sqlite3'))


def message(text, member='a'):
    return {'text': text, 'member_key': member, 'member_name': member}


def test_archive_idempotent_and_group_boundary_excludes_current_request(tmp_path):
    ctx = context_store(tmp_path)
    first = ctx.archive('群', 'one', [message('甲的公开消息')])
    assert first['inserted'] == 1
    assert ctx.archive('群', 'one', [message('甲的公开消息')]) == {'seq': first['seq'], 'inserted': 0}
    ctx.archive('另群', 'two', [message('另群秘密')])
    current = ctx.archive('群', 'three', [message('当前请求', 'b')])
    ctx.archive('群', 'four', [message('生成期间的新消息')])
    result = ctx.snapshot('群', current['seq'])
    assert [r['text'] for r in result['messages']] == ['甲的公开消息']
    assert result['from_seq'] == result['to_seq'] == first['seq']


def test_snapshot_whole_messages_bounded_and_cursor_scoped(tmp_path):
    ctx = context_store(tmp_path)
    saved = ctx.archive('群', 'one', [message('aaaa'), message('bb'), message('cc')])
    result = ctx.snapshot('群', saved['seq'] + 1, limit=2, max_chars=3)
    assert [r['text'] for r in result['messages']] == ['cc']
    assert result['characters'] == 2
    ctx.advance('群', 'thread-a', saved['seq'])
    assert ctx.cursor('群', 'thread-a') == saved['seq']
    assert ctx.cursor('另群', 'thread-a') == ctx.cursor('群', 'thread-b') == 0
    ctx.advance('群', 'thread-a', 0)
    assert ctx.cursor('群', 'thread-a') == saved['seq']


def test_request_snapshot_is_persisted_even_if_later_archive_changes(tmp_path):
    ctx = context_store(tmp_path)
    ctx.archive('群', 'one', [message('first')])
    saved = ctx.snapshot_for_request('群', 'request', 100)
    ctx.archive('群', 'two', [message('later')])
    assert ctx.snapshot_for_request('群', 'request', 100) == saved


@pytest.mark.parametrize('mode', ['none', 'emoji'])
def test_worker_archives_before_finishing_without_model(mode):
    store = QueueStore(':memory:')
    store.capture('群', [], [Incoming('普通群消息', 'member', 'ctx', '甲', mode)], group_mode=True, now=0)
    calls = []
    class Backend:
        def archive_group(self, contact, source_id, text, member_key, member_name, avatar=''):
            calls.append((contact, source_id, text, member_key, member_name))
            return 7
        def handle_reply(self, *args, **kwargs):
            pytest.fail('Silent and emoji batches must never invoke a model')
    ModelWorker(store, Backend(), quiet=0, clock=lambda: 0).process_once()
    batch = store.records('batches')[0]
    assert batch['state'] == ('waiting_delivery' if mode == 'emoji' else 'done')
    assert calls == [('群', batch['id'], '普通群消息', 'member', '甲')]
    assert len(store.records('outbox')) == int(mode == 'emoji')


def test_archive_failure_is_safe_to_retry_and_does_not_discard_silent_batch():
    store = QueueStore(':memory:')
    store.capture('群', [], [Incoming('保存我', 'a', '', '甲', 'none')], group_mode=True, now=0)
    class Backend:
        def archive_group(self, *args, **kwargs):
            raise requests.ConnectionError('archive unavailable')
        def handle_reply(self, *args, **kwargs):
            pytest.fail('Archive failure precedes model submission')
    ModelWorker(store, Backend(), quiet=0, clock=lambda: 0).process_once()
    row = store.records('batches')[0]
    assert row['state'] == 'uncertain'
    assert row['reply_complete'] == 0
    assert store.delivery_events()[0]['action'] == 'model_retryable'


def test_same_group_next_batch_cannot_overtake_sticker():
    store = QueueStore(':memory:')
    store.capture('群', [], [Incoming('表情回复', 'a', '', '甲', 'emoji'),
                            Incoming('/next', 'a', '', '甲', 'text')], group_mode=True, now=0)
    class Backend:
        def handle_reply(self, *args, **kwargs):
            return Reply.from_text('后续回复')
    worker = ModelWorker(store, Backend(), quiet=0, clock=lambda: 0)
    assert worker.process_once()
    first = store.records('batches')[0]
    sticker = store.records('outbox')[0]
    assert sticker['batch_id'] == first['id']
    assert not worker.process_once()
    delivery = store.claim_delivery(now=0)
    assert delivery.kind == 'emoji'
    store.finish_delivery(delivery.id, 'sent', now=0)
    assert worker.process_once()
    assert [row['kind'] for row in store.records('outbox')] == ['emoji', 'text']


def test_archive_and_handle_transport_send_authenticated_structured_metadata(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda:
            {'seq': 5, 'inserted': 1} if url.endswith('/archive') else {'reply': 'ok'})
    monkeypatch.setattr(requests, 'post', post)
    proc = ButlerProcessor({'token': 'secret'}, raise_errors=True)
    router = Router(proc)
    assert router.archive_group('群', 'batch', 'hello', 'a', '甲', avatar='png') == 5
    router.handle_reply('群', '问题', member_key='a', avatar='png', group_context_seq=5)
    assert calls[0][0].endswith('/v1/group/archive')
    assert calls[0][1]['headers']['Authorization'] == 'Bearer secret'
    assert calls[0][1]['json']['messages'][0]['avatar'] == 'png'
    assert calls[1][1]['json']['group_context_seq'] == 5
    assert calls[1][1]['json']['avatar'] == 'png'


def test_user_observation_transport_is_authenticated_and_contains_no_prompt(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'users': []})
    monkeypatch.setattr(requests, 'post', post)
    router = Router(ButlerProcessor({'token': 'secret'}, raise_errors=True))
    router.observe_users('101', 'dm', [{'member_key': '', 'member_name': '101', 'avatar': ''}])
    url, sent = calls[0]
    assert url.endswith('/v1/users/observe')
    assert sent['headers']['Authorization'] == 'Bearer secret'
    assert sent['json']['contact'] == '101' and 'text' not in sent['json']['messages'][0]


def test_confirmed_mention_metadata_survives_decode_into_delivery():
    reply = ButlerProcessor._decode_reply({'reply': '回答', 'meta': {'mention_name': '甲'}}, None)
    assert reply.mention_name == '甲'
    store = QueueStore(':memory:')
    store.capture('群', [], [Incoming('问题', 'a', '', '观察昵称')], group_mode=True, now=0)
    class Backend:
        def handle_reply(self, *args, **kwargs):
            return reply
    ModelWorker(store, Backend(), quiet=0, clock=lambda: 0).process_once()
    delivery = store.records('outbox')[0]
    assert delivery['mention_name'] == '甲'


def test_only_recent_same_member_followup_after_bot_reply_is_direct():
    inbox = MainInbox.__new__(MainInbox)
    inbox.bot = {'mention_names': ['Bot'], 'command_prefix': '/', 'group_continuation_seconds': 120}
    now = [0]
    inbox.clock = lambda: now[0]
    assert inbox._group_direct_request('群', 'a', '@Bot 问题', True, 'other')
    assert not inbox._group_direct_request('群', 'b', '继续', False, 'self')
    assert inbox._group_direct_request('群', 'a', '继续', False, 'self')
    assert not inbox._group_direct_request('另群', 'a', '继续', False, 'self')
    assert inbox._group_direct_request('群', 'b', '/help', False, 'other')
    assert inbox._group_direct_request('群', 'b', 'Bot，帮我看看', False, 'other')
    now[0] = 121
    assert not inbox._group_direct_request('群', 'b', '继续', False, 'self')


def test_local_group_cooldown_budget_and_direct_request_bypass(monkeypatch):
    inbox = MainInbox.__new__(MainInbox)
    inbox.cfg = {'wechat': {}}
    inbox.bot = {'group_reply_chance': 1, 'group_reply_cooldown_seconds': 20,
                 'group_reply_budget': 2, 'group_reply_budget_window_seconds': 60}
    now = [0]
    inbox.clock = lambda: now[0]
    monkeypatch.setattr(inbox, '_should_interject', lambda: True)
    assert inbox._reply_mode(False, contact='群') == 'text'
    assert inbox._reply_mode(False, contact='群') == 'none'
    assert inbox._reply_mode(True, contact='群') == 'text'
    assert inbox._reply_mode(False, contact='另群') == 'text'
    now[0] = 21
    assert inbox._reply_mode(False, contact='群') == 'text'
    now[0] = 42
    assert inbox._reply_mode(False, contact='群') == 'none'
    now[0] = 61
    assert inbox._reply_mode(False, contact='群') == 'text'


def test_merged_long_messages_archive_as_individual_observations(tmp_path):
    ctx=context_store(tmp_path)
    store=QueueStore(':memory:')
    store.capture('群',[],[Incoming('a'*6000,'m','','甲'),Incoming('b'*6000,'m','','甲')],group_mode=True,now=0)
    calls=[]
    class Backend:
        def archive_group(self,contact,source_id,text,member_key,member_name,avatar=''):
            return ctx.archive(contact,source_id,[message(text,member_key)])['seq']
        def archive_group_messages(self,contact,source_id,messages):
            return ctx.archive(contact,source_id,messages)['seq']
        def handle_reply(self,*args,**kwargs):
            calls.append(kwargs)
            return Reply.from_text('ok')
    ModelWorker(store,Backend(),quiet=0,clock=lambda:0).process_once()
    assert len(calls)==1
    batch=store.records('batches')[0]
    seq=calls[0]['group_context_seq']
    all_rows=ctx.snapshot('群',seq+1,max_chars=15000)['messages']
    assert [len(row['text'])for row in all_rows]==[6000,6000]
    assert ctx.snapshot_for_request('群',batch['id'],seq)['messages']==[]


@pytest.mark.parametrize('value', [True, -1, float('inf')])
def test_group_cooldown_config_rejects_unbounded_values(value):
    from wxbot.config import validate_runtime_config
    with pytest.raises(ValueError, match='group_reply_cooldown_seconds'):
        validate_runtime_config({'bot': {'group_reply_cooldown_seconds': value}})
