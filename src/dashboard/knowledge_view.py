"""L1 原文与知识图谱的只读投影，一人一个 vault。

绝不创建目录、绝不写文件：查不到就是「还没记录过」，界面显示空态而不是报错。
读取全部委托给 KnowledgeStore，写路径只属于 Butler 进程——
管理台不再自己解析存储格式，格式改了只需要改一处。
"""
from collections import defaultdict
from contextlib import closing
from pathlib import Path
import sqlite3

from butler.identity.contact_identity import normalize_name
from butler.runtime.knowledge_store import KnowledgeStore

MAX_READ_LIMIT = 200
EPISODE_FIELDS = ('owner', 'at', 'contact', 'channel_type', 'user_text', 'reply_text', 'outcome')
FACT_FIELDS = ('owner', 'contact', 'fact_id', 'kind', 'fact_key', 'fact_value', 'quote',
               'episode_at', 'confidence', 'source', 'created')


def _empty(available=False, limit=50, offset=0):
    return {'available': available, 'owners': [], 'rows': [], 'total': 0,
            'limit': limit, 'offset': offset, 'has_more': False}


class KnowledgeView:
    """管理台侧的只读投影；所有入参都当不可信输入处理。"""

    def __init__(self, root, *, identity_path=None):
        self.root = Path(root)
        self.store = KnowledgeStore(self.root)
        self.identity_path = Path(identity_path).resolve() if identity_path else None

    def _entries(self):
        return self.store.owners()

    def taxonomy(self):
        """分类与节点类型来自模板：新增一类后，页面上的筛选项随之出现。"""
        template = self.store.template
        return {'kinds': [{'key': item.key, 'label': item.index_label,
                           'section': item.section, 'hint': item.hint}
                          for item in template.kinds],
                'node_types': [{'key': item.key, 'label': item.directory,
                                'description': item.description}
                               for item in template.node_types]}

    def owners(self, kind='episodes'):
        """左栏的人列表：按人一行，sessions 列出这个人在哪些会话里留下过数据。

        一个人可以同时在私聊和几个群里说过话，所以左栏不按会话拆行：
        拆了就不是「这个人」的单位了。会话维度交给右栏的筛选。
        """
        rows = [{'owner': e['owner'], 'name': e.get('contact_name') or e.get('contact'),
                 'contact': e.get('contact'), 'channel_type': e.get('channel_type'),
                 'episodes': int(e.get('episodes') or 0), 'facts': int(e.get('facts') or 0),
                 'last_at': e.get('last_at') or 0,
                 'sessions': self.store.sessions(e['owner'], kind)}
                for e in self._entries()]
        if kind == 'facts':
            for row in rows:
                row['facts'] = sum(session['count'] for session in row['sessions'])
        return rows

    # ---------- 原文 ----------
    def read(self, owner='', query='', limit=50, offset=0, contact='', channel_type=''):
        taxonomy = self.taxonomy()
        if not self._entries():
            return {**_empty(), **taxonomy}
        try:
            page = self.store.read(owner=owner, query=query, limit=limit, offset=offset,
                                   contact=contact, channel_type=channel_type)
        except OSError as exc:
            raise RuntimeError('对话记录读取失败（%s）' % type(exc).__name__) from None
        rows = [{key: row.get(key) for key in EPISODE_FIELDS} for row in page['rows']]
        return {'available': True, 'owners': self.owners('episodes'), 'rows': rows,
                'total': page['total'], 'limit': page['limit'], 'offset': page['offset'],
                'has_more': page['has_more'], **taxonomy}

    def _identity_names(self):
        if self.identity_path is None or not self.identity_path.is_file():
            return {}, {}
        try:
            with closing(sqlite3.connect(self.identity_path.as_uri() + '?mode=ro', uri=True)) as db:
                tables = {name for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'user_profiles', 'user_bindings'} <= tables:
                    return {}, {}
                people = {'user:' + uid: name for uid, name in db.execute(
                    'SELECT user_id,display_name FROM user_profiles') if normalize_name(name)}
                has_binding_names = 'user_binding_names' in tables
                name = 'COALESCE(n.nickname,b.nickname)' if has_binding_names else 'b.nickname'
                join = ' LEFT JOIN user_binding_names n USING(binding_id)' if has_binding_names else ''
                nicknames = {}
                for uid, group, nickname in db.execute(
                        f'SELECT b.user_id,b.contact,{name} FROM user_bindings b{join} '
                        "WHERE b.channel_type='group' AND b.nickname_confirmed=1 "
                        'ORDER BY b.enabled DESC,b.identity_confirmed DESC,b.created_at,b.binding_id'):
                    if normalize_name(nickname):
                        nicknames.setdefault(('user:' + uid, group), nickname)
                return people, nicknames
        except sqlite3.Error:
            return {}, {}

    def _fact_groups(self, owners):
        groups, group_owners = {}, defaultdict(set)
        people, nicknames = self._identity_names()
        for entry in owners:
            owner = entry['owner']
            counts = {item['contact']: item['count'] for item in entry['sessions']}
            sessions = self.store.sessions(owner)
            channels = defaultdict(set)
            for item in sessions:
                channels[item['contact']].add(item['channel_type'])
                if item['channel_type'] == 'group':
                    group = groups.setdefault(item['contact'], {'name': item['contact'], 'episodes': 0, 'facts': 0})
                    group['episodes'] += item['count']
            # Retention can remove the original day files while keeping group facts.
            if entry['channel_type'] == 'group' and entry['contact'] not in channels:
                channels[entry['contact']].add('group')
            names = {contact for contact, kinds in channels.items() if kinds == {'group'}}
            for contact in sorted(names):
                group = groups.setdefault(contact, {'name': contact, 'episodes': 0, 'facts': 0})
                group['facts'] += counts.get(contact, 0)
                group_owners[contact].add(owner)
            entry['group_only'] = bool(names) and names.issuperset(channels) and names.issuperset(counts)
            entry['name'] = people.get(owner, entry['name'])
        return list(groups.values()), group_owners, people, nicknames

    # ---------- 事实 ----------
    def facts(self, owner='', query='', limit=50, offset=0, contact='', *, group=''):
        taxonomy = self.taxonomy()
        owners = self.owners('facts')
        if not owners:
            return {**_empty(), 'groups': [], **taxonomy}
        try:
            groups, group_owners, people, nicknames = self._fact_groups(owners)
            page = self.store.facts(owner=owner, query=query, limit=limit, offset=offset,
                                    contact=group or contact,
                                    allowed_owners=group_owners[group] if group else None)
        except OSError as exc:
            raise RuntimeError('知识库读取失败（%s）' % type(exc).__name__) from None
        rows = [{key: row.get(key) for key in FACT_FIELDS} for row in page['rows']]
        for row in rows:
            owner, contact = row['owner'], row['contact']
            if owner in group_owners.get(contact, ()):
                row['source_group'] = contact
                row['source_name'] = (nicknames.get((owner, contact)) or people.get(owner) or
                                      ('未识别成员' if owner.startswith('anon:') else '成员姓名未记录'))
        return {'available': True, 'owners': owners, 'groups': groups, 'rows': rows,
                'total': page['total'], 'limit': page['limit'], 'offset': page['offset'],
                'has_more': page['has_more'], **taxonomy}
