"""Configuration inventory for the dashboard, with server-side secret removal."""
from copy import deepcopy
import json
import hashlib
import re
import time
import tomllib
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote, unquote_plus

from common.flow_trace import queue_trace_path,butler_trace_path
from wxbot.queue_store import FAILURE_TIMEOUT_SECONDS
from wxbot.model_recovery import MODEL_MAX_ATTEMPTS,MODEL_RETRY_DELAYS
from log.config_schema import row_metadata
from log.settings import DEFAULTS as LOG_DEFAULTS,config_path


WX_DEFAULTS = {
    'bot': {'bound_users': [], 'bound_groups': [], 'mention_names': [], 'poll_interval':1.5,
            'reply_delay_min':.8, 'reply_delay_max':2.5, 'command_prefix':'/',
            'group_reply_chance':.1,'emoji_chance':.2,'group_reply_cooldown_seconds':30,
            'group_reply_budget':10,'group_reply_budget_window_seconds':600,'group_continuation_seconds':120},
    'queue': {'database':'cache/wxbot_queue.sqlite3', 'quiet_seconds':3., 'max_wait_seconds':10.,
              'confirm_timeout':5., 'max_model_requests':2,'failure_discard_seconds':180,'restart_chat_policy':'discard'},
    'butler': {'url':'http://127.0.0.1:8770', 'token':'', 'timeout':660},
    'outbound': {'enabled':True, 'host':'127.0.0.1', 'port':8765, 'token':''},
    'wechat': {'mode':'main', 'main_window':{'window_class':'mmui::MainWindow','chat_tab_name':'微信',
                'session_list_id':'session_list','search_depth':32,'listen_all':True,
                'max_scan_pages':20,'switch_timeout':3.},
               'group_sender':{'avatar_size':48,'avatar_left_offset':4,'avatar_top_offset':0,'member_names':{},
                               'identity_avatar_left_offset':12,'identity_avatar_top_offset':0},
               'sender_detect':{'strip_width':80,'diff_threshold':40,'min_pixels':20},
               'typing':{'mode':'chunked','chunk_size':5,'chunk_interval':.25}},
}
BT_DEFAULTS = {
    'reply':{'chunk_chars':500},
    'context':{'group_messages':30,'group_characters':6000},
    'agent':{'provider':'hermes','data_dir':'data'},
    'codex':{'home':'','plugin_root':'','model':'','timeout':600,'max_workers':2,'idle_seconds':600},
    'server':{'host':'127.0.0.1','port':8770,'token':''},
    'hermes':{'url':'http://127.0.0.1:8642','api_key':'','model':'hermes-agent','timeout':600,
              'root':'','send_identity':True,'profile_in_path':False},
    'wxbot':{'url':'http://127.0.0.1:8765','token':'','timeout':120},
    'dispatch':{'actions_enabled':True,'script_dir':'','respond_after_action':False},
    'log':{'flow_file':''}, 'groups':{'file':''}, 'contacts':[], 'message_routes':[],
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


def paths(data,prefix=()):
    for key,value in data.items():
        current=(*prefix,key)
        if isinstance(value,dict) and value:yield from paths(value,current)
        else:yield current,value


def source_version(path,body):
    return hashlib.sha256(str(Path(path).resolve()).encode('utf-8')+b'\0'+body).hexdigest()


class ConfigView:
    def __init__(self, wxbot_path, butler_path, home, *, repo_root=None, groups_override=None, log_runtime=None,
                 log_config_path=None):
        self.wxbot_path, self.butler_path = Path(wxbot_path), Path(butler_path)
        self.home = Path(home)
        self.root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
        self.groups_override, self.log_runtime = groups_override, log_runtime or {}
        self.log_config_path=Path(log_config_path) if log_config_path else config_path()
        self._secrets, self._raw, self._sources = set(), {}, []

    def _load(self, name, title, path, *, kind='toml'):
        source = {'id':name,'title':title,'path':'','status':'ok','error':'','modified_at':None}
        try:
            if not isinstance(path,(str,Path)):
                raise ValueError('无法确定配置路径')
            path = Path(path)
            source['path'] = str(path.resolve())
            body=path.read_bytes()
            source['version']=source_version(path,body)
            data = tomllib.loads(body.decode('utf-8-sig')) if kind=='toml' else json.loads(body.decode('utf-8-sig'))
            if not isinstance(data,dict):
                raise ValueError('配置必须是对象')
            source['modified_at'] = path.stat().st_mtime
            self._collect(data)
        except FileNotFoundError:
            source.update(status='missing',error='文件不存在')
            source['version']=source_version(path,b'')
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

    def scrub_message_text(self, value):
        """Redact message secrets without reserializing URLs or changing prose."""
        def redact_url(match):
            url = match[0]
            url = re.sub(r'(^[A-Za-z][A-Za-z0-9+.-]*://)[^/?#]*@', r'\1***@', url)
            def parameter(part):
                return part[1]+part[2]+'='+('***' if sensitive(unquote_plus(part[2])) else part[3])
            return re.sub(r'([?&#])([^?&#=]+)=([^&#]*)', parameter, url)
        value = re.sub(r'''[A-Za-z][A-Za-z0-9+.-]*://[^\s<>"']+''', redact_url, value)
        for secret in sorted(self._secrets,key=len,reverse=True):
            if len(secret)>=4 or value==secret:
                value = value.replace(secret,'***')
        return value

    def read(self):
        self._sources, self._raw, self._secrets = [], {}, set()
        wx = self._load('wxbot','wxbot 配置',self.wxbot_path)
        bt = self._load('butler','Butler 配置',self.butler_path)
        from log.directory_view import load_directory, directory_section, MOVED_WX
        directory=load_directory(self,wx,bt)
        from butler.contact_admin import configured_store
        unified = configured_store(self.butler_path,bt)
        mode=(wx.get('installation') or {}).get('mode','local')
        model = wx.get('model') or {}
        backend = model.get('backend','ollama') if isinstance(model,dict) else 'ollama'
        model_defaults = {'backend':'ollama','max_history':10,'system_prompt':''}
        if backend in ('openai','hermes','responses','openclaw'):
            model_defaults.update(url='http://127.0.0.1:8642/v1/chat/completions',model='hermes-agent',timeout=300,api_key='')
        elif backend=='cursor':
            model_defaults.update(executable='agent',work_dir='data/cursor',model='',api_key='',timeout=600)
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
                default_keys={key for key,value in leaves(merge(WX_DEFAULTS,{'model':model_defaults}) if source=='wxbot' else BT_DEFAULTS)}
                for path,value in paths({group:values}):
                    if directory is not None and ((source=='butler' and path==('contacts',)) or
                        (source=='wxbot' and (path in MOVED_WX or path[:3]==('wechat','group_sender','member_names')))):
                        continue
                    key='.'.join(path)
                    rows.append({'key':source+'.'+key,'value':self.sanitize(value,key),
                                 'origin':'file' if key in raw_keys else 'default',
                                 'sensitive':sensitive(key),**row_metadata(source,path,value,default_available=key in default_keys)})
                    if sensitive(key):
                        rows[-1]['editor']='secret'
                        if not isinstance(value,str):rows[-1]['description']+=' 新值请使用JSON格式；清空会移除此字段。'
                    elif isinstance(value,str) and rows[-1]['value']!=value:
                        rows[-1]['description']+=' 此值包含隐藏内容；修改时请填写完整的新值，不能保存星号占位。'
                sections.append({'id':source+'.'+group,'title':('wxbot' if source=='wxbot' else 'Butler')+' · '+group,
                                 'source_id':source,'source':str(self.wxbot_path if source=='wxbot' else self.butler_path),'rows':rows})
        if directory is not None and not unified:sections.append(directory_section(self,directory))
        if unified:
            self._sources.append({'id':'contacts','title':'统一联系人数据库','path':str(unified.path),
                'status':'ok','version':str(unified.snapshot()['version']),'error':'','modified_at':None,'read_only':True})
            sections.append({'id':'contacts','title':'联系人 · 唯一来源','source_id':'contacts','source':str(unified.path),
                'contacts_href':'/app/?tab=contacts','rows':[{'key':'contacts.source','value':'联系人、监听、角色、心跳与订阅统一在「联系人」维护。',
                'origin':'database','editable':False,'sensitive':False}]})
        sections.append({'id':'wxbot.typing','title':'微信输入与分句（代码固定规则）',
                         'source':str(self.root/'wxbot'/'wechat'/'typing.py'),
                         'rows':[{'key':'wxbot.typing.'+key,'value':value,'origin':'code','sensitive':False} for key,value in
                                 (('input_method','分批剪贴板粘贴'),
                                  ('unicode_keyboard',False),('clipboard_restore','恢复原格式；保留用户期间新复制的内容'),
                                  ('verify_input',True),('split_reply_at','。？！!? / 代码区外换行'),
                                  ('reply_parts_source','Butler 完整生成后一次返回，wxbot 按用户逐句轮转'))]})
        sections.append({'id':'wxbot.failure_policy','title':'发送失败与人工核对（代码固定规则）',
                         'source':str(self.root/'wxbot'/'queue_store.py'),
                         'rows':[{'key':'wxbot.failure_policy.'+key,'value':value,'origin':'code','sensitive':False}
                                 for key,value in (('starts_at','首次发件失败；重试/重启不重置'),
                                     ('states',['blocked','uncertain']),
                                     ('model_max_attempts',MODEL_MAX_ATTEMPTS),
                                     ('model_retry_delays_seconds',list(MODEL_RETRY_DELAYS)),
                                     ('model_unknown_result','不自动重放；失败等待达到 queue.failure_discard_seconds 后结束旧批次并放行后续消息'),
                                     ('manual_actions','收发队列 → 人工核对：重试、确认已发、立即丢弃'))]})
        hermes = bt.get('hermes') or {}
        def resolved_path(value, fallback):
            if value is None or value=='':
                return fallback
            if not isinstance(value,str):
                return None
            if (bt.get('agent') or {}).get('provider') != 'codex':
                return Path(value)
            path = Path(value).expanduser()
            return (path if path.is_absolute() else self.butler_path.resolve().parent/path).resolve()
        home = resolved_path(hermes.get('root'),self.home) if isinstance(hermes,dict) else None
        if (bt.get('agent') or {}).get('provider')=='codex':
            from butler.config import load as load_butler
            home=load_butler(self.butler_path).data_path()
        heartbeat = bt.get('heartbeat') or {}
        groups = bt.get('groups') or {}
        if not isinstance(heartbeat,dict): heartbeat={}
        if not isinstance(groups,dict): groups={}
        policy_path = resolved_path(heartbeat.get('config_file'),home/'cache'/'butler_heartbeat.json' if home else None)
        group_path = resolved_path(groups.get('file'),home/'cache'/'butler_groups.json' if home else None)
        policies = {} if unified else self._load('policies','用户角色 / Skill / 心跳开关',policy_path,kind='json')
        group_data = {} if unified else self._load('groups','用户分组',group_path,kind='json')
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
            if not unified and not same_path(path,other):
                data=self._load(name,title,path,kind='json')
                dynamic_sources.append((name,title,path,data))
                warnings.append(title+'与 Butler 来源不同，已分别列出，请核对服务的 home / 配置路径。')
        for name,title,path,data in (dynamic_sources if mode=='local' and not unified else []):
            if not data:data={'users':{}} if name in {'policies','log_policies'} else {'groups':{}}
            rows=[]
            for key,value in paths(data):
                joined='.'.join(key)
                meta=row_metadata(name,key,value)
                meta['editable']=key[0] not in {'version','updated_at'}
                rows.append({'key':name+'.'+joined,'value':self.sanitize(value,joined),'origin':'file',
                             'sensitive':sensitive(joined),**meta})
                if sensitive(joined):rows[-1]['editor']='secret'
            sections.append({'id':name,'title':title,'source_id':name,
                             'source':str(path) if path else '路径无效，请检查 Butler 配置','rows':rows})
        log_config=self._load('log_config','log 启动配置',self.log_config_path)
        log_rows=[]
        log_default_paths={p for p,v in paths(LOG_DEFAULTS)}
        for key,value in paths(merge(LOG_DEFAULTS,log_config)):
            joined='.'.join(key)
            row={'key':'log_config.'+joined,'value':self.sanitize(value,joined),
                 'origin':'file' if any(p==key for p,v in paths(log_config)) else 'default','sensitive':sensitive(joined),
                 **row_metadata('log_config',key,value,default_available=key in log_default_paths)}
            if row['sensitive']:row['editor']='secret'
            log_rows.append(row)
        sections.append({'id':'log_config','title':'log · 启动配置','source':str(self.log_config_path),'source_id':'log_config','rows':log_rows})
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
        for section in sections:
            source=next((s for s in self._sources if s['id']==section.get('source_id')),None)
            for row in section['rows']:
                row.setdefault('editable',False)
                if unified:
                    keys=tuple(row.get('path',[]));sid=section.get('source_id')
                    if (sid in {'directory','contacts','policies','groups','log_policies','log_groups'} or
                        sid=='butler' and (keys[:1] in {('contacts',),('directory',)} or keys in {('heartbeat','config_file'),('groups','file')}) or
                        sid=='wxbot' and (keys[:1]==('directory',) or keys in MOVED_WX or keys[:3]==('wechat','group_sender','member_names')) or
                        sid=='log_config' and keys==('sources','groups_file')):
                        row['editable']=False
                if source and source['status']=='error':row['editable']=False
        # Run the final whole payload through the scrubber: a secret may also occur in a path or a harmless field.
        payload={'read_only':False,'runtime_verified':False,'at':time.time(),'sources':self._sources,'sections':sections,'warnings':warnings,
                 'connection':{'mode':mode,'business_tools':mode=='local','local_butler':mode=='local'},
                 'note':'按来源文件保存修改；保存不等于运行服务已加载。页面逐项标明生效方式，不自动重启任何服务。密钥原值不会回显。'}
        self._catalog=deepcopy(payload)  # Writer authorization uses server metadata, never scrubbed display strings.
        safe=self.scrub(payload)
        # Schema identifiers are protocol structure. A key coinciding with "timeout" must not rename a field.
        for original,output in zip(payload['sources'],safe['sources']):
            for key in ('id','status','version'):
                if key in original:output[key]=original[key]
        for original,output in zip(sections,safe['sections']):
            for key in ('id','source_id'):
                if key in original:output[key]=original[key]
            for row,shown in zip(original['rows'],output['rows']):
                for key in ('key','path','editor','origin'):
                    if key in row:shown[key]=deepcopy(row[key])
        return safe

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
        path = name if name==':memory:' else str(Path(name) if Path(name).is_absolute() else self.wxbot_path.resolve().parent/name)
        return {'path':path,'quiet':float(queue.get('quiet_seconds',3)),
                'failure_timeout_seconds':queue.get('failure_discard_seconds',FAILURE_TIMEOUT_SECONDS),
                'max_wait':float(queue.get('max_wait_seconds',10)),'prefix':bot.get('command_prefix','/')}

    def flow_options(self):
        queue = self.queue_options()
        bt = self._raw.get('butler') or {}
        log = bt.get('log') or {}
        hermes = bt.get('hermes') or {}
        flow_file = log.get('flow_file') if isinstance(log,dict) else None
        if (bt.get('agent') or {}).get('provider')=='codex':
            from butler.config import load as load_butler
            flow_file=load_butler(self.butler_path).flow_log_path()
        root = hermes.get('root') if isinstance(hermes,dict) else None
        if not flow_file and isinstance(root,str) and root:
            flow_file = str(Path(root)/'cache'/'wxbot.log')
        bt_trace = butler_trace_path(flow_file) if isinstance(flow_file,str) else None
        return {'queue_options':queue,'trace_paths':[queue_trace_path(queue['path']),bt_trace]}
