"""L1 原文与知识图谱的只读投影，一人一个 vault。

绝不创建目录、绝不写文件：查不到就是「还没记录过」，界面显示空态而不是报错。
读取全部委托给 KnowledgeStore，写路径只属于 Butler 进程——
管理台不再自己解析存储格式，格式改了只需要改一处。
"""
from pathlib import Path

from butler.runtime.knowledge_store import KnowledgeStore

MAX_READ_LIMIT = 200
EPISODE_FIELDS = ('owner', 'at', 'contact', 'channel_type', 'user_text', 'reply_text', 'outcome')
FACT_FIELDS = ('owner', 'contact', 'kind', 'fact_key', 'fact_value', 'quote',
               'episode_at', 'confidence', 'source', 'created')


def _empty(available=False, limit=50, offset=0):
    return {'available': available, 'owners': [], 'rows': [], 'total': 0,
            'limit': limit, 'offset': offset, 'has_more': False}


class KnowledgeView:
    """管理台侧的只读投影；所有入参都当不可信输入处理。"""

    def __init__(self, root):
        self.root = Path(root)
        self.store = KnowledgeStore(self.root)

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
        return [{'owner': e['owner'], 'name': e.get('contact_name') or e.get('contact'),
                 'contact': e.get('contact'), 'channel_type': e.get('channel_type'),
                 'episodes': int(e.get('episodes') or 0), 'facts': int(e.get('facts') or 0),
                 'last_at': e.get('last_at') or 0,
                 'sessions': self.store.sessions(e['owner'], kind)}
                for e in self._entries()]

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

    # ---------- 事实 ----------
    def facts(self, owner='', query='', limit=50, offset=0, contact=''):
        taxonomy = self.taxonomy()
        if not self._entries():
            return {**_empty(), **taxonomy}
        try:
            page = self.store.facts(owner=owner, query=query, limit=limit, offset=offset,
                                    contact=contact)
        except OSError as exc:
            raise RuntimeError('知识库读取失败（%s）' % type(exc).__name__) from None
        rows = [{key: row.get(key) for key in FACT_FIELDS} for row in page['rows']]
        return {'available': True, 'owners': self.owners('facts'), 'rows': rows,
                'total': page['total'], 'limit': page['limit'], 'offset': page['offset'],
                'has_more': page['has_more'], **taxonomy}
