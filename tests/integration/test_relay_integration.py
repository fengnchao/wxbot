"""Authenticated local-only relay integration; fake delivery never reaches WeChat."""
from io import BytesIO
import json
from pathlib import Path
from contextlib import contextmanager
from threading import Thread
from http.server import ThreadingHTTPServer

from PIL import Image
import requests

from butler.config import Config
from butler.agent.core import Butler
from butler.server import make_handler
from butler.channels.telegram.relay.store import RelayStore


@contextmanager
def server(tmp_path):
    cfg=Config(provider='codex',data_dir=str(tmp_path/'data'),config_dir=str(tmp_path),token='test-secret')
    Path(cfg.group_file_path()).parent.mkdir(parents=True,exist_ok=True)
    Path(cfg.group_file_path()).write_text(json.dumps({'groups':{'1':['101']}}),encoding='utf-8')
    butler=Butler(cfg)
    httpd=ThreadingHTTPServer(('127.0.0.1',0),make_handler(butler,cfg))
    thread=Thread(target=httpd.serve_forever,daemon=True);thread.start()
    session=requests.Session();session.trust_env=False;session.headers['Authorization']='Bearer test-secret'
    try:yield f'http://127.0.0.1:{httpd.server_port}',session,cfg
    finally:
        session.close();httpd.shutdown();thread.join(3);httpd.server_close()


def test_media_http_auth_image_bytes_and_bundle_receipt(tmp_path,monkeypatch):
    from butler.delivery import push
    seen=[]
    monkeypatch.setattr(push,'push_bundle_to_wxbot',lambda cfg,contact,items,request_id,log=None:
                        (seen.append((contact,items,request_id)) is None,'sent'))
    with server(tmp_path) as (url,session,cfg):
        raw=BytesIO();Image.new('RGB',(20,20),'green').save(raw,'PNG')
        assert requests.post(url+'/v1/media',data=raw.getvalue(),timeout=3).status_code==401
        assert session.post(url+'/v1/media',data=b'not an image').status_code==400
        uploaded=session.post(url+'/v1/media',data=raw.getvalue()).json()
        mid=uploaded['media_id']
        actual=session.get(url+'/v1/media/'+mid)
        assert actual.content==raw.getvalue() and actual.headers['Content-Type']=='image/png'
        items=[{'kind':'text','text':'来源\n正文\nhttps://example.com/'},{'kind':'image','media_id':mid}]
        response=session.post(url+'/v1/push/bundle',json={'contact':'101','items':items,'request_id':'post:123'})
        assert response.json()=={'ok':True,'detail':'sent','contact':'101','request_id':'post:123'}
        assert seen==[('101',items,'post:123')]
        assert session.post(url+'/v1/push/bundle',json={'contact':'101','items':[{'kind':'image','path':'C:/secret.png'}],'request_id':'bad'}).status_code==400
        assert len(seen)==1
        assert session.get(url+'/v1/telegram-relay/authorize',params={'contact':'101'}).json()=={'contact':'101','allowed':True}
        assert session.get(url+'/v1/telegram-relay/authorize',params={'contact':'removed'}).json()['allowed'] is False
        Path(cfg.group_file_path()).write_text(json.dumps({'groups':{'1':[]}}),encoding='utf-8')
        assert session.get(url+'/v1/telegram-relay/authorize',params={'contact':'101'}).json()['allowed'] is False
        assert session.post(url+'/v1/push/bundle',json={'contact':'101','items':items,'request_id':'revoked'}).status_code==403
        assert len(seen)==1


def test_desktop_hold_is_persistent_and_requires_explicit_authenticated_ack(tmp_path):
    with server(tmp_path) as (url,session,cfg):
        store=RelayStore(cfg.data_path()/'telegram-relay'/'desktop.sqlite3')
        store.hold('desktop','channel','请先核对残留菜单')
        body={'id':'desktop','action':'cancelled','acknowledge':False}
        assert session.post(url+'/v1/telegram-relay/resolve',json=body).status_code==400
        assert store.has_hold()
        body['acknowledge']=True
        assert session.post(url+'/v1/telegram-relay/resolve',json=body).json()['ok']
        assert not store.has_hold()
