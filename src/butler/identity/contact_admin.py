"""Business-facing unified contact management. Paths come from server config only."""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
import uuid
import json
import hashlib

from butler.identity.contact_store import ContactStore, clean_policy, is_unified

# 管理员手工上传的头像记在 algorithm 列，采集来的图带的是感知哈希算法名。
ADMIN_AVATAR = 'admin'


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

    def merge_preview(self, source_id, target_id):
        if not is_unified(self.path):
            raise ValueError('联系人尚未迁移')
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            return self._merge_preview(db, ContactStore._snapshot(db), source_id, target_id)

    @staticmethod
    def _merge_preview(db, state, source_id, target_id):
        from butler.identity.contact_identity import canonical_user
        if not all(isinstance(value, str) and value for value in (source_id, target_id)):
            raise ValueError('联系人 ID 无效')
        if source_id == target_id:
            raise ValueError('不能把联系人合并到它自己')
        for value in (source_id, target_id):
            if canonical_user(db, value) != value:
                raise ValueError('该联系人已经合并到其他档案')
        people = {row['id']: row for row in ContactAdmin._rows(db, state) if row['kind'] == 'person'}
        if source_id not in people or target_id not in people:
            raise ValueError('联系人不存在，请刷新列表')
        summaries, notes, fingerprint = [], [], [state]
        for value in (source_id, target_id):
            row = people[value]
            profile = dict(db.execute('SELECT * FROM user_profiles WHERE user_id=?', (value,)).fetchone())
            bindings = [dict(b) for b in db.execute('SELECT * FROM user_bindings WHERE user_id=? ORDER BY binding_id', (value,))]
            items = [dict(n) for n in db.execute('SELECT key,value,updated FROM memory WHERE owner=? ORDER BY key', ('user:'+value,))]
            variants = row.get('memory_conflicts', [])
            fingerprint.append([profile, bindings, items, variants, row['memberships']])
            summaries.append({key: row[key] for key in ('id','name','bindings','conversations','memberships','memory_count','policy')})
            notes.append([dict(n, source_user_id=value, source_label=row['name']) for n in items] + variants)
        by_key = {}
        for item in notes[0] + notes[1]:
            by_key.setdefault(item['key'], []).append(item)
        conflicts = [item for values in by_key.values() if len({n['value'] for n in values}) > 1 for item in values]
        version = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False,
                                            separators=(',', ':')).encode()).hexdigest()
        return {'source': summaries[0], 'target': summaries[1], 'conflicts': conflicts,
                'version': state['version'], 'preview_version': version,
                'rules': '保留目标人物；群身份与窗口并入，窗口现有策略保持原行为；个人记忆保留全部来源，冲突待整理。'}

    def _checked_merge(self, db, state, source, target, preview_version):
        if not isinstance(preview_version, str) or not preview_version:
            raise ValueError('请先预览身份合并的影响范围')
        preview = self._merge_preview(db, state, source, target)
        if preview_version != preview['preview_version']:
            raise ValueError('merge preview version conflict; 请重新预览后确认')
        return self._merge(db, state, source, target)

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
    def _feature_owners(db, tables):
        """跨人重复的头像特征 -> 真正拥有它的人。群成员观测 ID 与特征一致时最可信。"""
        if 'user_avatars' not in tables:
            return {}
        result = {}
        for r in db.execute('SELECT a.feature FROM user_avatars a JOIN user_bindings b ON b.binding_id=a.binding_id '
                            'GROUP BY a.feature HAVING COUNT(DISTINCT b.user_id)>1'):
            owner = ''
            if 'user_observation_keys' in tables:
                row = db.execute('SELECT b.user_id FROM user_observation_keys o '
                                 'JOIN user_bindings b ON b.binding_id=o.binding_id '
                                 'WHERE o.member_key=? LIMIT 1',(r[0],)).fetchone()
                owner = row[0] if row else ''
            result[r[0]] = owner
        return result

    @staticmethod
    def _evidence(db, tables):
        """每条绑定的认人证据强度，以及可以安全展示的头像。"""
        avatars = {}
        if 'user_avatars' in tables:
            for r in db.execute('SELECT binding_id,COUNT(*) n,MAX(LENGTH(image)) big FROM user_avatars GROUP BY binding_id'):
                avatars[r[0]] = (r[1], r[2] or 0)
        observations = {r[0]: r[1] for r in db.execute(
            'SELECT binding_id,COUNT(*) FROM user_observation_keys GROUP BY binding_id')} if 'user_observation_keys' in tables else {}
        aliases = {r[0]: r[1] for r in db.execute(
            'SELECT binding_id,COUNT(*) FROM user_member_aliases GROUP BY binding_id')} if 'user_member_aliases' in tables else {}
        # 同一张头像出现在两个人名下，说明匹配时串了人，只有真正的拥有者能拿它展示。
        shared = ContactAdmin._feature_owners(db, tables)
        return avatars, observations, aliases, shared

    @staticmethod
    def _pick_primary(items):
        """同一人多条群身份时保留证据最完整的一条，其余默认折叠。"""
        def rank(b):
            avatars, observations, aliases, _ = b.get('_evidence', ((0, 0), 0, 0, set()))
            name = b.get('nickname', '')
            return (
                -int(bool(b.get('identity_confirmed'))),
                -int(bool(b.get('enabled'))),
                -int(avatars[0] > 0),
                -int(bool(b.get('nickname_confirmed'))),
                -observations, -aliases,
                int(len(name) > 2 and name.endswith('）')),
                b.get('created_at') or 0,
                b.get('binding_id') or '',
            )
        ordered = sorted(items, key=rank)
        return (ordered[0] if ordered else None, ordered[1:])

    @staticmethod
    def _base_name(name):
        """去掉同名冲突时自动加的「（12 位绑定 ID）」后缀，还原真正的群昵称。"""
        text = (name or '').strip()
        if not text.endswith('）') or '（' not in text:
            return text
        head, _, tail = text.rpartition('（')
        suffix = tail[:-1]
        if len(suffix) == 12 and all(ch in '0123456789abcdef' for ch in suffix):
            return head.strip() or text
        return text

    @staticmethod
    def _display_name(display_name, groups):
        """自动登记的档案名是「待命名-<ID>」；群昵称经确认后就用昵称当显示名。"""
        if not display_name.startswith('待命名-'):
            return display_name
        confirmed = [b['nickname'] for b in groups
                     if b.get('nickname_confirmed') and not b['nickname'].startswith('待命名-')]
        return confirmed[0] if confirmed else display_name

    @staticmethod
    def _merge_candidates(bindings, user_id, primary, shown):
        """同群同昵称却分成两份档案，说明当初没认出是同一人，列出可合并的对象。"""
        found = {}
        for mine in primary:
            base = ContactAdmin._base_name(mine.get('nickname', ''))
            for other in bindings:
                if (other.get('channel_type') != 'group' or other.get('contact') != mine.get('contact')
                        or other.get('user_id') == user_id or other.get('user_id') not in shown):
                    continue
                if ContactAdmin._base_name(other.get('nickname', '')) != base:
                    continue
                found.setdefault(other['user_id'], {'id': other['user_id'],
                                                    'name': shown[other['user_id']],
                                                    'nickname': other.get('nickname', ''),
                                                    'contact': other.get('contact', '')})
        return list(found.values())

    @staticmethod
    def _delete_blockers(db, state, user_id, related=None):
        """删除档案的硬条件：自动登记、从未确认、没有投递窗口、没人合并到它。

        返回不能删的原因，空字符串表示可以删。已确认过的身份一律保留：
        「我」「老登看剑」的档案名也是待命名开头，但它们被人工确认过。
        """
        if not db.execute('SELECT 1 FROM user_profiles WHERE user_id=?', (user_id,)).fetchone():
            return '联系人不存在'
        if any(c.get('person_id') == user_id for c in state['conversations']):
            return '该档案还挂着投递窗口，请先删除会话'
        if db.execute('SELECT 1 FROM memory WHERE owner=? LIMIT 1', ('user:'+user_id,)).fetchone():
            return '该档案有个人记忆，不允许自动删除'
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'user_memory_variants' in tables and db.execute(
                'SELECT 1 FROM user_memory_variants WHERE user_id=? LIMIT 1', (user_id,)).fetchone():
            return '该档案有记忆来源，不允许自动删除'
        rows = related if related is not None else \
            [dict(r) for r in db.execute('SELECT * FROM user_bindings WHERE user_id=?', (user_id,))]
        if not rows:
            return '该档案没有群身份，无需删除'
        if any(r.get('identity_confirmed') for r in rows):
            return '该档案有已确认的身份，不允许自动删除'
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_redirects'").fetchone() \
                  and db.execute('SELECT 1 FROM user_redirects WHERE user_id=? OR old_user_id=?', (user_id,user_id)).fetchone():
            return '有其他档案已合并到它，不允许删除'
        return ''

    @staticmethod
    def _delete_binding(db, binding_id):
        """删掉一条身份及其采集证据；记忆归档案所有，不跟着单条绑定消失。"""
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('user_avatars', 'user_observation_keys', 'user_member_aliases', 'user_binding_names'):
            if table in tables:
                db.execute('DELETE FROM ' + table + ' WHERE binding_id=?', (binding_id,))
        if 'user_legacy_owners' in tables:
            db.execute('DELETE FROM user_legacy_owners WHERE binding_id=?', (binding_id,))
        db.execute('DELETE FROM user_bindings WHERE binding_id=?', (binding_id,))

    @staticmethod
    def _delete_person(db, user_id):
        """删掉一份档案：群身份、头像、观测 ID、共享记忆一并清除。"""
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        binding_ids = [r[0] for r in db.execute('SELECT binding_id FROM user_bindings WHERE user_id=?', (user_id,))]
        for table in ('user_avatars', 'user_observation_keys', 'user_member_aliases', 'user_binding_names'):
            if table in tables:
                for binding_id in binding_ids:
                    db.execute('DELETE FROM ' + table + ' WHERE binding_id=?', (binding_id,))
        if 'user_legacy_owners' in tables:
            for binding_id in binding_ids:
                db.execute('DELETE FROM user_legacy_owners WHERE binding_id=?', (binding_id,))
        db.execute('DELETE FROM user_bindings WHERE user_id=?', (user_id,))
        db.execute('DELETE FROM memory WHERE owner=?', ('user:' + user_id,))
        if 'user_memory_variants' in tables:
            db.execute('DELETE FROM user_memory_variants WHERE user_id=?', (user_id,))
        if 'user_name_history' in tables:
            db.execute('DELETE FROM user_name_history WHERE user_id=?', (user_id,))
        db.execute('DELETE FROM user_profiles WHERE user_id=?', (user_id,))
        return len(binding_ids)

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
        avatars, observations, aliases, shared = ContactAdmin._evidence(db, tables)
        for binding in bindings:
            binding['_evidence'] = (avatars.get(binding['binding_id'], (0, 0)), observations.get(binding['binding_id'], 0),
                                    aliases.get(binding['binding_id'], 0), shared)
        # 头像按人取一张：管理员手工换的图最可信，其余只信已确认且启用的绑定。
        pictures = {}
        if 'user_avatars' in tables:
            for r in db.execute('SELECT b.user_id,a.image,a.feature,a.algorithm,LENGTH(a.image) big FROM user_avatars a '
                                'JOIN user_bindings b ON b.binding_id=a.binding_id '
                                'WHERE b.enabled=1 AND (b.identity_confirmed=1 OR a.algorithm=? ) '
                                'ORDER BY (a.algorithm=?) DESC,LENGTH(a.image) DESC,a.created_at DESC',
                                (ADMIN_AVATAR, ADMIN_AVATAR)):
                bucket = pictures.setdefault(r['user_id'], {'image': '', 'count': 0, 'unusable': 0})
                bucket['count'] += 1
                owner = shared.get(r['feature'], '')
                if r['algorithm'] != ADMIN_AVATAR and ((r['feature'] in shared and owner != r['user_id'])
                                                      or r['big'] < 1024):
                    bucket['unusable'] += 1
                elif not bucket['image']:
                    bucket['image'] = r['image']
        rows = []
        # 自动登记的档案名是「待命名-<ID>」；群昵称一旦确认，就用昵称当显示名。
        shown = {p['user_id']: ContactAdmin._display_name(p['display_name'], [
            b for b in bindings if b['user_id'] == p['user_id'] and b['channel_type'] == 'group'])
            for p in profiles}
        for p in profiles:
            related = [b for b in bindings if b['user_id'] == p['user_id']]
            conversations = [deepcopy(c) for c in state['conversations'] if c.get('person_id')==p['user_id']]
            count = db.execute('SELECT COUNT(*) FROM memory WHERE owner=?', ('user:'+p['user_id'],)).fetchone()[0] if 'memory' in tables else 0
            for b in related:
                b['memory_owner'] = 'user:'+p['user_id']
            groups = [b for b in related if b['channel_type']=='group']
            primary, hidden = [], []
            for contact in dict.fromkeys(b['contact'] for b in groups):
                best, rest = ContactAdmin._pick_primary([b for b in groups if b['contact'] == contact])
                if best: primary.append(best)
                hidden.extend(rest)
            picture = pictures.get(p['user_id'], {})
            row = {'id':p['user_id'],'kind':'person','name':shown[p['user_id']],
                   'enabled':any(bool(b['enabled']) for b in related) if related else any(c['enabled'] for c in conversations),
                   'conversations':conversations,'memberships':primary,
                   'bindings':related,'memory_count':count,'policy':state['person_policies'].get(p['user_id']),
                   'avatar':'data:image/png;base64,'+picture['image'] if picture.get('image') else '',
                   'avatar_count':picture.get('count', 0),
                   'avatar_issues':picture.get('unusable', 0),
                   'wechat':next((c['name'] for c in conversations if c['channel_type']=='dm' and c['enabled']), ''),
                   'hidden_memberships':len(hidden),
                   'duplicate_names':[b['nickname'] for b in hidden],
                   'merge_candidates':ContactAdmin._merge_candidates(bindings, p['user_id'], primary, shown)}
            row['can_cleanup'] = p['display_name'].startswith('待命名-') and not ContactAdmin._delete_blockers(
                db, state, p['user_id'], related)
            if 'user_name_history' in tables:
                row['historical_names']=[r[0] for r in db.execute('SELECT name FROM user_name_history WHERE user_id=? ORDER BY name',(p['user_id'],))]
            if 'user_memory_variants' in tables:
                from butler.identity.contact_identity import conflict_memories
                row['memory_conflicts'] = conflict_memories(db,p['user_id'])
                row['memory_count']=count-len({r['key'] for r in row['memory_conflicts']})+len(row['memory_conflicts'])
            rows.append(row)
        people = {p['user_id'] for p in profiles}
        for c in state['conversations']:
            if c['channel_type']=='dm' and c.get('person_id') in people: continue
            members = [b for b in bindings if c['channel_type']=='group' and b['channel_type']=='group' and b['contact']==c['name']]
            kept, dropped = [], []
            if c['channel_type']=='group':
                for uid in dict.fromkeys(b['user_id'] for b in members):
                    best, rest = ContactAdmin._pick_primary([b for b in members if b['user_id'] == uid])
                    if best: kept.append(best)
                    dropped.extend(rest)
                # Equal nicknames are only a hint; different people remain visible.
            route = deepcopy(c)
            rows.append({'id':c['id'],'kind':'group' if c['channel_type']=='group' else 'person',
                         'name':c['name'],'enabled':c['enabled'],'conversations':[route],
                         'memberships':kept or members,'bindings':members,'memory_count':0,'policy':c.get('policy'),
                         'avatar':'','avatar_count':0,'avatar_issues':0,
                         'wechat':c['name'] if c['channel_type']=='dm' else '',
                         'hidden_memberships':len(dropped),
                         'duplicate_names':[b['nickname'] for b in dropped]})
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
            'link_binding':{'id','binding_id','binding_version','preview_version'},
            'membership':{'id','group_id','nickname'},
            'memory_set':{'id','memory_version','key','value'},
            'memory_delete':{'id','memory_version','key'},
            'settings':{'settings'},
            'aliases':{'aliases'},
            'avatar':{'id','avatar'},
            'avatar_cleanup':set(),
            'binding':{'id','binding_id','nickname','enabled'},
            'binding_disable':{'id','binding_id'},
            'merge':{'id','source_id','preview_version'},
            'person_delete':{'id'},
            'person_cleanup':{'ids'},
            'contact_delete':{'id','kind'},
            'binding_delete':{'id','binding_id'},
        }
        if action not in fields or set(payload)-fields[action]-{'action','version'}: raise ValueError('未知联系人操作或字段')
        for key in ('id','binding_id','person_id','group_id'):
            if key in payload and not isinstance(payload[key],str):raise ValueError('联系人或成员 ID 无效')
        version = payload.get('version')
        if action == 'person_cleanup':
            ids = payload.get('ids')
            if not isinstance(ids,list) or not ids or len(ids)>1000 or any(not isinstance(item,str) or not item for item in ids):
                raise ValueError('请先预览并指定要清理的档案，最多 1000 条')
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
                    desired = payload.get('person_id') or None
                    if binding is None:
                        binding = registry._create(db, 'dm', name, name, person_id=desired, reuse_name=False)
                    state=ContactStore._snapshot(db)
                    person = binding['user_id']
                    if desired and desired != person:
                        raise ValueError('该窗口已属于其他人物，请先预览并确认身份合并')
                state['conversations'].append({'id':uuid.uuid4().hex,'name':name,'channel_type':channel,
                    'uid':'contact-'+uuid.uuid4().hex[:16],'profile':'default','label':'','session_key':'',
                    'person_id':person,'listening':False,'enabled':True,'policy':None,'subscriptions':[]})
            elif action == 'person':
                person = db.execute('SELECT * FROM user_profiles WHERE user_id=?',(payload.get('id'),)).fetchone()
                if person is None: raise ValueError('联系人不存在')
                pid = person['user_id']
                if 'name' in payload:
                    name = self._name(payload['name'])
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
                        raise ValueError('窗口归属改变需要先预览并确认身份合并')
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
                self._checked_merge(db,state,source['user_id'],payload.get('id'),payload.get('preview_version'))
            elif action == 'membership':
                group=next((c for c in state['conversations'] if c['id']==payload.get('group_id') and c['channel_type']=='group'),None)
                if group is None:raise ValueError('所属群不存在')
                target=payload.get('id')
                if not db.execute('SELECT 1 FROM user_profiles WHERE user_id=?',(target,)).fetchone():raise ValueError('联系人不存在')
                registry._create(db,'group',group['name'],self._name(payload.get('nickname')),
                                 person_id=target, reuse_name=False)
            elif action == 'aliases':
                state['aliases']=deepcopy(payload.get('aliases'))
            elif action == 'avatar':
                from common.avatar_identity import decode_avatar, normalize_avatar
                from butler.identity import contact_identity
                pid = payload.get('id')
                if not db.execute('SELECT 1 FROM user_profiles WHERE user_id=?',(pid,)).fetchone():
                    raise ValueError('联系人不存在')
                db.execute('DELETE FROM user_avatars WHERE binding_id IN '
                           '(SELECT binding_id FROM user_bindings WHERE user_id=?)',(pid,))
                image = payload.get('avatar')
                if image:
                    if not isinstance(image,str) or len(image)>2*1024*1024: raise ValueError('头像数据无效或过大')
                    target = db.execute('SELECT binding_id FROM user_bindings WHERE user_id=? '
                                        'ORDER BY enabled DESC,created_at LIMIT 1',(pid,)).fetchone()
                    if target is None: raise ValueError('此联系人还没有私聊或群绑定，无法上传头像')
                    feature = normalize_avatar(decode_avatar(image))
                    registry._add_avatar(db, target[0], feature)
                    # 手工换的图不参与自动采集的归属判定，总是可以展示。
                    db.execute('UPDATE user_avatars SET algorithm=? WHERE binding_id=? AND image=?',
                               (ADMIN_AVATAR, target[0], feature['image']))
                registry._audit(db, 'person:'+pid, 'avatar_set' if image else 'avatar_cleared',
                                {'source':'administrator'})
                contact_identity.touch_version(db)
            elif action == 'avatar_cleanup':
                from butler.identity import contact_identity
                removed = self._cleanup_avatars(db)
                registry._audit(db, 'person:cleanup', 'avatar_cleanup',
                                {'source':'administrator','removed':removed})
                contact_identity.touch_version(db)
            elif action in {'binding','binding_disable'}:
                from butler.identity import contact_identity
                member = db.execute('SELECT * FROM user_bindings WHERE binding_id=?',(payload.get('binding_id'),)).fetchone()
                if member is None: raise ValueError('成员关系不存在，请刷新列表')
                if member['user_id'] != payload.get('id'): raise ValueError('该成员关系不属于这个联系人')
                if action == 'binding_disable':
                    db.execute('UPDATE user_bindings SET enabled=0,version=version+1 WHERE binding_id=?',(member['binding_id'],))
                    registry._audit(db, member['binding_id'], 'disabled',
                                    {'source':'administrator','reason':'duplicate'})
                else:
                    nickname = payload.get('nickname', contact_identity.binding_name(db, member))
                    if not isinstance(nickname,str) or not nickname.strip() or len(nickname)>200:
                        raise ValueError('群昵称不能为空或过长')
                    enabled = payload.get('enabled', bool(member['enabled']))
                    if type(enabled) is not bool: raise ValueError('启用状态必须为布尔值')
                    old = contact_identity.binding_name(db, member)
                    db.execute('UPDATE user_bindings SET enabled=?,identity_confirmed=1,nickname_confirmed=1,'
                               'version=version+1 WHERE binding_id=?',(int(enabled),member['binding_id']))
                    if nickname.strip() != old:
                        contact_identity.ensure_schema(db)
                        db.execute('INSERT OR REPLACE INTO user_binding_names VALUES(?,?)',(member['binding_id'],nickname.strip()))
                        contact_identity.remember_name(db, member['user_id'], old)
                    registry._audit(db, member['binding_id'], 'binding_updated',
                                    {'source':'administrator','fields':list(payload)})
                contact_identity.touch_version(db)
            elif action == 'merge':
                from butler.identity.contact_identity import canonical_user
                source = payload.get('source_id')
                if not isinstance(source, str) or not source:
                    raise ValueError('要合并的联系人无效')
                if not db.execute('SELECT 1 FROM user_profiles WHERE user_id=?', (source,)).fetchone():
                    raise ValueError('要合并的联系人不存在，请刷新列表')
                if canonical_user(db, source) != source:
                    raise ValueError('该联系人已经合并到其他档案')
                if canonical_user(db, payload.get('id')) == source:
                    raise ValueError('不能把联系人合并到它自己')
                target = self._checked_merge(db, state, source, payload.get('id'), payload.get('preview_version'))
                registry._audit(db, 'person:'+target, 'merged',
                                {'merged_user': source, 'source': 'administrator'})
            elif action == 'contact_delete':
                from butler.identity import contact_identity
                from butler.identity.contact_identity import canonical_user, ensure_schema
                ensure_schema(db)
                target, kind = payload.get('id'), payload.get('kind')
                if kind not in {'person', 'group'}:
                    raise ValueError('联系人类型无效，请刷新列表')
                person = db.execute('SELECT display_name FROM user_profiles WHERE user_id=?',
                                    (target,)).fetchone()
                conversation = next((c for c in state['conversations'] if c['id'] == target), None)
                if person is not None and kind == 'person':
                    # 合并掉的旧档案只留作历史引用，删掉它会断掉重定向，只能删合并后的那一份。
                    if canonical_user(db, target) != target:
                        raise ValueError('这份档案已经合并到其他联系人，请删除合并后的档案')
                    routes = [c for c in state['conversations']
                              if c['channel_type'] == 'dm' and c.get('person_id') == target]
                    count = ContactAdmin._delete_person(db, target)
                    # 只摘掉这个人的私聊窗口，群聊路由属于群本身，不能跟着人一起消失。
                    state['conversations'] = [c for c in state['conversations']
                                              if c['channel_type'] != 'dm' or c.get('person_id') != target]
                    state['person_policies'].pop(target, None)
                    registry._audit(db, 'person:'+target, 'contact_deleted',
                                    {'source':'administrator','name':person[0],'bindings':count,
                                     'routes':[c['name'] for c in routes]})
                elif conversation is not None and conversation['channel_type'] == kind:
                    # 只摘掉路由：群昵称记录和成员档案跟着群走，重新加群还要靠它们认人。
                    name = conversation['name']
                    state['conversations'] = [c for c in state['conversations'] if c['id'] != target]
                    registry._audit(db, kind+':'+target, 'contact_deleted',
                                    {'source':'administrator','name':name,'routes':[name]})
                else:
                    raise ValueError('联系人不存在，请刷新列表')
                contact_identity.touch_version(db)
            elif action == 'binding_delete':
                from butler.identity import contact_identity
                from butler.identity.contact_identity import ensure_schema
                ensure_schema(db)
                member = db.execute('SELECT * FROM user_bindings WHERE binding_id=?',
                                    (payload.get('binding_id'),)).fetchone()
                if member is None:
                    raise ValueError('成员关系不存在，请刷新列表')
                if member['user_id'] != payload.get('id'):
                    raise ValueError('该成员关系不属于这个联系人')
                nickname, contact = contact_identity.binding_name(db, member), member['contact']
                ContactAdmin._delete_binding(db, member['binding_id'])
                registry._audit(db, 'person:'+member['user_id'], 'binding_deleted',
                                {'source':'administrator','binding':member['binding_id'],
                                 'contact':contact,'nickname':nickname,'person_removed':False})
                contact_identity.touch_version(db)
            elif action in {'person_delete','person_cleanup'}:
                from butler.identity import contact_identity
                from butler.identity.contact_identity import ensure_schema
                ensure_schema(db)
                delete = [payload.get('id')] if action == 'person_delete' else list(dict.fromkeys(payload['ids']))
                removed = []
                for uid in delete:
                    if action == 'person_cleanup':
                        profile = db.execute('SELECT display_name FROM user_profiles WHERE user_id=?', (uid,)).fetchone()
                        if profile is None or not profile[0].startswith('待命名-'):
                            continue
                    blockers = ContactAdmin._delete_blockers(db, state, uid)
                    if blockers:
                        if action == 'person_delete':
                            raise ValueError(blockers)
                        continue
                    name = db.execute('SELECT display_name FROM user_profiles WHERE user_id=?', (uid,)).fetchone()[0]
                    count = ContactAdmin._delete_person(db, uid)
                    state['person_policies'].pop(uid, None)
                    registry._audit(db, 'person:'+uid, 'person_deleted',
                                    {'source':'administrator','name':name,'bindings':count})
                    removed.append(name)
                if action == 'person_cleanup' and not removed:
                    raise ValueError('没有可删除的未命名档案')
                contact_identity.touch_version(db)
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
            # 头像、绑定等操作会直接推进 unified_contacts 的版本号，保存前同步一次，避免自相冲突。
            store._save(db,state,store._snapshot(db)['version'])
        return {'ok':True,**self.read()}

    @staticmethod
    def _cleanup_avatars(db):
        """删除不可信头像：占位小图，以及同一张图挂在别人名下的副本。"""
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        removed = 0
        for row in db.execute('SELECT id FROM user_avatars WHERE LENGTH(image)<1024 AND algorithm!=?',
                              (ADMIN_AVATAR,)).fetchall():
            db.execute('DELETE FROM user_avatars WHERE id=?',(row[0],));removed += 1
        for feature, owner in ContactAdmin._feature_owners(db, tables).items():
            if owner:
                keep = owner
            else:
                # 没有群成员观测 ID 可对照时，保守地只保留私聊最多的那个人。
                people = [r[0] for r in db.execute('SELECT DISTINCT b.user_id FROM user_avatars a '
                                                   'JOIN user_bindings b ON b.binding_id=a.binding_id WHERE a.feature=?',(feature,))]
                if len(people) < 2: continue
                def strength(uid):
                    binds = db.execute('SELECT channel_type FROM user_bindings WHERE user_id=?',(uid,)).fetchall()
                    return (sum(1 for b in binds if b[0]=='dm'), len(binds))
                keep = max(people, key=strength)
            # 管理员手工换的图不参与清理。
            for row in db.execute('SELECT a.id FROM user_avatars a JOIN user_bindings b ON b.binding_id=a.binding_id '
                                  'WHERE a.feature=? AND a.algorithm!=? AND b.user_id!=?',
                                  (feature, ADMIN_AVATAR, keep)).fetchall():
                db.execute('DELETE FROM user_avatars WHERE id=?',(row[0],));removed += 1
        return removed

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
