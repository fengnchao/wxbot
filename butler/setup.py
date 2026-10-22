"""Portable initialization and read-only environment diagnostics."""
import importlib.metadata
import json
from pathlib import Path
import platform
import secrets
import socket
import tomllib

import tomlkit

from .config import Config,load

REPO=Path(__file__).resolve().parents[1]


def _new(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('x',encoding='utf-8') as fh:
            fh.write(text)
        return True
    except FileExistsError:
        return False


def initialize(root):
    root=Path(root).resolve()
    root.mkdir(parents=True,exist_ok=True)
    cfgpath=root/'config.butler.toml'
    if not cfgpath.exists():
        document=tomlkit.parse((REPO/'config.butler.codex.example.toml').read_text(encoding='utf-8'))
        document['server']['token']=secrets.token_urlsafe(32)
        document['wxbot']['token']=secrets.token_urlsafe(32)
        _new(cfgpath,tomlkit.dumps(document))
    cfg=load(cfgpath)
    if cfg.provider!='codex':
        return {'ok':True,'preserved_existing_backend':True,'config':str(cfgpath),
                'next':'Existing configuration preserved. Use a separate directory for a fresh Codex install.'}
    cfg.data_path().mkdir(parents=True,exist_ok=True)
    cfg.codex_home_path().mkdir(parents=True,exist_ok=True)
    from .business import BusinessStore
    BusinessStore(cfg.data_path()/'business.sqlite3')
    for path,body in [(cfg.heartbeat_config_path(),{'version':1,'users':{}}),
                      (cfg.group_file_path(),{'version':1,'groups':{}})]:
        _new(Path(path),json.dumps(body,ensure_ascii=False,indent=2)+'\n')
    wx=tomlkit.parse((REPO/'config.wxbot.example.toml').read_text(encoding='utf-8'))
    wx.setdefault('butler',{})['token']=cfg.token
    wx['butler']['url']=f'http://127.0.0.1:{cfg.port}'
    wx.setdefault('outbound',{})['token']=cfg.wxbot_token
    wx.setdefault('bot',{})['bound_users']=[]
    wx['bot']['bound_groups']=[]
    wx['bot']['mention_names']=[]
    wx.setdefault('model',{})['backend']='butler'
    _new(root/'config.wxbot.toml',tomlkit.dumps(wx))
    log=tomlkit.document()
    log['server']={'host':'127.0.0.1','port':8788}
    log['sources']={'home':str(cfg.data_path()),'wxbot_config':str(root/'config.wxbot.toml'),
                    'butler_config':str(cfgpath),'groups_file':cfg.group_file_path()}
    _new(root/'config.log.toml',tomlkit.dumps(log))
    _new(cfg.codex_home_path()/'config.toml',
         '# Dedicated bot login/state. Personal Codex configuration is not imported.\n'
         '[features]\nmemories = false\nplugins = false\nshell_tool = false\n')
    return {'ok':True,'config':str(cfgpath),'next':'python -m butler login; python -m butler doctor'}


def doctor(cfg,*,check_wechat=True):
    checks={}
    try:
        from .plugin import validate_plugin
        protocol=validate_plugin(cfg.plugin_path())
        from .catalogue import SkillCatalogue
        count=len(SkillCatalogue(cfg.plugin_path()/'skills').list())
        checks['plugin']={'ok':protocol.get('protocol_version')==1,'skills':count,'protocol_version':protocol.get('protocol_version')}
    except Exception as exc:
        checks['plugin']={'ok':False,'error':type(exc).__name__}
    checks['platform']={'ok':platform.system()=='Windows','platform':platform.system()}
    checks['codex_login']={'ok':(cfg.codex_home_path()/'auth.json').is_file(),
                           'hint':'python -m butler login' }
    try:
        checks['sdk']={'ok':True,'version':importlib.metadata.version('openai-codex')}
    except importlib.metadata.PackageNotFoundError:
        checks['sdk']={'ok':False,'hint':'Run scripts/setup.ps1'}
    checks['data_directory']={'ok':cfg.data_path().is_dir(),'path':str(cfg.data_path())}
    config_root=Path(cfg.config_dir or REPO)
    ports={'butler_port':cfg.port,'wxbot_port':8765,'log_port':8788}
    for filename,section,name in [('config.wxbot.toml','outbound','wxbot_port'),
                                  ('config.log.toml','server','log_port')]:
        path=config_root/filename
        if path.is_file():
            try:
                raw=tomllib.loads(path.read_text(encoding='utf-8-sig'))
                port=int((raw.get(section) or {}).get('port',ports[name]))
                if not 1<=port<=65535:raise ValueError('Invalid port')
                ports[name]=port
            except (OSError,ValueError,TypeError) as exc:
                checks[name]={'ok':False,'error':type(exc).__name__,'hint':'Check '+filename}
    for name,port in ports.items():
        if name in checks:continue
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1',port));available=True
            except OSError:
                available=False
        checks[name]={'ok':available,'port':port,'hint':'Available' if available else 'Port occupied; may already be running'}
    if check_wechat:
        try:
            import uiautomation as auto
            window=auto.WindowControl(searchDepth=1,ClassName='mmui::MainWindow')
            exists=window.Exists(0,0)
            path=Path(cfg.config_dir or REPO)/'config.wxbot.toml'
            wx=tomllib.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
            automation_id=((wx.get('wechat') or {}).get('main_window') or {}).get('session_list_id','session_list')
            controls=exists and window.Control(searchDepth=32,AutomationId=automation_id).Exists(0,0)
            checks['wechat']={'ok':bool(controls),'window_found':exists,'session_list_found':bool(controls),
                              'hint':'Read-only window/control detection; no focus or send'}
        except Exception as exc:
            checks['wechat']={'ok':False,'error':type(exc).__name__}
    return {'ok':all(row['ok'] for row in checks.values()),'backend':cfg.provider,'checks':checks}
