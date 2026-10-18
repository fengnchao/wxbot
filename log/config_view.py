"""Configuration inventory for the dashboard, with server-side secret removal."""
from copy import deepcopy
import json
import re
import time
import tomllib
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote

from common.flow_trace import queue_trace_path,butler_trace_path
from wxbot.queue_store import FAILURE_TIMEOUT_SECONDS


WX_DEFAULTS = {
    'bot': {'bound_users': [], 'bound_groups': [], 'mention_names': [], 'poll_interval':1.5,
            'reply_delay_min':.8, 'reply_delay_max':2.5, 'command_prefix':'/'},
    'queue': {'database':'cache/wxbot_queue.sqlite3', 'quiet_seconds':3., 'max_wait_seconds':10.,
              'confirm_timeout':5., 'max_model_requests':2},
    'butler': {'url':'http://127.0.0.1:8770', 'token':'', 'timeout':660},
    'outbound': {'enabled':True, 'host':'127.0.0.1', 'port':8765, 'token':''},
    'wechat': {'mode':'main', 'main_window':{'window_class':'mmui::MainWindow','chat_tab_name':'微信',
                'session_list_id':'session_list','search_depth':32,'listen_all':True,
                'max_scan_pages':20,'switch_timeout':3.},
               'group_sender':{'avatar_size':48,'avatar_left_offset':4,'avatar_top_offset':0,'member_names':{}},
               'sender_detect':{'strip_width':80,'diff_threshold':40,'min_pixels':20}},
}
BT_DEFAULTS = {
    'server':{'host':'127.0.0.1','port':8770,'token':''},
    'hermes':{'url':'http://127.0.0.1:8642','api_key':'','model':'hermes-agent','timeout':600,
              'root':'','send_identity':True,'profile_in_path':False},
    'wxbot':{'url':'http://127.0.0.1:8765','token':'','timeout':120},
    'dispatch':{'actions_enabled':True,'script_dir':'','respond_after_action':False},
    'log':{'flow_file':''}, 'groups':{'file':''}, 'contacts':[],
    'heartbeat':{'config_file':'','state_file':'','audit_file':'','min_interval_minutes':180,'max_interval_minutes':360},
}
_SECRET_WORDS = {'key','apikey','token','password','passwd','secret','authorization','credential',
                 'credentials','cookie','privatekey','auth','headers','signature','sig','jwt'}


def sensitive(key):
    name = re.sub(r'(?<=[a-z0-9])(?=[A-Z])','_',str(key)).lower()
    words = re.split(r'[^a-z0-9]+',name)
    return bool(_SECRET_WORDS.intersection(words))


def merge(defaults, raw):
    result = deepcopy(defaults)
    for key, value in raw.items():
        result[key] = merge(result[key],value) if isinstance(value,dict) and isinstance(result.get(key),dict) else deepcopy(value)
    return result


def leaves(data, prefix=''):
    for key, value in data.items():
        name = prefix+'.'+key if prefix else key
        if isinstance(value,dict) and value:
            yield from leaves(value,name)
        else:
            yield name,value


class ConfigView:
    def __init__(self, wxbot_path, butler_path, home, *, repo_root=None, groups_override=None, log_runtime=None):
        self.wxbot_path, self.butler_path = Path(wxbot_path), Path(butler_path)
        self.home = Path(home)
        self.root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
        self.groups_override, self.log_runtime = groups_override, log_runtime or {}
        self._secrets, self._raw, self._sources = set(), {}, []

    def _load(self, name, title, path, *, kind='toml'):
        source = {'id':name,'title':title,'path':'','status':'ok','error':'','modified_at':None}
        try:
            if not isinstance(path,(str,Path)):
                raise ValueError('无法确定配置路径')
            path = Path(path)
            source['path'] = str(path.resolve())
            with path.open('rb') as fh:
                data = tomllib.load(fh) if kind=='toml' else json.load(fh)
            if not isinstance(data,dict):
                raise ValueError('配置必须是对象')
            source['modified_at'] = path.stat().st_mtime
            self._collect(data)
        except FileNotFoundError:
            source.update(status='missing',error='文件不存在')
            data = {}
        except Exception as exc:
            source.update(status='error',error='读取失败（'+type(exc).__name__+'）')
            data = {}
        self._sources.append(source)
        self._raw[name] = data
        return data

    def _collect(self, data, secret=False):
        if isinstance(data,dict):
            for key,value in data.items():
                self._collect(value,secret or sensitive(key))
        elif isinstance(data,list):
            for value in data:
                self._collect(value,secret)
        elif isinstance(data,str):
            if secret and data:
                self._secrets.add(data)
                bearer = re.search(r'(?i)\bbearer\s+(\S+)',data)
                if bearer:
                    self._secrets.add(bearer[1])
            if '://' in data:
                try:
                    url = urlsplit(data)
                    for key,value in parse_qsl(url.query)+parse_qsl(url.fragment):
                        if sensitive(key) and value:
                            self._secrets.add(value)
                    if '@' in url.netloc:
                        self._secrets.add(url.netloc.rsplit('@',1)[0])
                except ValueError:
                    pass

    def sanitize(self, data, key=''):
        if sensitive(key):
            return '已配置（隐藏）' if data else '未配置'
        if isinstance(data,dict):
            return {self._text(str(k)):self.sanitize(v,k) for k,v in data.items()}
        if isinstance(data,(list,tuple)):
            return [self.sanitize(value) for value in data]
        return self._text(data) if isinstance(data,str) else data

    def _text(self, value):
        if '://' in value:
            try:
                url = urlsplit(value)
                netloc = '***@'+url.netloc.rsplit('@',1)[1] if '@' in url.netloc else url.netloc
                query = urlencode([(k,'***' if sensitive(k) else v) for k,v in parse_qsl(url.query,keep_blank_values=True)])
                fragment = url.fragment
                if any(sensitive(k) for k,v in parse_qsl(fragment)):
                    fragment = urlencode([(k,'***' if sensitive(k) else v) for k,v in parse_qsl(fragment,keep_blank_values=True)])
                value = urlunsplit((url.scheme,netloc,url.path,query,fragment))
            except ValueError:
                # Invalid URLs may still contain credentials; fail closed.
                value = 'URL 格式无效（已隐藏）'
        for secret in sorted(self._secrets,key=len,reverse=True):
            if len(secret)>=4 or value==secret:
                value = value.replace(secret,'***')
        return value

    def scrub(self, data):
        """Remove known secret values from an already shaped API payload, keeping its field names."""
        if isinstance(data,dict):
            return {key:self.scrub(value) for key,value in data.items()}
        if isinstance(data,(list,tuple)):
            return [self.scrub(value) for value in data]
        return self._text(data) if isinstance(data,str) else data

    def read(self):
        self._sources, self._raw, self._secrets = [], {}, set()
        wx = self._load('wxbot','wxbot 配置',self.wxbot_path)
        bt = self._load('butler','Butler 配置',self.butler_path)
        model = wx.get('model') or {}
        backend = model.get('backend','ollama') if isinstance(model,dict) else 'ollama'
        model_defaults = {'backend':'ollama','max_history':10,'system_prompt':''}
        if backend in ('openai','hermes'):
            model_defaults.update(url='http://127.0.0.1:8642/v1/chat/completions',model='hermes-agent',timeout=300,api_key='')
        elif backend not in ('butler','echo'):
            model_defaults.update(url='http://localhost:11434/api/chat',model='qwen2.5:7b',timeout=120)
        effective = merge(WX_DEFAULTS,{'model':model_defaults})
        effective = merge(effective,wx)
        full_bt = merge(BT_DEFAULTS,bt)
        sections = []
        for source,data,raw in (('wxbot',effective,wx),('butler',full_bt,bt)):
            raw_keys = {key for key,value in leaves(raw)}
            for group,values in data.items():
                rows=[]
                for key,value in leaves({group:values}):
                    rows.append({'key':source+'.'+key,'value':self.sanitize(value,key),
                                 'origin':'file' if key in raw_keys else 'default',
                                 'sensitive':sensitive(key)})
                sections.append({'id':source+'.'+group,'title':('wxbot' if source=='wxbot' else 'Butler')+' · '+group,
                                 'source':str(self.wxbot_path if source=='wxbot' else self.butler_path),'rows':rows})
        sections.append({'id':'wxbot.typing','title':'微信输入与分句（代码固定规则）',
                         'source':str(self.root/'wxbot'/'wechat'/'typing.py'),
                         'rows':[{'key':'wxbot.typing.'+key,'value':value,'origin':'code','sensitive':False} for key,value in
                                 (('chunk_size',5),('chunk_interval',.5),('input_method','分批剪贴板粘贴'),
                                  ('unicode_keyboard',False),('clipboard_restore','恢复原格式；保留用户期间新复制的内容'),
                                  ('verify_input',True),('split_reply_at','。？！!? / 代码区外换行'),
                                  ('reply_parts_source','Butler 完整生成后一次返回，wxbot 按用户逐句轮转'))]})
        sections.append({'id':'wxbot.failure_policy','title':'发送失败与人工核对（代码固定规则）',
                         'source':str(self.root/'wxbot'/'queue_store.py'),
                         'rows':[{'key':'wxbot.failure_policy.'+key,'value':value,'origin':'code','sensitive':False}
                                 for key,value in (('discard_after_seconds',FAILURE_TIMEOUT_SECONDS),
                                     ('starts_at','首次发件失败；重试/重启不重置'),
                                     ('states',['blocked','uncertain']),
                                     ('manual_actions','收发队列 → 人工核对：重试、确认已发、立即丢弃'))]})
        hermes = bt.get('hermes') or {}
        def resolved_path(value, fallback):
            if value is None or value=='':
                return fallback
            return Path(value) if isinstance(value,str) else None
        home = resolved_path(hermes.get('root'),self.home) if isinstance(hermes,dict) else None
        heartbeat = bt.get('heartbeat') or {}
        groups = bt.get('groups') or {}
        if not isinstance(heartbeat,dict): heartbeat={}
        if not isinstance(groups,dict): groups={}
        policy_path = resolved_path(heartbeat.get('config_file'),home/'cache'/'butler_heartbeat.json' if home else None)
        group_path = resolved_path(groups.get('file'),home/'cache'/'butler_groups.json' if home else None)
        policies = self._load('policies','用户角色 / Skill / 心跳开关',policy_path,kind='json')
        group_data = self._load('groups','用户分组',group_path,kind='json')
        dynamic_sources = [('policies','Butler 用户角色 / Skill / 心跳开关',policy_path,policies),
                           ('groups','Butler 用户分组',group_path,group_data)]
        warnings=[]
        log_policy_path=resolved_path(heartbeat.get('config_file'),self.home/'cache'/'butler_heartbeat.json')
        log_group_path=Path(self.groups_override) if self.groups_override else self.home/'cache'/'butler_groups.json'
        def same_path(a,b):
            try:
                return a is not None and b is not None and Path(a).resolve()==Path(b).resolve()
            except (ValueError,OSError):
                return False
        for name,title,path,other in (
                ('log_policies','log 页面当前使用的角色 / 心跳策略',log_policy_path,policy_path),
                ('log_groups','log 页面当前使用的用户分组',log_group_path,group_path)):
            if not same_path(path,other):
                data=self._load(name,title,path,kind='json')
                dynamic_sources.append((name,title,path,data))
                warnings.append(title+'与 Butler 来源不同，已分别列出，请核对服务的 home / 配置路径。')
        for name,title,path,data in dynamic_sources:
            sections.append({'id':name,'title':title,'source':str(path) if path else '路径无效，请检查 Butler 配置','rows':[
                {'key':name+'.'+key,'value':self.sanitize(value,key),'origin':'file','sensitive':sensitive(key)}
                for key,value in leaves(data)]})
        sections.append({'id':'log','title':'log 服务与配置来源','source':'log 进程参数 / 环境变量',
                         'rows':[{'key':'log.'+key,'value':value,'origin':'runtime','sensitive':False} for key,value in
                                 {'home':str(self.home),'wxbot_config':str(self.wxbot_path),'butler_config':str(self.butler_path),
                                  'groups_file':str(log_group_path),
                                  'heartbeat_config_file':str(log_policy_path) if log_policy_path else '路径无效',
                                  **self.log_runtime}.items()]})
        try:
            trace_paths=self.flow_options()['trace_paths']
            trace_rows=[{'key':name+'.flow_trace_file','value':str(path) if path else '未启用磁盘流转记录',
                         'origin':'code','sensitive':False} for name,path in zip(('wxbot','butler'),trace_paths)]
            sections.append({'id':'log.flow_trace','title':'消息流转记录文件（由配置推导）',
                             'source':str(self.root/'common'/'flow_trace.py'),'rows':trace_rows})
        except Exception:
            warnings.append('流转记录路径无法由当前配置推导，请检查 wxbot / Butler 配置。')
        # Run the final whole payload through the scrubber: a secret may also occur in a path or a harmless field.
        return self.scrub({'read_only':True,'runtime_verified':False,'at':time.time(),'sources':self._sources,'sections':sections,'warnings':warnings,
                              'note':'展示文件中的配置、缺省值和代码规则；未核对运行中 wxbot/Butler 的已加载配置。修改文件后需按对应服务的生效方式处理。'})

    def queue_options(self):
        if 'wxbot' not in self._raw:
            self.read()
        source = next(s for s in self._sources if s['id']=='wxbot')
        if source['status']!='ok':
            raise ValueError('wxbot 配置不可读取')
        cfg = self._raw['wxbot']
        queue = cfg.get('queue') or {}
        bot = cfg.get('bot') or {}
        name = str(queue.get('database','cache/wxbot_queue.sqlite3'))
        path = name if name==':memory:' else str(Path(name) if Path(name).is_absolute() else self.root/name)
        return {'path':path,'quiet':float(queue.get('quiet_seconds',3)),
                'max_wait':float(queue.get('max_wait_seconds',10)),'prefix':bot.get('command_prefix','/')}

    def flow_options(self):
        queue = self.queue_options()
        bt = self._raw.get('butler') or {}
        log = bt.get('log') or {}
        hermes = bt.get('hermes') or {}
        flow_file = log.get('flow_file') if isinstance(log,dict) else None
        root = hermes.get('root') if isinstance(hermes,dict) else None
        if not flow_file and isinstance(root,str) and root:
            flow_file = str(Path(root)/'cache'/'wxbot.log')
        bt_trace = butler_trace_path(flow_file) if isinstance(flow_file,str) else None
        return {'queue_options':queue,'trace_paths':[queue_trace_path(queue['path']),bt_trace]}
