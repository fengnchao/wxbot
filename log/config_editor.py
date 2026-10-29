"""Validated configuration patches. Browser input never selects a filesystem target."""
from contextlib import contextmanager
from copy import deepcopy
import json
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid

import tomlkit

from log.config_schema import validate_value
from log.config_view import merge,source_version,WX_DEFAULTS,BT_DEFAULTS,sensitive

_LOCK=threading.RLock()
_HIDDEN={'已配置（隐藏）','未配置'}
_RESTART={'wxbot':['wxbot'],'butler':['Butler'],'log_config':['log']}


class ConfigConflict(ValueError):
    """The browser's file version is no longer current."""


def edit_lock_path(path):
    target=Path(path).resolve()
    identity=os.path.normcase(str(target))
    digest=hashlib.sha256(identity.encode('utf-8')).hexdigest()
    return target.parent/'data'/'cache'/'config-locks'/(digest+'.lock')


@contextmanager
def config_lock(path):
    """Serialize dashboard writers, including the existing role/group editors."""
    with _LOCK:
        lockpath=edit_lock_path(path)
        lockpath.parent.mkdir(parents=True,exist_ok=True)
        with lockpath.open('a+b') as fh:
            if fh.tell()==0:fh.write(b'\0');fh.flush()
            fh.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(fh.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(fh,fcntl.LOCK_EX)
            try:yield
            finally:
                fh.seek(0)
                if os.name=='nt':msvcrt.locking(fh.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(fh,fcntl.LOCK_UN)


def _get(data,path,default=None):
    for key in path:
        if not isinstance(data,dict) or key not in data:return default
        data=data[key]
    return data


def _put(data,path,value,delete=False):
    current=data
    for key in path[:-1]:
        if key not in current:current[key]={}
        current=current[key]
    if delete:current.pop(path[-1],None)
    else:current[path[-1]]=value


def _has_hidden(value):
    if isinstance(value,str):return value in _HIDDEN
    if isinstance(value,dict):return any(_has_hidden(v) for v in value.values())
    if isinstance(value,list):return any(_has_hidden(v) for v in value)
    return False


def _old_item(value,old,index,new_names):
    if isinstance(value,dict) and 'name' in value:
        same_name=next((v for v in old if isinstance(v,dict) and v.get('name')==value['name']),None)
        if value.get('uid'):
            matches=[v for v in old if isinstance(v,dict) and v.get('uid')==value['uid']
                     and v.get('profile','default')==value.get('profile','default')]
            if (same_name is not None and len(matches)==1 and matches[0] is not same_name
                    and matches[0].get('name') not in new_names and _has_hidden(value)):
                raise ValueError('联系人合并存在歧义，无法确定保留哪个隐藏值；请明确填写新的会话模板')
            if same_name is None and len(matches)==1:return matches[0]
        return same_name
    return old[index] if index<len(old) else None


def _restore_hidden(value,old,key=''):
    if sensitive(key) and isinstance(value,str) and value in _HIDDEN:
        if old is None:raise ValueError('新增项目不能使用隐藏状态作为密钥')
        return old
    if isinstance(value,dict):
        return {k:_restore_hidden(v,old.get(k) if isinstance(old,dict) else None,k) for k,v in value.items()}
    if isinstance(value,list):
        old=old if isinstance(old,list) else []
        names={v.get('name') for v in value if isinstance(v,dict) and isinstance(v.get('name'),str)}
        return [_restore_hidden(v,_old_item(v,old,i,names)) for i,v in enumerate(value)]
    return value


def _restore_redacted(value,old,view):
    if isinstance(value,str) and isinstance(old,str):
        masked=view._text(old)
        if masked!=old:
            if value==masked:return old
            if '***' in value or '%2a' in value.lower():
                raise ValueError('此配置含隐藏内容；请填写完整的新值，或将凭据配置在独立密钥项中')
    elif isinstance(value,dict) and isinstance(old,dict):
        return {k:_restore_redacted(v,old.get(k),view) for k,v in value.items()}
    elif isinstance(value,list) and isinstance(old,list):
        names={v.get('name') for v in value if isinstance(v,dict) and isinstance(v.get('name'),str)}
        return [_restore_redacted(v,_old_item(v,old,i,names),view) for i,v in enumerate(value)]
    return value


def validate_document(source,data,view,changes,policy_validator=None):
    if source=='wxbot':
        from wxbot.config import validate_runtime_config,validate_model_concurrency
        cfg=merge(WX_DEFAULTS,data)
        validate_runtime_config(cfg)
        validate_model_concurrency(cfg['queue']['max_model_requests'])
        bot=cfg['bot'];q=cfg['queue']
        if bot['reply_delay_max']<bot['reply_delay_min']:raise ValueError('最长回复等待不得小于最短等待')
        if set(bot['bound_users']) & set(bot['bound_groups']):raise ValueError('私聊与群聊绑定不能重叠')
        if bot['bound_groups'] and not bot['mention_names']:raise ValueError('绑定群聊时必须配置机器人群昵称')
        if cfg['wechat']['mode']=='independent' and not (bot['bound_users'] or bot['bound_groups']):
            raise ValueError('独立窗口模式需要绑定用户或群聊')
        if q['max_wait_seconds']<=0 or q['confirm_timeout']<=0:raise ValueError('合并及发送确认等待必须大于0')
    elif source=='butler':
        cfg=merge(BT_DEFAULTS,data)
        context=cfg['context']
        for key,high in (('group_messages',200),('group_characters',30000)):
            if type(context[key])is not int or not 1<=context[key]<=high:
                raise ValueError('群上下文配置超出允许范围')
        from butler.reply import validate_chunk_chars
        validate_chunk_chars(cfg['reply']['chunk_chars'])
        hb=cfg['heartbeat']
        if hb['max_interval_minutes']<hb['min_interval_minutes']:raise ValueError('心跳最长间隔不得小于最短间隔')
        contacts=cfg['contacts']
        if not isinstance(contacts,list):raise ValueError('联系人必须是JSON数组')
        names=set()
        for contact in contacts:
            if not isinstance(contact,dict):raise ValueError('联系人格式无效')
            name=contact.get('name');uid=contact.get('uid') or name
            if not isinstance(name,str) or not name.strip() or name!=name.strip() or name in names:raise ValueError('联系人名称须非空、无首尾空格且唯一')
            names.add(name)
            if not isinstance(uid,str) or not uid.isascii() or not uid.strip() or any(c in uid for c in '\r\n'):
                raise ValueError('联系人uid必须是非空ASCII文本')
            for key,value in contact.items():
                if not isinstance(value,str):raise ValueError('联系人字段必须是文本')
            if 'session_key' in contact:
                try:contact['session_key'].format(name=name,uid=uid,profile=contact.get('profile','default'),channel_type='dm')
                except (ValueError,KeyError,IndexError,AttributeError):raise ValueError('联系人session_key模板无效') from None
    elif source in {'policies','log_policies'}:
        users=data.get('users')
        if not isinstance(users,dict):raise ValueError('角色心跳配置必须包含users对象')
        known={c.get('name') for c in view._raw.get('butler',{}).get('contacts',[]) if isinstance(c,dict)}
        for name,policy in users.items():
            if name not in known:raise ValueError('角色心跳策略包含未配置的联系人')
            if (not isinstance(policy,dict) or not isinstance(policy.get('role_skill'),str) or not policy['role_skill'].strip()
                    or not isinstance(policy.get('allowed_skills'),list) or
                    any(not isinstance(s,str) or not s.strip() for s in policy['allowed_skills']) or
                    type(policy.get('heartbeat_enabled')) is not bool):raise ValueError('角色心跳策略格式无效')
        old=view._raw.get(source,{}).get('users',{})
        changed=[name for name,p in users.items() if any(p.get(k)!=old.get(name,{}).get(k) for k in ('role_skill','allowed_skills'))]
        if changed:
            if policy_validator is None:raise ValueError('角色与工具变更需要验证Hermes技能目录，请通过log服务保存')
            policy_validator(users,changed,view._raw.get('butler',{}))
    elif source in {'groups','log_groups'}:
        groups=data.get('groups',data)
        if not isinstance(groups,dict):raise ValueError('分组必须是JSON对象')
        for key,users in groups.items():
            if not str(key).isdigit() or int(key)<=0 or not isinstance(users,list) or any(not isinstance(u,str) or not u.strip() or len(u)>64 for u in users):
                raise ValueError('分组编号须为正整数，成员须为非空名称列表')


class ConfigEditor:
    def __init__(self,view,*,policy_validator=None):
        self.view,self.policy_validator=view,policy_validator

    def save(self,payload):
        if not isinstance(payload,dict) or payload.get('acknowledge') is not True:raise ValueError('请确认配置修改')
        source=payload.get('source');version=payload.get('version');changes=payload.get('changes')
        if not isinstance(source,str) or not isinstance(version,str) or not isinstance(changes,list) or not 1<=len(changes)<=200:
            raise ValueError('配置修改请求格式无效')
        if source=='directory':
            from log.directory_view import save_directory
            return save_directory(self.view,payload)
        self.view.read()
        entry=next((s for s in self.view._sources if s['id']==source),None)
        if entry is None or entry['status']=='error' or not entry.get('path'):raise ValueError('配置来源不可编辑')
        path=Path(entry['path'])
        with config_lock(path):
            self.view.read()
            catalog=self.view._catalog
            entry=next(s for s in self.view._sources if s['id']==source)
            if entry.get('version')!=version:raise ConfigConflict('配置文件已变化，请刷新后重新核对')
            rows={tuple(row['path']):row for section in catalog['sections'] if section.get('source_id')==source
                  for row in section['rows'] if row.get('editable') and 'path' in row}
            old=path.read_bytes() if path.exists() else b''
            if source_version(path,old)!=version:raise ConfigConflict('配置文件已更新，请刷新后重新核对')
            plain=deepcopy(self.view._raw[source])
            json_source=source in {'policies','log_policies','groups','log_groups'}
            document=deepcopy(plain) if json_source else tomlkit.parse(old.decode('utf-8-sig'))
            seen=set()
            for change in changes:
                if not isinstance(change,dict) or not isinstance(change.get('path'),list) or not change['path'] or any(not isinstance(k,str) for k in change['path']):
                    raise ValueError('配置字段路径无效')
                keys=tuple(change['path']);row=rows.get(keys)
                if row is None or keys in seen:raise ValueError('配置字段不可编辑或重复')
                seen.add(keys)
                op=change.get('op')
                if op=='default':
                    if not row.get('default_available'):raise ValueError('此字段没有默认值')
                    _put(document,keys,None,delete=True);_put(plain,keys,None,delete=True)
                    continue
                if op not in {'set','clear'} or (op=='clear' and not row['sensitive']):raise ValueError('配置操作无效')
                value='' if op=='clear' else change.get('value')
                if row['sensitive'] and op=='set' and (not isinstance(value,str) or not value or value in _HIDDEN):
                    raise ValueError('请填入新密钥，或明确选择清空')
                reference=_get(self.view._raw[source],keys,row['value'])
                if row['sensitive'] and not isinstance(reference,str):
                    if op=='clear':
                        _put(document,keys,None,delete=True);_put(plain,keys,None,delete=True)
                        continue
                    if isinstance(value,str):
                        try:value=json.loads(value)
                        except ValueError:raise ValueError('此密钥配置需要JSON格式的新值') from None
                validate_value(keys,value,reference)
                value=_restore_hidden(value,reference)
                if not row['sensitive']:value=_restore_redacted(value,reference,self.view)
                _put(document,keys,value);_put(plain,keys,value)
            validate_document(source,plain,self.view,changes,self.policy_validator)
            text=json.dumps(document,ensure_ascii=False,indent=2)+'\n' if json_source else tomlkit.dumps(document)
            encoded=text.encode('utf-8-sig' if old.startswith(b'\xef\xbb\xbf') else 'utf-8')
            if encoded==old:return {'ok':True,'restart':[],'message':'配置没有变化','backup':''}
            backup=None
            if path.exists():
                backup=path.with_name(path.name+'.config-backup-'+str(time.time_ns())+'-'+uuid.uuid4().hex[:8])
                with backup.open('xb') as fh:fh.write(old);fh.flush();os.fsync(fh.fileno())
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(prefix='.'+path.name+'-',suffix='.tmp',dir=path.parent,delete=False) as fh:
                    temporary=Path(fh.name);fh.write(encoded);fh.flush();os.fsync(fh.fileno())
                current=path.read_bytes() if path.exists() else b''
                if source_version(path,current)!=version:raise ConfigConflict('配置文件已变化，本次未覆盖；请刷新')
                os.replace(temporary,path)
            finally:
                if temporary is not None and temporary.exists():temporary.unlink()
            self.view.read()  # Subsequent derived paths/timeouts and scrubbing use the saved values.
            return {'ok':True,'restart':_RESTART.get(source,[]),'message':'配置已保存；请按页面提示自行重启对应服务' if source in _RESTART else '配置已保存，后续读取生效',
                    'backup':str(backup) if backup else ''}
