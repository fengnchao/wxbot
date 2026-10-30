"""Opt-in real Codex integration probe. Temporary services/state; never sends WeChat."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from butler.config import Config
from butler.agent.core import Butler
from butler.server import make_handler
from butler.identity.contacts import load_contacts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-home',required=True,help='Codex home already authenticated by this user; no credentials are copied')
    parser.add_argument('--model',default='')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='butler-codex-probe-') as temp:
        cfg=Config(provider='codex',token='probe-only-token',data_dir=temp,codex_home=str(Path(args.auth_home).resolve()),
                   codex_model=args.model,codex_timeout=120,wxbot_url='http://127.0.0.1:1',
                   contacts=load_contacts([{'name':'probe-alice','uid':'probe-alice'},{'name':'probe-bob','uid':'probe-bob'}]))
        policy=Path(cfg.heartbeat_config_path());policy.parent.mkdir(parents=True)
        policy.write_text(json.dumps({'users':{
            'probe-alice':{'role_skill':'paimon','allowed_skills':['butler-memory'],'heartbeat_enabled':False},
            'probe-bob':{'role_skill':'tong-jincheng-perspective','allowed_skills':[],'heartbeat_enabled':False}}}),encoding='utf-8')
        butler=Butler(cfg)
        def forbidden(*a,**kw):raise AssertionError('Probe forbids all outbound delivery')
        butler.push=forbidden
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(butler,cfg))
        cfg.port=server.server_port
        threading.Thread(target=server.serve_forever,daemon=True).start()
        outputs=[]
        try:
            for contact,text in [('probe-alice','这轮聊天的暗号是青柠。请调用 memory_set 保存 key=probe-code、value=青柠，然后用一句角色口吻说你是谁。'),
                                 ('probe-bob','你是谁？请用一句话回答。')]:
                result=butler.handle(contact,text)
                if result.meta.get('error'):raise RuntimeError(result.meta['error']+' / '+butler.backend.last_error)
                outputs.append({'contact':contact,'reply':result.reply})
            butler.backend.close()
            from butler.backends.codex import owner_key
            stored=butler.store.memories(owner_key(butler.contact_of('probe-alice')))
            if not any(x['key']=='probe-code' and x['value']=='青柠' for x in stored):
                raise RuntimeError('Real MCP memory_set was not executed')
            result=butler.handle('probe-alice','这轮聊天的暗号是什么？请用 memory_get 核对，只回暗号。')
            if result.meta.get('error') or '青柠' not in (result.reply or ''):
                raise RuntimeError('Thread/memory resume check did not succeed')
            outputs.append({'contact':'probe-alice','reply':result.reply})
            print(json.dumps({'ok':True,'outputs':outputs,'events':butler.store.events(20),'wechat_sent':False},ensure_ascii=False,indent=2))
        finally:
            butler.backend.close();server.shutdown();server.server_close()


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
