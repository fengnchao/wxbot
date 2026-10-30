"""Authoritative local conversations and contact settings, owned by Butler."""
from contextlib import contextmanager, closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import uuid


_FIELDS=('conversations','settings','aliases','person_policies')
_ROUTE_FIELDS=('name','channel_type','uid','profile','label','session_key')


def is_unified(path):
    if not path or not Path(path).exists():return False
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='unified_contacts'").fetchone():return False
        row=db.execute('SELECT active FROM unified_contacts WHERE id=1').fetchone()
        return bool(row and row[0])


def from_config(cfg):
    path=getattr(cfg,'contact_database','') or getattr(getattr(cfg,'contacts',None),'path','')
    return ContactStore(path) if path and is_unified(path) else None


def clean_policy(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('invalid contact policy')
    role=value.get('role_skill');allowed=value.get('allowed_skills');enabled=value.get('heartbeat_enabled')
    if not isinstance(role,str) or not role.strip() or not isinstance(allowed,list) or type(enabled) is not bool:
        raise ValueError('invalid contact role/skills/heartbeat')
    if any(not isinstance(v,str) or not v.strip() for v in allowed):raise ValueError('invalid allowed skills')
    return dict(role_skill=role.strip(),allowed_skills=sorted(set(v.strip() for v in allowed)-{role.strip()}),heartbeat_enabled=enabled)


class ContactStore:
    def __init__(self,path):
        self.path=Path(path).resolve();self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS unified_contacts(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,payload TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 0)')
            db.execute('INSERT OR IGNORE INTO unified_contacts VALUES(1,0,?,0)',
                (json.dumps(dict(conversations=[],settings={},aliases=[],person_policies={})),))

    @contextmanager
    def transaction(self):
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()

    @staticmethod
    def _snapshot(db):
        row=db.execute('SELECT version,payload FROM unified_contacts WHERE id=1').fetchone()
        return dict(json.loads(row['payload']),version=row['version'])

    def snapshot(self):
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=30)) as db:
            db.row_factory=sqlite3.Row;return self._snapshot(db)

    @staticmethod
    def _validated(state):
        value={key:deepcopy(state.get(key,[] if key in ('conversations','aliases') else {})) for key in _FIELDS}
        if not isinstance(value['conversations'],list) or not isinstance(value['settings'],dict) or not isinstance(value['aliases'],list) or not isinstance(value['person_policies'],dict):
            raise ValueError('invalid unified contact state')
        settings=value['settings']
        if set(settings)-{'bot','wechat'}:raise ValueError('invalid global contact settings')
        bot=settings.setdefault('bot',{})
        if not isinstance(bot,dict):raise ValueError('invalid bot settings')
        # Listening names are projections only, never another stored source.
        bot.pop('bound_users',None);bot.pop('bound_groups',None)
        if set(bot)-{'mention_names'}:raise ValueError('invalid bot settings')
        mentions=bot.setdefault('mention_names',[])
        if not isinstance(mentions,list) or any(not isinstance(n,str) or not n.strip() for n in mentions):raise ValueError('invalid mention names')
        wechat=settings.setdefault('wechat',{})
        if not isinstance(wechat,dict) or set(wechat)-{'main_window'}:raise ValueError('invalid WeChat settings')
        main=wechat.setdefault('main_window',{})
        if not isinstance(main,dict) or set(main)-{'listen_all'}:raise ValueError('invalid listening settings')
        if 'listen_all' in main and type(main['listen_all']) is not bool:raise ValueError('listen_all must be boolean')
        ids,names=set(),set()
        for c in value['conversations']:
            if not isinstance(c,dict):raise ValueError('invalid conversation')
            for key in ('id','name'):
                if not isinstance(c.get(key),str) or not c[key].strip():raise ValueError('conversation id/name required')
            if c['id'] in ids or c['name'] in names:raise ValueError('duplicate conversation id/name')
            ids.add(c['id']);names.add(c['name'])
            if c.get('channel_type','dm') not in {'dm','group'}:raise ValueError('invalid channel type')
            c.setdefault('channel_type','dm')
            for key,default in [('uid',c['name']),('profile','default'),('label',''),('session_key',''),('person_id','')]:
                c.setdefault(key,default)
                if not isinstance(c[key],str):raise ValueError('invalid route field '+key)
            for key,default in [('listening',False),('enabled',True)]:
                c.setdefault(key,default)
                if type(c[key]) is not bool:raise ValueError('invalid conversation '+key)
            if c['session_key']:
                try:c['session_key'].format(**{k:c[k] for k in ('name','uid','profile','channel_type')})
                except (ValueError,KeyError,IndexError,AttributeError):raise ValueError('invalid session key') from None
            if 'inherit_person_policy' in c and type(c['inherit_person_policy']) is not bool:raise ValueError('invalid policy inheritance')
            c['policy']=clean_policy(c.get('policy'))
            subscriptions=c.setdefault('subscriptions',[])
            if not isinstance(subscriptions,list) or any(type(n) is not int or n<1 for n in subscriptions):raise ValueError('invalid subscriptions')
            c['subscriptions']=sorted(set(subscriptions))
        if not mentions and any(c['enabled'] and c['listening'] and c['channel_type']=='group' for c in value['conversations']):
            raise ValueError('监听群聊需要配置机器人群昵称 (mention_names)')
        for person,policy in list(value['person_policies'].items()):
            if not isinstance(person,str) or not person:raise ValueError('invalid person policy owner')
            value['person_policies'][person]=clean_policy(policy)
        alias_keys=set()
        for alias in value['aliases']:
            if not isinstance(alias,dict) or any(not isinstance(alias.get(k),str) for k in ('group','member_key','name','source')):
                raise ValueError('invalid member alias')
            if not alias['member_key'].strip() or not alias['name'].strip():raise ValueError('成员标识和昵称不能为空')
            key=(alias['group'],alias['member_key'],alias['source'])
            if key in alias_keys:raise ValueError('duplicate member alias')
            alias_keys.add(key)
            if type(alias.get('pending')) is not bool or alias['source'] not in {'manual','learned','legacy'}:raise ValueError('invalid member alias source')
            if not alias['group'] and not alias['pending']:raise ValueError('unscoped alias must remain pending')
        return value

    @classmethod
    def _save(cls,db,state,expected_version,activate=False):
        old=cls._snapshot(db)
        if type(expected_version) is not int or old['version']!=expected_version:raise ValueError('contact version conflict; reload before saving')
        merged={key:state.get(key,old[key]) for key in _FIELDS}
        value=cls._validated(merged)
        db.execute('UPDATE unified_contacts SET version=version+1,payload=?,active=CASE WHEN ? THEN 1 ELSE active END WHERE id=1',
            (json.dumps(value,ensure_ascii=False),int(activate)))
        return cls._snapshot(db)

    def save(self,state,expected_version):
        with self.transaction() as db:return self._save(db,state,expected_version)

    def activate(self,state,expected_version=0):
        with self.transaction() as db:return self._save(db,state,expected_version,activate=True)

    @staticmethod
    def _route_rows(state):
        return [{key:c[key] for key in _ROUTE_FIELDS} for c in state['conversations'] if c.get('enabled',True)]

    def contact_rows(self):return self._route_rows(self.snapshot())

    @staticmethod
    def _channel(state):
        channel=deepcopy(state['settings']);bot=channel.setdefault('bot',{})
        bot['bound_users']=[c['name'] for c in state['conversations'] if c['enabled'] and c['listening'] and c['channel_type']=='dm']
        bot['bound_groups']=[c['name'] for c in state['conversations'] if c['enabled'] and c['listening'] and c['channel_type']=='group']
        return channel

    def channel_projection(self):return self._channel(self.snapshot())

    @staticmethod
    def _policies(state):
        result={}
        for c in state['conversations']:
            policy=c.get('policy')
            if policy is None and c.get('inherit_person_policy',True):policy=state['person_policies'].get(c.get('person_id'))
            if c['enabled'] and policy:result[c['name']]=deepcopy(policy)
        return result

    def policies(self):return self._policies(self.snapshot())

    def set_policy(self,name,policy):
        with self.transaction() as db:
            state=self._snapshot(db);c=next((c for c in state['conversations'] if c['name']==name),None)
            if c is None:raise ValueError('unknown contact conversation')
            c['policy']=clean_policy(policy);self._save(db,state,state['version']);return deepcopy(c['policy'])

    def groups(self):
        groups={}
        for c in self.snapshot()['conversations']:
            if c['enabled']:
                for kind in c['subscriptions']:groups.setdefault(str(kind),[]).append(c['name'])
        return groups

    def set_groups(self,groups):
        if not isinstance(groups,dict):raise ValueError('groups must be an object')
        with self.transaction() as db:
            state=self._snapshot(db);by_name={c['name']:c for c in state['conversations']}
            for c in by_name.values():c['subscriptions']=[]
            for kind,names in groups.items():
                if not str(kind).isdigit() or int(kind)<1 or not isinstance(names,list):raise ValueError('invalid subscription group')
                for name in names:
                    if name not in by_name:raise ValueError('unknown subscriber conversation')
                    by_name[name]['subscriptions'].append(int(kind))
            self._save(db,state,state['version'])
        return self.groups()

    def directory_snapshot(self):
        state=self.snapshot()
        return dict(contacts=self._route_rows(state),channel=self._channel(state),aliases=state['aliases'],version=state['version'])

    def save_directory(self,payload,expected_version):
        with self.transaction() as db:
            state=self._snapshot(db);by_name={c['name']:c for c in state['conversations']}
            contacts=payload.get('contacts',self.contact_rows());channel=payload.get('channel',self.channel_projection())
            names=set();bot=channel.get('bot',{})
            users=bot.get('bound_users',[]);groups=bot.get('bound_groups',[])
            if set(users)&set(groups):raise ValueError('contact cannot be both dm and group')
            for route in contacts:
                name=route.get('name','');names.add(name)
                c=by_name.get(name) or dict(id=uuid.uuid4().hex,name=name,person_id='',policy=None,subscriptions=[],enabled=True)
                c.update({key:route[key] for key in _ROUTE_FIELDS if key in route})
                c['listening']=name in users or name in groups
                c['channel_type']='group' if name in groups else c.get('channel_type','dm')
                by_name[name]=c
            for name in set(users)|set(groups):
                if name not in by_name:by_name[name]=dict(id=uuid.uuid4().hex,name=name,channel_type='group' if name in groups else 'dm',enabled=True,listening=True)
                else:by_name[name]['listening']=True
            for name,c in by_name.items():
                if name not in names and name not in users and name not in groups:c['enabled']=False;c['listening']=False
            state.update(conversations=list(by_name.values()),settings=deepcopy(channel),aliases=payload.get('aliases',state['aliases']))
            saved=self._save(db,state,expected_version)
        return self.directory_snapshot()

    def member_name(self,group,member_key):
        rows=[a for a in self.snapshot()['aliases'] if a['group']==group and a['member_key']==member_key and not a['pending']]
        rows.sort(key=lambda a:a['source']!='manual');return rows[0]['name'] if rows else ''

    def observe_member(self,group,member_key,name):
        if not group or not member_key or not name:return
        with self.transaction() as db:
            state=self._snapshot(db)
            row=next((a for a in state['aliases'] if a['group']==group and a['member_key']==member_key and a['source']=='learned'),None)
            if row and row['name']==name:return
            if row:row['name']=name
            else:state['aliases'].append(dict(group=group,member_key=member_key,name=name,source='learned',pending=False))
            self._save(db,state,state['version'])
