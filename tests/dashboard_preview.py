"""Disposable browser QA server. No real Butler, model, clipboard or WeChat calls."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import sqlite3
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from butler.setup import initialize
from wxbot.queue_store import QueueStore,Incoming


def main():
    import tomlkit
    with tempfile.TemporaryDirectory(prefix='管家 页面验证 ') as directory:
        root=Path(directory)
        initialize(root)
        wx=root/'config.wxbot.toml';bt=root/'config.butler.toml';lc=root/'config.log.toml'
        queue=root/'data/cache/queue.sqlite3'
        doc=tomlkit.parse(wx.read_text(encoding='utf-8'));doc['queue']['database']=str(queue)
        wx.write_text(tomlkit.dumps(doc),encoding='utf-8')
        doc=tomlkit.parse(bt.read_text(encoding='utf-8'))
        doc['contacts']=[{'name':'示例用户 A','uid':'a','profile':'default','label':'小林'},
                         {'name':'项目讨论群','uid':'group','profile':'default','channel_type':'group'}]
        bt.write_text(tomlkit.dumps(doc),encoding='utf-8')
        os.environ.update(WXBOT_CONFIG=str(wx),BUTLER_CONFIG=str(bt),LOG_CONFIG=str(lc),HERMES_HOME=str(root/'data'))
        store=QueueStore(queue)
        now=time.time()
        store.capture('示例用户 A',[],[Incoming('你好，帮我看一下这个问题。')],now=now-400)
        store.prepare(quiet=0,max_wait=10,prefix='/',now=now-390)
        batch=store.claim_batch(now=now-380)
        store.finish_batch_parts(batch.id,('你好，这是一条完整回复。',),now=now-375)
        delivery=store.claim_delivery(now=now-370)
        store.finish_delivery(delivery.id,'blocked',now=now-30,error='输入框焦点发生变化，未按回车')
        for i in range(61):store.capture('项目讨论群',[],[Incoming(f'第 {i+1} 条示例收件：'+'这是一段较长消息，'*8,member_key='member-'+str(i%3))],group_mode=True,now=now-61+i)
        with sqlite3.connect(queue) as db:
            db.execute("INSERT INTO batches(id,contact,text,context,state,created_at,started_at,attempts) VALUES('model-demo','示例用户 B','记住我喜欢简短回复','','processing',?,?,1)",(now-10,now-9))
            db.execute("INSERT INTO inbox(contact,text,received_at,batch_id,member_key,context,group_mode) VALUES('示例用户 B','记住我喜欢简短回复',?,'model-demo','','',0)",(now-11,))
            db.execute("INSERT INTO outbox(id,contact,text,state,created_at,not_before) VALUES('push-demo','提醒用户 C','该出门了，记得带伞。','pending',?,?)",(now-5,now-5))
            db.execute("INSERT INTO outbox(id,contact,text,state,created_at,not_before,finished_at) VALUES('sent-demo','示例用户 D','收到，已经记下了。','sent',?,?,?)",(now-20,now-20,now-2))
        store.close()
        import log.server as dashboard
        runtime={'backend':'codex','protocol_version':1,
                 'memory':[{'contact':'示例用户 A','key':'偏好','value':'喜欢简洁回复。'*25,'updated':now}],
                 'events':[{'id':1,'at':now,'contact':'示例用户 A','stage':'model_tool','status':'completed','details':'工具执行完成，结果已记录。'}],
                 'reminders':[{'id':'test-reminder','contact':'示例用户 A','text':'明天整理资料','schedule':'in 1d','due':now+86400,'status':'scheduled','detail':''}]}
        dashboard.fetch_butler_data=lambda *args,**kwargs:runtime
        dashboard.fetch_hermes_skills=lambda *args,**kwargs:[{'name':'butler-companion','description':'简洁自然的默认助理','tags':['butler-role']},{'name':'butler-memory','description':'记住用户明确提供的偏好','tags':[]}]
        class PreviewHandler(dashboard.Handler):
            home=str(root/'data')

            def do_GET(self):
                if self.path.startswith('/preview/mode/'):
                    self.server.preview_mode=self.path.rsplit('/',1)[-1]
                    self._json({'mode':self.server.preview_mode});return
                if '--workflow' in sys.argv and self.path=='/api/workflow':
                    mode=getattr(self.server,'preview_mode','normal')
                    if mode=='offline':
                        self._json({'error':'simulated offline'},503);return
                    view=self._config_view();view.read()
                    from log.workflow_view import WorkflowView
                    payload=WorkflowView(**view.flow_options(),contacts=[{'name':'项目讨论群','uid':'group-demo','channel_type':'group'}]).read()
                    # Synthetic model progress only in this disposable preview, never a real send.
                    model=next(m for m in payload['messages'] if m['id']=='model-demo')
                    stamp=int(time.time()//3)*3
                    model['stage']=3
                    model['events'].append({'key':'preview-'+str(stamp),'ts':stamp,'node':3,'stage':'hermes_tool','status':'started','tool':'memory.list'})
                    if mode=='empty':
                        payload['messages']=[];payload['counts']={k:0 for k in payload['counts']}
                    self._json(payload);return
                super().do_GET()
        handler=PreviewHandler
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        print('PREVIEW_URL=http://127.0.0.1:'+str(server.server_port)+'/',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()


if __name__=='__main__':main()
