"""Dashboard projection and versioned edits through Butler's directory service."""
from copy import deepcopy
from pathlib import Path

from butler.directory import DirectoryStore, directory_path, directory_enabled
from log.config_schema import row_metadata, validate_value


DIRECTORY_FIELDS = {('contacts',), ('channel','bot','bound_users'), ('channel','bot','bound_groups'),
                    ('channel','bot','mention_names'), ('channel','wechat','main_window','listen_all'), ('aliases',)}
MOVED_WX = {('bot','bound_users'),('bot','bound_groups'),('bot','mention_names'),
            ('wechat','main_window','listen_all')}


def load_directory(view, wx, bt):
    if not directory_enabled(view.wxbot_path, wx): return None
    path=directory_path(view.wxbot_path,wx)
    if path!=directory_path(view.butler_path,bt): raise ValueError('Butler 和 wxbot 用户目录路径不一致')
    state=DirectoryStore(path).snapshot()
    view._collect(state)
    view._raw['directory']=deepcopy(state)
    view._sources.append({'id':'directory','title':'共享用户与通道目录','path':str(path),'status':'ok',
                          'version':str(state['version']),'error':'','modified_at':None})
    bt['contacts']=deepcopy(state['contacts'])
    for group,values in state['channel'].items():
        if group=='bot': wx.setdefault('bot',{}).update(deepcopy(values))
        elif group=='wechat':wx.setdefault('wechat',{}).setdefault('main_window',{}).update(deepcopy(values.get('main_window',{})))
    return state


def directory_section(view, state):
    def value_at(keys):
        value=state
        for key in keys:value=value.get(key,{})
        return value
    rows=[]
    for keys in sorted(DIRECTORY_FIELDS):
        value=value_at(keys)
        meta=row_metadata('directory',keys,value)
        meta.update(effect='保存至共享数据库；主窗口后续收件/查询生效，独立窗口模式需重启 wxbot',default_available=False)
        if keys==('contacts',):meta.update(widget='contacts',label='Butler 联系人路由',description='保留旧 uid/Profile/会话键；这里的监听设置不会授予身份或工具权限。')
        if keys==('aliases',):meta.update(widget='json',editor='json',label='群昵称与待核对别名',description='每项 group / member_key / name / source / pending。旧别名填写所属群后可设 pending=false；仅用于显示，不确认身份。')
        rows.append({'key':'directory.'+'.'.join(keys),'value':view.sanitize(value,'.'.join(keys)),
                     'origin':'database','sensitive':False,**meta})
    source=next(s for s in view._sources if s['id']=='directory')
    return {'id':'directory','title':'共享用户目录 · 监听与昵称','source_id':'directory','source':source['path'],'rows':rows}


def save_directory(view, payload):
    from log.config_editor import ConfigConflict, _get, _put, _restore_hidden, _restore_redacted
    view.read()
    source=next((s for s in view._sources if s['id']=='directory'),None)
    if source is None:raise ValueError('共享目录尚未迁移，请先运行 python -m butler migrate')
    if payload['version']!=source['version']:raise ConfigConflict('用户目录已变化，请刷新后重新核对')
    state=deepcopy(view._raw['directory'])
    seen=set()
    for change in payload['changes']:
        keys=change.get('path') if isinstance(change,dict) else None
        if not isinstance(keys,list) or any(not isinstance(k,str) for k in keys):raise ValueError('目录字段无效')
        keys=tuple(keys)
        if keys not in DIRECTORY_FIELDS or keys in seen or change.get('op')!='set':raise ValueError('目录字段不可编辑或重复')
        seen.add(keys)
        reference=_get(state,keys)
        value=change.get('value')
        validate_value(keys,value,reference)
        value=_restore_hidden(value,reference)
        value=_restore_redacted(value,reference,view)
        _put(state,keys,value)
    bot=state['channel'].get('bot',{})
    if bot.get('bound_groups') and not bot.get('mention_names'):raise ValueError('监听群聊需要机器人微信昵称')
    if view._raw['wxbot'].get('wechat',{}).get('mode','main')=='independent' and not (bot.get('bound_groups') or bot.get('bound_users')):
        raise ValueError('独立窗口模式需要监听名单')
    try: saved=DirectoryStore(source['path']).save(state, int(payload['version']))
    except ValueError as exc:
        if 'version conflict' in str(exc):raise ConfigConflict('用户目录已变化，请刷新后重新核对') from None
        raise
    return {'ok':True,'version':str(saved['version']),'restart':[], 'backup':'', 'message':'已保存到共享用户目录'}
