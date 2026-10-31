"""Portable initialization and read-only environment diagnostics."""
import importlib.metadata
import json
from pathlib import Path
import platform
import secrets
import socket
import tomllib

import tomlkit

from common.paths import REPO_ROOT
from butler.config import Config,load

REPO=REPO_ROOT


def _new(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('x',encoding='utf-8') as fh:
            fh.write(text)
        return True
    except FileExistsError:
        return False


def initialize(root):
    """Noninteractive, idempotent first installation using built-in defaults."""
    from butler.runtime.install_wizard import install, Connection
    return install(root, Connection(provider='codex'))


def doctor(cfg,*,check_wechat=True):
    checks={}
    from butler.runtime.install_wizard import installation_mode
    mode=installation_mode(cfg.config_dir or REPO)
    if mode=='direct':
        checks['model_chain']={'ok':False,'hint':'Stop local services, then run python -m butler migrate'}
    try:
        from butler.runtime.plugin import validate_plugin
        protocol=validate_plugin(cfg.plugin_path())
        from butler.agent.catalogue import SkillCatalogue
        count=len(SkillCatalogue(cfg.plugin_path()/'skills').list())
        checks['plugin']={'ok':protocol.get('protocol_version')==1,'skills':count,'protocol_version':protocol.get('protocol_version')}
    except Exception as exc:
        checks['plugin']={'ok':False,'error':type(exc).__name__}
    checks['platform']={'ok':platform.system()=='Windows','platform':platform.system()}
    if mode=='local' and cfg.provider=='codex':
        checks['codex_login']={'ok':bool(cfg.codex_api_key) or (cfg.codex_home_path()/'auth.json').is_file(),
                               'hint':'API Key 已配置；未调用模型验证' if cfg.codex_api_key else 'python -m butler login' }
        try:
            checks['sdk']={'ok':True,'version':importlib.metadata.version('openai-codex')}
        except importlib.metadata.PackageNotFoundError:
            checks['sdk']={'ok':False,'hint':'Run scripts/setup.ps1'}
    checks['data_directory']={'ok':cfg.data_path().is_dir(),'path':str(cfg.data_path())}
    config_root=Path(cfg.config_dir or REPO)
    ports={'butler_port':cfg.port,'wxbot_port':8765,'log_port':8788}
    if mode!='local': ports.pop('butler_port')
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
            path=Path(cfg.config_dir or REPO)/'config.wxbot.toml'
            wx=tomllib.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
            wcfg=wx.get('wechat') or {}
            class_name=(wcfg.get('main_window') or {}).get('window_class','mmui::MainWindow')
            window=auto.WindowControl(searchDepth=1,ClassName=class_name)
            exists=window.Exists(0,0)
            automation_id=((wx.get('wechat') or {}).get('main_window') or {}).get('session_list_id','session_list')
            controls=exists and window.Control(searchDepth=32,AutomationId=automation_id).Exists(0,0)
            checks['wechat']={'ok':bool(controls),'window_found':exists,'session_list_found':bool(controls),
                              'hint':'Read-only window/control detection; no focus or send'}
        except Exception as exc:
            checks['wechat']={'ok':False,'error':type(exc).__name__}
    return {'ok':all(row['ok'] for row in checks.values()),'backend':cfg.provider,'mode':mode,'checks':checks}
