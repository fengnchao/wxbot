"""Dashboard projection and versioned edits through Butler's directory service."""
from copy import deepcopy
from pathlib import Path

from butler.directory import DirectoryStore, directory_path, directory_enabled
from log.config_schema import row_metadata, validate_value


DIRECTORY_FIELDS = {('contacts',), ('channel','bot','bound_users'), ('channel','bot','bound_groups'),
                    ('channel','bot','mention_names'), ('channel','wechat','main_window','listen_all'), ('aliases',), ('entries',)}
MOVED_WX = {('bot','bound_users'),('bot','bound_groups'),('bot','mention_names'),
            ('wechat','main_window','listen_all')}


def load_directory(view, wx, bt):
    if not directory_enabled(view.wxbot_path, wx): return None
    path=directory_path(view.wxbot_path,wx)
    if path!=directory_path(view.butler_path,bt): raise ValueError('Butler 和 wxbot 用户目录路径不一致')
    state=DirectoryStore(path).snapshot()
    public=deepcopy(state)
    for alias in public['aliases']:alias.pop('member_key',None)
    view._collect(public)
    view._raw['directory']=deepcopy(state)
    view._sources.append({'id':'directory','title':'共享用户与通道目录','path':str(path),'status':'ok',
                          'version':str(state['version']),'error':'','modified_at':None})
    bt['contacts']=deepcopy(state['contacts'])
    for group,values in state['channel'].items():
        if group=='bot': wx.setdefault('bot',{}).update(deepcopy(values))
        elif group=='wechat':wx.setdefault('wechat',{}).setdefault('main_window',{}).update(deepcopy(values.get('main_window',{})))
    return state


def contact_entries(state):
    rows={c['name']:deepcopy(c) for c in state['contacts']}
    bot=state.get('channel',{}).get('bot',{})
    users,groups=bot.get('bound_users',[]),bot.get('bound_groups',[])
    for name in [*users,*groups]:rows.setdefault(name,{'name':name})
    for name,row in rows.items():
        row.setdefault('uid',name);row.setdefault('profile','default');row.setdefault('label','')
        row['channel_type']='group' if name in groups else 'dm' if name in users else row.get('channel_type','dm')
        row['listening']=name in users or name in groups
    return list(rows.values())


def set_contact_entries(state,entries):
    if not isinstance(entries,list):raise ValueError('联系人必须是列表')
    contacts,users,groups=[],[],[]
    for entry in entries:
        if not isinstance(entry,dict) or type(entry.get('listening')) is not bool:raise ValueError('联系人监听开关必须是布尔值')
        row=deepcopy(entry);listening=row.pop('listening');name=row.get('name')
        if not isinstance(name,str) or not name.strip() or name!=name.strip():raise ValueError('联系人名称不能为空或带首尾空格')
        kind=row.get('channel_type','dm')
        if kind not in {'dm','group'}:raise ValueError('联系人类型必须是私聊或群聊')
        contacts.append(row)
        if listening:(groups if kind=='group' else users).append(name)
    state['contacts']=contacts
    state['channel'].setdefault('bot',{}).update(bound_users=users,bound_groups=groups)


def directory_section(view, state):
    definitions=[(('entries',),contact_entries(state),'directory-contacts','联系人与监听','在同一列表维护联系人、会话类型和监听开关；路由信息随该联系人保存。'),
                 (('aliases',),state['aliases'],'alias-list','群昵称与待核对别名','按群维护成员昵称，可补充所属群、修改昵称和标记待核对。昵称显示不等于确认身份。'),
                 (('channel','bot','mention_names'),state['channel'].get('bot',{}).get('mention_names',[]),None,None,None),
                 (('channel','wechat','main_window','listen_all'),state['channel'].get('wechat',{}).get('main_window',{}).get('listen_all',True),None,None,None)]
    rows=[]
    for keys,value,widget,label,description in definitions:
        meta=row_metadata('directory',keys,value)
        meta.update(effect='保存后供后续收件使用；独立窗口模式需重启 wxbot',default_available=False)
        if widget:meta.update(widget=widget,editor='json',label=label,description=description)
        shown=view.sanitize(value,'.'.join(keys))
        if keys==('aliases',):
            shown=[{k:view._text(v) if k=='member_key' else view.sanitize(v,k) for k,v in row.items()} for row in value]
        rows.append({'key':'directory.'+'.'.join(keys),'value':shown,'origin':'database','sensitive':False,**meta})
    source=next(s for s in view._sources if s['id']=='directory')
    return {'id':'directory','title':'联系人设置','source_id':'directory','source':source['path'],'rows':rows}


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
        if keys==('entries',) and seen & {('contacts',),('channel','bot','bound_users'),('channel','bot','bound_groups')}:raise ValueError('请通过同一联系人列表保存监听与路由')
        if keys in {('contacts',),('channel','bot','bound_users'),('channel','bot','bound_groups')} and ('entries',) in seen:raise ValueError('请通过同一联系人列表保存监听与路由')
        reference=contact_entries(state) if keys==('entries',) else _get(state,keys)
        value=change.get('value')
        validate_value(keys,value,reference)
        value=_restore_hidden(value,reference)
        value=_restore_redacted(value,reference,view)
        if keys==('entries',):set_contact_entries(state,value)
        else:_put(state,keys,value)
    bot=state['channel'].get('bot',{})
    if bot.get('bound_groups') and not bot.get('mention_names'):raise ValueError('监听群聊需要机器人微信昵称')
    if view._raw['wxbot'].get('wechat',{}).get('mode','main')=='independent' and not (bot.get('bound_groups') or bot.get('bound_users')):
        raise ValueError('独立窗口模式需要监听名单')
    try: saved=DirectoryStore(source['path']).save(state, int(payload['version']))
    except ValueError as exc:
        if 'version conflict' in str(exc):raise ConfigConflict('用户目录已变化，请刷新后重新核对') from None
        raise
    return {'ok':True,'version':str(saved['version']),'restart':[], 'backup':'', 'message':'已保存到共享用户目录'}
