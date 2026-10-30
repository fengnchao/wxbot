"""Real adapter -> callback -> durable queue -> readonly dashboard, fake network only."""
import json
from contextlib import closing

import pytest

from wxbot.processor.openai_compat import OpenAICompatProcessor
from wxbot.processor.router import Router
from wxbot.queue_worker import ModelWorker
from wxbot.queue_store import QueueStore,Incoming
from log.model_stream_view import read_stream


@pytest.mark.parametrize('interrupt',[False,True])
def test_chat_stream_reaches_queue_before_generation_finishes(tmp_path,monkeypatch,interrupt):
    path=tmp_path/'queue.db'
    with closing(QueueStore(path)) as store:
        store.capture('A',[],[Incoming('hello')],now=1)
        seen=[]
        def frame(delta,finish=None):
            return ('data: '+json.dumps({'id':'completion','choices':[{'index':0,'delta':delta,'finish_reason':finish}]})).encode()
        class Response:
            def raise_for_status(self):pass
            def close(self):pass
            def iter_lines(self):
                yield frame({'content':'第一句。'});yield b''
                # This executes before the fake provider completes generation.
                rows=store.records('outbox')
                assert len(rows)==1 and rows[0]['text']=='第一句。'
                seen.append(rows[0]['id'])
                yield frame({'content':'第二句'});yield b''
                first=store.claim_delivery(now=4)
                part=store.stream_part(first.id)
                assert part['sealed']
                with store.stream_enter_gate(first.id,first.text,part['version']) as allowed:assert allowed
                store.finish_delivery(first.id,'sent',now=5)
                if interrupt:return
                yield frame({'content':'！'});yield b''
                yield frame({},'stop');yield b''
                yield b'data: [DONE]';yield b''
        def post(*args,**kwargs):
            assert kwargs['stream'] and kwargs['json']['stream']
            return Response()
        monkeypatch.setattr('wxbot.processor.openai_compat.requests.post',post)
        router=Router(OpenAICompatProcessor({'backend':'openai','model':'fake'}))
        worker=ModelWorker(store,router,quiet=0,max_wait=1,typing_mode='streaming',clock=lambda:3)
        assert worker.process_once()
        assert seen
        rows=store.records('outbox')
        assert rows[0]['state']=='sent'
        rid=rows[0]['batch_id']
        events=read_stream(path,rid)['events']
        assert any(e['type']=='answer_delta' for e in events)
        if interrupt:
            assert all(row['state'] in {'sent','skipped'} for row in rows)
            assert store.stream_snapshot(rid)['status']=='cancelled'
            assert not worker.process_once(),'interrupted request must not replay'
        else:
            assert ''.join(row['text'] for row in rows)=='第一句。第二句！'
            assert rows[1]['state']=='pending' and store.stream_part(rows[1]['id'])['sealed']
            assert store.get_batch(rid)['reply_complete']
