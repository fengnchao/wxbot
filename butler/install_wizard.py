"""Interactive first installation. No model calls, login copying or service starts."""
from dataclasses import dataclass, field
from getpass import getpass
import ipaddress
import json
import os
from pathlib import Path
import secrets
import tomllib
from urllib.parse import urlsplit, urlunsplit

import tomlkit

from .defaults import butler_defaults, wxbot_defaults, log_defaults

PRESETS = {
    'codex': ('本机 Codex（本人登录）', '', ''),
    'hermes': ('Hermes API Server', 'http://127.0.0.1:8642/v1/chat/completions', 'hermes-agent'),
    'openclaw': ('OpenClaw Gateway（先启用 HTTP 对话端点）', 'http://127.0.0.1:18789/v1/chat/completions', ''),
    'cursor': ('Cursor 无界面 CLI（只读问答）', '', ''),
    'deepseek': ('DeepSeek 模型 API', 'https://api.deepseek.com/v1/chat/completions', ''),
    'butler': ('已有 Butler 服务', 'http://127.0.0.1:8770', ''),
    'custom': ('自定义 API（Chat Completions / Responses）', '', ''),
}
CONFIG_NAMES = ('config.butler.toml', 'config.wxbot.toml', 'config.log.toml')


@dataclass
class Connection:
    provider: str = 'codex'
    protocol: str = ''
    url: str = ''
    api_key: str = field(default='', repr=False)
    model: str = ''
    agent: str = 'main'
    executable: str = 'agent'
    work_dir: str = 'data/cursor'
    timeout: int = 600


def normalize_url(value, *, suffix=''):
    value = value.strip()
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username
                 and not parsed.password and not parsed.query and not parsed.fragment and parsed.port != 0
                 and not any(ch.isspace() or ord(ch)<32 for ch in value) and '\\' not in value)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('请填写有效 HTTP/HTTPS 地址；不允许内嵌账号、密码、查询参数或片段')
    path = parsed.path.rstrip('/')
    if suffix and path.endswith(suffix): path = path[:-len(suffix)]
    return urlunsplit((parsed.scheme, parsed.netloc, path, '', ''))


def listener(value, *, suffix=''):
    base = normalize_url(value, suffix=suffix)
    parsed = urlsplit(base)
    try: local = parsed.hostname == 'localhost' or ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError: local = False
    if not local or parsed.scheme != 'http' or parsed.path:
        raise ValueError('本机服务请使用 HTTP 回环地址，不能使用远端主机或额外路径')
    # Existing HTTP servers bind IPv4; reject IPv6 rather than generate an unusable listener.
    if ':' in parsed.hostname:
        raise ValueError('本机监听请使用 127.0.0.1 或 localhost')
    return parsed.hostname, parsed.port or 80, base


def installation_mode(root):
    path = Path(root)/'config.wxbot.toml'
    if not path.exists(): return 'local'
    with path.open('rb') as fh: raw = tomllib.load(fh)
    mode = (raw.get('installation') or {}).get('mode', 'local')
    if mode not in {'local', 'external', 'direct'}: raise ValueError('未知安装模式')
    return mode


def connection_model(conn):
    if conn.provider not in PRESETS: raise ValueError('不支持的智能体类型')
    if type(conn.timeout) is not int or not 1 <= conn.timeout <= 86400: raise ValueError('超时须为 1–86400 秒')
    if conn.provider in {'codex', 'butler'}: return {'backend': 'butler'}
    if conn.provider == 'cursor':
        if not conn.executable.strip() or not conn.work_dir.strip(): raise ValueError('Cursor 需要程序位置和专属目录')
        return {'backend': 'cursor', 'executable': conn.executable, 'work_dir': conn.work_dir,
                'api_key': conn.api_key, 'model': conn.model, 'timeout': conn.timeout}
    backend = {'hermes':'hermes', 'openclaw':'openclaw', 'deepseek':'openai'}.get(conn.provider, conn.protocol)
    if backend not in {'hermes','openclaw','openai','responses'}: raise ValueError('请选择已支持的 API 协议')
    endpoint = normalize_url(conn.url or PRESETS[conn.provider][1])
    path = urlsplit(endpoint).path
    suffix = '/responses' if backend == 'responses' else '/chat/completions'
    if not path.endswith(suffix):
        endpoint += suffix if path.endswith('/v1') else '/v1' + suffix
    model = conn.model or PRESETS[conn.provider][2]
    if backend=='openclaw': model = model or 'openclaw/' + (conn.agent or 'main')
    if not model: raise ValueError('请填写模型名（按服务端实际提供的名称）')
    result = {'backend':backend, 'url':endpoint, 'api_key':conn.api_key, 'model':model,
              'timeout':conn.timeout, 'max_history':10}
    if backend=='openclaw': result['agent']=conn.agent or 'main'
    return result


def _finish_data(root, nickname=''):
    from .config import load
    from .setup import _new
    from .business import BusinessStore
    cfg = load(root/'config.butler.toml')
    BusinessStore(cfg.data_path()/'business.sqlite3')
    for name, body in [('butler_heartbeat.json', {'version':1,'users':{}}),
                       ('butler_groups.json', {'version':1,'groups':{}})]:
        _new(cfg.data_path()/'cache'/name, json.dumps(body)+'\n')
    if installation_mode(root)=='local' and cfg.provider=='codex':
        _new(cfg.codex_home_path()/'config.toml',
             '# Dedicated bot state; no personal configuration is imported.\n'
             '[features]\nmemories = false\nplugins = false\nshell_tool = false\n')
    from .migration import migrate_installation
    migrate_installation(root)
    if nickname:
        from .directory import DirectoryStore, directory_path
        store = DirectoryStore(directory_path(root/'config.wxbot.toml'))
        state=store.initialize_channel()
        state['channel']['bot']['mention_names']=[nickname]
        store.save(state,state['version'])


def install(root, connection=None, *, nickname='', wxbot_url='http://127.0.0.1:8765',
            butler_url='http://127.0.0.1:8770', log_url='http://127.0.0.1:8788',
            wxbot_token='', butler_token=''):
    root = Path(root).resolve()
    if any((root/name).exists() for name in CONFIG_NAMES):
        return {'ok': True, 'preserved_existing': True, 'next':'已有配置保留；升级目录请运行 python -m butler migrate'}
    conn = connection or Connection()
    model = connection_model(conn)
    wxhost, wxport, wxbase = listener(wxbot_url, suffix='/send')
    bhost, bport, bbase = listener(butler_url, suffix='/v1/handle')
    lhost, lport, lbase = listener(log_url)
    mode = 'local' if conn.provider=='codex' else ('external' if conn.provider=='butler' else 'direct')
    ports = [wxport, lport] + ([bport] if mode=='local' else [])
    if len(ports)!=len(set(ports)): raise ValueError('本机服务端口不能相同')
    bt, wx, lg = butler_defaults(), wxbot_defaults(), log_defaults()
    wx['installation'] = {'mode':mode, 'provider':conn.provider}
    bt['directory'] = wx['directory'] = {'database':'data/business.sqlite3'}
    bt['server'].update(host=bhost, port=bport, token=butler_token or secrets.token_urlsafe(32))
    bt['wxbot'].update(url=wxbase, token=wxbot_token or secrets.token_urlsafe(32))
    bt['codex']['model'] = conn.model if conn.provider=='codex' else ''
    if conn.provider=='codex' and conn.api_key:bt['codex']['api_key']=conn.api_key
    wx['outbound'].update(host=wxhost, port=wxport, token=bt['wxbot']['token'])
    wx['model'] = model
    if mode=='external':
        wx['butler'].update(url=normalize_url(conn.url or PRESETS['butler'][1], suffix='/v1/handle'), token=conn.api_key)
    elif mode=='local': wx['butler'].update(url=bbase, token=bt['server']['token'])
    else: wx.pop('butler', None)
    lg['server'].update(host=lhost, port=lport)
    root.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for name, document in zip(CONFIG_NAMES, (bt,wx,lg)):
            path = root/name
            with path.open('x', encoding='utf-8') as fh:
                created.append(path)
                fh.write(tomlkit.dumps(document)); fh.flush(); os.fsync(fh.fileno())
        _finish_data(root, nickname)
    except BaseException:
        for path in created: path.unlink(missing_ok=True)
        raise
    prefix = f'python -m butler --config "{root / CONFIG_NAMES[0]}"'
    return {'ok':True, 'provider':conn.provider, 'mode':mode,
            'config_directory':str(root), 'send_url':wxbase+'/send', 'dashboard':lbase,
            'receive_url':wx['butler']['url']+'/v1/handle' if mode in {'local','external'} else model.get('url','Cursor CLI'),
            'next':(([prefix+' login'] if mode=='local' and not conn.api_key else []) + [prefix+' doctor', prefix+' start']),
            'note':'安装完成；未启动服务。直接模型接入不提供 Butler 记忆或业务工具。'}


def run_wizard(root, *, input_fn=input, secret_fn=getpass, output=print):
    root = Path(root).resolve()
    if any((root/n).exists() for n in CONFIG_NAMES): return install(root)
    def ask(prompt, default=''):
        return input_fn(f'{prompt}' + (f' [{default}]' if default else '') + ': ').strip() or default
    try:
        output('选择接入方式：\n'+'\n'.join(f'  {i}. {key} — {row[0]}' for i,(key,row) in enumerate(PRESETS.items(),1)))
        choice = ask('编号或名称', 'codex')
        if choice.isdigit() and 1<=int(choice)<=len(PRESETS): choice=list(PRESETS)[int(choice)-1]
        if choice not in PRESETS: raise ValueError('请选择列表中的接入方式')
        conn = Connection(provider=choice)
        if choice=='codex':
            conn.model=ask('模型名（留空使用账户默认）')
            conn.api_key=secret_fn('Codex API Key（留空稍后使用本人 Codex 登录，输入不回显）: ').strip()
        elif choice=='cursor':
            conn.executable=ask('Cursor CLI 程序位置', 'agent')
            conn.work_dir=ask('专属工作目录（相对安装目录）', 'data/cursor')
            conn.model=ask('模型名（可留空）')
            conn.api_key=secret_fn('Cursor API Key（留空使用本机登录，输入不回显）: ').strip()
        else:
            if choice=='custom': conn.protocol=ask('协议 openai / responses', 'openai')
            conn.url=ask('接口地址', PRESETS[choice][1])
            conn.api_key=secret_fn('API Key / Token（本机无鉴权可留空，输入不回显）: ').strip()
            if choice=='openclaw': conn.agent=ask('目标 Agent', 'main')
            elif choice!='butler': conn.model=ask('模型名', PRESETS[choice][2])
        wxurl=ask('本机 wxbot 消息地址', 'http://127.0.0.1:8765')
        wxtoken=secret_fn('消息服务 Token（留空随机生成）: ').strip()
        bturl=ask('本机 Butler 接收地址', 'http://127.0.0.1:8770') if choice=='codex' else 'http://127.0.0.1:8770'
        logurl=ask('管理台地址', 'http://127.0.0.1:8788')
        nickname=ask('机器人微信昵称（稍后可在管理台修改）')
        connection_model(conn)
        listener(wxurl,suffix='/send'); listener(bturl,suffix='/v1/handle'); listener(logurl)
        if choice=='butler': normalize_url(conn.url,suffix='/v1/handle')
        output(f'接入：{PRESETS[choice][0]}；消息地址：{wxurl}；管理台：{logurl}；密钥：已隐藏/随机生成。')
        output('微信使用主窗口默认配置；换电脑后运行 doctor 检测窗口与控件。')
        if ask('确认保存？y/n', 'n').lower() not in {'y','yes','是'}: return {'ok':False,'cancelled':True}
        return install(root,conn,nickname=nickname,wxbot_url=wxurl,butler_url=bturl,log_url=logurl,wxbot_token=wxtoken)
    except (EOFError, KeyboardInterrupt):
        return {'ok':False,'cancelled':True}
    except ValueError as exc:
        return {'ok':False,'error':str(exc)}
