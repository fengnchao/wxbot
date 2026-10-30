"""Business-facing unified contact management. Paths come from server config only."""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
import uuid
import json

from butler.identity.contact_store import ContactStore, clean_policy, is_unified


def configured_store(config_path, raw=None):
    """Return the active canonical store without activating or importing anything."""
    from butler.identity.directory import directory_path
    path = directory_path(config_path, raw)
    return ContactStore(path) if is_unified(path) else None


class ContactAdmin:
    def __init__(self, path, *, policy_validator=None):
        self.path = Path(path).resolve()
        self.policy_validator = policy_validator

    def read(self, *, id='', query='', kind=''):
        if not is_unified(self.path):
            return {'active': False, 'version': 0, 'rows': [], 'total': 0,
                    'guidance': '先运行 python -m butler contacts-preview，只读核对后停止旧服务，再执行 contacts-migrate --acknowledge-stopped。'}
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            state = ContactStore._snapshot(db)
            rows = self._rows(db, state)
        if query:
            needle = query.casefold()
            rows = [r for r in rows if needle in str(r).casefold()]
        if kind:
            rows = [r for r in rows if (r['kind'] == kind or
                    kind == 'dm' and r['kind'] == 'person' and any(c['channel_type']=='dm' for c in r['conversations']) or
                    kind == 'disabled' and not r['enabled'] or
                    kind == 'pending' and (not r['conversations'] or any(c.get('needs_route') for c in r['conversations']) or any(not m.get('identity_confirmed',1) for m in r['memberships'])))]
        result = {'active': True, 'version': state['version'], 'rows': rows, 'total': len(rows),
                  'settings': state['settings'], 'aliases':state['aliases']}
        if id:
            row = next((r for r in rows if r['id'] == id), None)
            if row is None: raise ValueError('联系人不存在，请刷新列表')
            result['row'] = row
        return result

    def memory(self, person_id):
        data=self.read(id=person_id)
        if not data['active']:raise ValueError('联系人尚未迁移')
        row=data['row']
        if row['kind']!='person':raise ValueError('只有联系人有个人记忆')
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as db:
            db.row_factory=sqlite3.Row
            person=db.execute('SELECT * FROM user_profiles WHERE user_id=?',(person_id,)).fetchone()
            if person is None:raise ValueError('此目的地尚无个人档案')
            items=[dict(r) for r in db.execute('SELECT key,value,updated FROM memory WHERE owner=? ORDER BY key',('user:'+person_id,))]
            conflicts=row.get('memory_conflicts',[])
            keys={r['key'] for r in conflicts}
            items=[r for r in items if r['key'] not in keys]+conflicts
            return {'contact_id':person_id,'version':person['memory_version'],'items':items,
                'binding':dict(next(iter(row['bindings']),{}),user_id=person_id,nickname=person['display_name'],
                    contact=person['display_name'],channel_type='dm',memory_owner='user:'+person_id,binding_id='person:'+person_id)}

    def audit(self,person_id,offset=0,limit=20):
        self.memory(person_id)
        offset=max(0,int(offset));limit=min(100,max(1,int(limit)))
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as db:
            db.row_factory=sqlite3.Row
            where='WHERE binding_id IN (SELECT binding_id FROM user_bindings WHERE user_id=?) OR binding_id=?'
            args=(person_id,'person:'+person_id)
            total=db.execute('SELECT COUNT(*) FROM user_audit '+where,args).fetchone()[0]
            rows=[dict(r) for r in db.execute('SELECT * FROM user_audit '+where+' ORDER BY id DESC LIMIT ? OFFSET ?',(*args,limit,offset))]
            for row in rows:row['details']=json.loads(row['details'])
            return {'rows':rows,'total':total,'offset':offset,'limit':limit}

    @staticmethod
    def _rows(db, state):
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        profiles = list(db.execute('SELECT * FROM user_profiles ORDER BY display_name,user_id')) if 'user_profiles' in tables else []
        if 'user_redirects' in tables:
            retired = {r[0] for r in db.execute('SELECT old_user_id FROM user_redirects')}
            profiles = [p for p in profiles if p['user_id'] not in retired]
        bindings = [dict(r) for r in db.execute('SELECT * FROM user_bindings ORDER BY contact,nickname,binding_id')] if 'user_bindings' in tables else []
        if 'user_binding_names' in tables:
            names = dict(db.execute('SELECT binding_id,nickname FROM user_binding_names'))
            for binding in bindings:binding['nickname']=names.get(binding['binding_id'],binding['nickname'])
        rows = []
        for p in profiles:
            related = [b for b in bindings if b['user_id'] == p['user_id']]
            conversations = [deepcopy(c) for c in state['conversations'] if c.get('person_id')==p['user_id']]
            count = db.execute('SELECT COUNT(*) FROM memory WHERE owner=?', ('user:'+p['user_id'],)).fetchone()[0] if 'memory' in tables else 0
            for b in related:
                b['memory_owner'] = 'user:'+p['user_id']
            row = {'id':p['user_id'],'kind':'person','name':p['display_name'],
                   'enabled':any(bool(b['enabled']) for b in related) if related else any(c['enabled'] for c in conversations),
                   'conversations':conversations,'memberships':[b for b in related if b['channel_type']=='group'],
                   'bindings':related,'memory_count':count,'policy':state['person_policies'].get(p['user_id'])}
            if 'user_name_history' in tables:
                row['historical_names']=[r[0] for r in db.execute('SELECT name FROM user_name_history WHERE user_id=? ORDER BY name',(p['user_id'],))]
            if related and 'user_avatars' in tables:
                picture=db.execute('SELECT image FROM user_avatars WHERE binding_id IN (SELECT binding_id FROM user_bindings WHERE user_id=?) ORDER BY created_at DESC LIMIT 1',(p['user_id'],)).fetchone()
                row['avatar']='data:image/png;base64,'+picture[0] if picture else ''
            if 'user_memory_variants' in tables:
                from butler.identity.contact_identity import conflict_memories
                row['memory_conflicts'] = conflict_memories(db,p['user_id'])
                row['memory_count']=count-len({r['key'] for r in row['memory_conflicts']})+len(row['memory_conflicts'])
            rows.append(row)
        people = {p['user_id'] for p in profiles}
        for c in state['conversations']:
            if c['channel_type']=='dm' and c.get('person_id') in people: continue
            rows.append({'id':c['id'],'kind':'group' if c['channel_type']=='group' else 'person',
                         'name':c['name'],'enabled':c['enabled'],'conversations':[deepcopy(c)],
                         'memberships':[b for b in bindings if c['channel_type']=='group' and b['channel_type']=='group' and b['contact']==c['name']],
                         'bindings':[],'memory_count':0,'policy':c.get('policy')})
        return sorted(rows,key=lambda r:(r['name'],r['kind'],r['id']))

    def _policy(self, route, policy):
        policy = clean_policy(policy)
        if policy is not None:
            if self.policy_validator is None: raise ValueError('角色和 Skill 必须通过服务端技能目录验证')
            self.policy_validator(route, policy)
        return policy

    def save(self, payload):
        if not isinstance(payload, dict): raise ValueError('联系人请求格式无效')
        if not is_unified(self.path): raise ValueError('联系人尚未迁移；请先只读预览并明确切换')
        action = payload.get('action')
        fields = {
            'create':{'name','channel_type','person_id'},
            'person':{'id','name','enabled','policy','confirm_merge'},
            'conversation':{'id','name','channel_type','uid','profile','label','session_key','listening','enabled','policy','subscriptions','person_id'},
            'link_binding':{'id','binding_id','binding_version'},
            'membership':{'id','group_id','nickname'},
            'memory_set':{'id','memory_version','key','value'},
            'memory_delete':{'id','memory_version','key'},
            'settings':{'settings'},
            'aliases':{'aliases'},
        }
        if action not in fields or set(payload)-fields[action]-{'action','version'}: raise ValueError('未知联系人操作或字段')
        for key in ('id','binding_id','person_id','group_id'):
            if key in payload and not isinstance(payload[key],str):raise ValueError('联系人或成员 ID 无效')
        version = payload.get('version')
        if type(version) is not int: raise ValueError('联系人版本无效')
        store = ContactStore(self.path)
        # Schema creation belongs to an explicit administration write, never GET.
        from butler.business import BusinessStore
        from butler.identity.user_registry import UserRegistry
        registry = UserRegistry(BusinessStore(self.path))
        with store.transaction() as db:
            state = store._snapshot(db)
            if state['version'] != version: raise ValueError('contact version conflict; reload before saving')
            if action == 'create':
                name = self._name(payload.get('name'))
                channel = payload.get('channel_type','dm')
                if channel not in {'dm','group'}: raise ValueError('会话类型无效')
                if any(c['name']==name for c in state['conversations']): raise ValueError('此会话已存在')
                person = ''
                if channel == 'dm':
                    binding = db.execute("SELECT * FROM user_bindings WHERE channel_type='dm' AND contact=? ORDER BY created_at,binding_id",(name,)).fetchone()
                    if binding is None:binding = registry._create(db, 'dm', name, name)
                    state=ContactStore._snapshot(db)
                    person = binding['user_id']
                    if payload.get('person_id') and payload['person_id'] != person:
                        person = self._merge(db, state, person, payload['person_id'])
                state['conversations'].append({'id':uuid.uuid4().hex,'name':name,'channel_type':channel,
                    'uid':'contact-'+uuid.uuid4().hex[:16],'profile':'default','label':'','session_key':'',
                    'person_id':person,'listening':False,'enabled':True,'policy':None,'subscriptions':[]})
            elif action == 'person':
                person = db.execute('SELECT * FROM user_profiles WHERE user_id=?',(payload.get('id'),)).fetchone()
                if person is None: raise ValueError('联系人不存在')
                pid = person['user_id']
                if 'name' in payload:
                    name = self._name(payload['name'])
                    from butler.identity.contact_identity import normalize_name, _people, _priority
                    matches=sorted((p for p in _people(db).values() if p['user_id']!=pid and normalize_name(name) in p['names']),key=_priority)
                    if matches:
                        if payload.get('confirm_merge') is not True: raise ValueError('同名联系人将合并并共享记忆，请核对后确认归并')
                        pid = self._merge(db,state,pid,matches[0]['user_id'])
                    db.execute('UPDATE user_profiles SET display_name=? WHERE user_id=?',(name,pid))
                    from butler.identity.contact_identity import ensure_schema, remember_name
                    ensure_schema(db)
                    remember_name(db,pid,person['display_name'])
                    remember_name(db,pid,name)
                if 'enabled' in payload:
                    if type(payload['enabled']) is not bool: raise ValueError('启用开关必须为布尔值')
                    db.execute('UPDATE user_bindings SET enabled=?,version=version+1 WHERE user_id=?',(int(payload['enabled']),pid))
                    for c in state['conversations']:
                        if c.get('person_id')==pid:
                            c['enabled']=payload['enabled']
                            if not payload['enabled']:c['listening']=False
                if 'policy' in payload:
                    route = next((c for c in state['conversations'] if c.get('person_id')==pid and c['channel_type']=='dm'),{'name':person['display_name'],'profile':'default'})
                    policy = self._policy(route,payload['policy'])
                    if policy and policy['heartbeat_enabled'] and not any(c.get('person_id')==pid and c['channel_type']=='dm' and c['enabled'] for c in state['conversations']):
                        raise ValueError('个人心跳需要明确的私聊投递会话')
                    state['person_policies'][pid] = policy
            elif action == 'conversation':
                c = next((c for c in state['conversations'] if c['id']==payload.get('id')),None)
                if c is None: raise ValueError('会话不存在')
                updates = {k:v for k,v in payload.items() if k not in {'action','version','id'}}
                if 'person_id' in updates and updates['person_id']:
                    from butler.identity.contact_identity import canonical_user
                    updates['person_id']=canonical_user(db,updates['person_id'])
                    if c['channel_type']!='dm' or not db.execute('SELECT 1 FROM user_profiles WHERE user_id=?',(updates['person_id'],)).fetchone(): raise ValueError('联系人关联无效')
                    if c.get('person_id') and c['person_id'] != updates['person_id']:
                        self._merge(db,state,c['person_id'],updates['person_id'])
                        c=next(c for c in state['conversations'] if c['id']==payload['id'])
                if 'policy' in updates:
                    updates['policy'] = self._policy(dict(c,**updates),updates['policy'])
                    updates['inherit_person_policy']=True
                old_name = c['name']
                if 'name' in updates: updates['name'] = self._name(updates['name'])
                if all(isinstance(updates.get(k),str) and updates[k].strip() for k in ('name','uid','profile')):
                    updates['needs_route']=False
                c.update(updates)
                if c['name'] != old_name:
                    db.execute('UPDATE user_bindings SET contact=?,version=version+1 WHERE contact=? AND channel_type=?',(c['name'],old_name,c['channel_type']))
                    for alias in state['aliases']:
                        if alias['group']==old_name: alias['group']=c['name']
            elif action == 'link_binding':
                source = registry._get(db,payload.get('binding_id'))
                if type(payload.get('binding_version')) is not int or source['version']!=payload['binding_version']: raise ValueError('binding version conflict; reload before saving')
                self._merge(db,state,source['user_id'],payload.get('id'))
            elif action == 'membership':
                group=next((c for c in state['conversations'] if c['id']==payload.get('group_id') and c['channel_type']=='group'),None)
                if group is None:raise ValueError('所属群不存在')
                target=payload.get('id')
                if not db.execute('SELECT 1 FROM user_profiles WHERE user_id=?',(target,)).fetchone():raise ValueError('联系人不存在')
                binding=registry._create(db,'group',group['name'],self._name(payload.get('nickname')))
                self._merge(db,state,binding['user_id'],target)
            elif action == 'aliases':
                state['aliases']=deepcopy(payload.get('aliases'))
            elif action == 'settings':
                state['settings'] = deepcopy(payload.get('settings'))
            elif action in {'memory_set','memory_delete'}:
                from butler.identity.contact_identity import canonical_user,ensure_schema
                ensure_schema(db)
                pid=canonical_user(db,payload.get('id'))
                person=db.execute('SELECT * FROM user_profiles WHERE user_id=?',(pid,)).fetchone()
                if person is None:raise ValueError('联系人不存在')
                if type(payload.get('memory_version')) is not int or person['memory_version']!=payload['memory_version']:raise ValueError('memory version conflict; reload before saving')
                key=payload.get('key');owner='user:'+pid
                if not isinstance(key,str) or not key.strip() or len(key)>200:raise ValueError('记忆 key 无效')
                old=db.execute('SELECT value FROM memory WHERE owner=? AND key=?',(owner,key)).fetchone()
                if action=='memory_delete':registry.store.delete_memory(owner,key,db=db,source='administrator')
                else:registry.store.set_memory(owner,key,payload.get('value'),db=db,source='administrator')
                registry._audit(db,'person:'+pid,action,{'key':key,'previous':old[0] if old else None,'value':payload.get('value'),'source':'administrator'})
            store._save(db,state,state['version'])
        return {'ok':True,**self.read()}

    @staticmethod
    def _name(value):
        from butler.identity.contact_identity import normalize_name
        name = normalize_name(value)
        if not name or len(name)>200: raise ValueError('名称不能为空、占位名称或过长')
        return name

    @staticmethod
    def _merge(db,state,source,target):
        from butler.identity.contact_identity import canonical_user
        target=canonical_user(db,target)
        if not isinstance(target,str) or not db.execute('SELECT 1 FROM user_profiles WHERE user_id=?',(target,)).fetchone(): raise ValueError('目标联系人不存在')
        if source == target: return target
        from butler.identity.contact_identity import merge_users
        report=merge_users(db,source,target)
        # Identity redirects can freeze inherited policies and advance this same
        # transaction's canonical version. The initial client version was checked
        # before the merge; preserve that helper's updated route behavior.
        fresh=ContactStore._snapshot(db)
        state.clear();state.update(fresh)
        return report['target_id']
