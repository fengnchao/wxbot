"""用户知识图谱：一人一个 Obsidian vault，节点是 Markdown，关联是 [[双链]]。

目录结构（root 默认 data/knowledge）：

    data/knowledge/
      index.json                目录缓存：owner、条数、提炼游标；删掉也能从 vault 重建
      template.md               可选的模板覆盖层，由管理台「知识模板」页维护
      p-<slug>/vault/           Obsidian vault 根，只放 .md
        人物/冯草草.md          节点目录来自模板，默认人物/组织/话题
        组织/鸭王集训营.md
        话题/AI 编程.md
        对话/2026-11-01.md      按天记录的原文
        index.md                 中心索引页：把节点与日记全部串起来

为什么是 Markdown 而不是表：知识图谱的价值在节点之间的关联，只有正文里的 [[双链]]
才能被 Obsidian 的 graph view 直接画出来。表能存字段，存不出拓扑。

为什么还有 index.md：只有实体之间互相提到时才产生双链，新库或单聊的对话里
根本没有第三方实体，graph view 就是一堆孤立点。索引页按类别列出事实、按目录列出
节点、按天列出日记，每个条目都是一个双链，于是所有文件都挂到同一个中心上。

为什么一人一个 vault：任何一个人的数据坏了、被导出或整体清空，都不牵连别人；
Obsidian 一次只开一个 vault，一个人的图也不会被别人的节点淹没。

为什么原文也写 Markdown：事实要能点回原话才有说服力。按天一个文件把文件数量
压到每年 365 个，不至于把 graph 挤满。

为什么 index.json 可以重建：它只存计数与游标，不是知识本身；删掉它一条知识都不会丢。
"""
from __future__ import annotations

from contextlib import closing, suppress
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

import yaml

from butler.runtime.knowledge_template import (LEGACY_INDEX, LEGACY_KINDS, LEGACY_NODE_DIRS,
                                                LEGACY_SECTIONS, OVERRIDE_NAME, load_template)

MAX_READ_LIMIT = 200
OUTCOMES = ('ok', 'error', 'silent')
# 默认值来自模板模块，保留这些名字让旧引用继续可用；实际读写一律走 self.template。
FACT_KINDS = LEGACY_KINDS
FACT_SECTIONS = LEGACY_SECTIONS
# 索引页的分类标题用日常说法，与节点里的小节名解耦：小节名一改，旧事实就留在旧小节里。
INDEX_SECTIONS = LEGACY_INDEX
NODE_TYPES = tuple(LEGACY_NODE_DIRS)
NODE_DIRS = LEGACY_NODE_DIRS
EPISODE_DIR = '对话'
INDEX_FILE = 'index.md'
INDEX_LIMIT = 40
INDEX_DAYS = 10
CHANNEL_LABELS = {'group': '群聊', 'dm': '私聊'}

FACT_LINE = re.compile(r'^- (?P<body>.*?) <!-- (?P<meta>fp:[^<>]*?) -->$')
LINK = re.compile(r'\[\[([^\[\]]+)\]\]')
# 日记块行尾的注释：重建目录时用它算「最近说话」，比文件 mtime 可靠。
BLOCK_AT = re.compile(r'<!-- [^<>]*?at:([\d.]+)[^<>]*?-->')


def episode_owner(contact, channel_type='dm'):
    """身份体系签发的 memory_owner 优先；没有身份就落到独立命名空间，绝不挂到别人名下。"""
    owner = str(getattr(contact, 'memory_owner', '') or '').strip()
    if owner:
        return owner
    name = str(getattr(contact, 'name', '') or contact or '').strip()
    return 'anon:%s:%s' % ('group' if channel_type == 'group' else 'dm', name)


def owner_slug(owner):
    """owner 里有冒号和中文，不能直接当目录名；用稳定散列，目录名不需要反查。"""
    digest = sha1(str(owner).encode('utf-8')).hexdigest()[:16]
    return 'p-' + digest


def _safe(name, fallback='未命名'):
    """节点文件名：Obsidian 的 [[链接]] 不能带 []|#^，文件名也不能带路径分隔符。"""
    text = re.sub(r'[\x00-\x1f<>:"/\\|?*#^\[\]]', '-', str(name or ''))
    text = re.sub(r'\s+', ' ', text).strip(' .-')[:60].strip(' .-')
    return text or fallback


def _inline(value, limit=300):
    """写进 HTML 注释的短字段：注释不能被 --> 提前截断，也不能带换行。"""
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text.replace('|', '｜').replace('>', '＞').replace('<', '＜')[:limit]


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stamp(at):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(at))


def _atomic_write(path, text, attempts=3, delay=0.05):
    """Markdown 没有事务：先写同目录临时文件再替换，读侧永远看到完整文件。

    Windows 上目标文件可能被别的进程短暂持有——Obsidian 正在索引同一个 vault 时，
    os.replace 会抛 PermissionError（WinError 5）。这类冲突几十毫秒就过去，所以退避
    重试几次；次数用尽或遇到别的错误才抛出，并顺手清掉临时文件，不留给编辑器索引。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tries = max(1, int(attempts))
    for attempt in range(tries):
        try:
            tmp.write_text(text, encoding='utf-8')
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt + 1 >= tries:
                with suppress(OSError):
                    tmp.unlink()
                raise
            time.sleep(delay * (attempt + 1))


def _frontmatter(values):
    lines = ['---']
    for key, value in values.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            lines.append('%s: %s' % (key, value))
        else:
            lines.append('%s: %s' % (key, json.dumps(str(value), ensure_ascii=False)))
    lines.append('---')
    return '\n'.join(lines)


def _split_frontmatter(text):
    """读用 YAML，写用 _frontmatter：手工拼的引号格式由 json.dumps 保证合法。"""
    if not text.startswith('---'):
        return {}, text
    end = text.find('\n---', 3)
    if end < 0:
        return {}, text
    try:
        data = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        data = {}
    meta = {str(k): v for k, v in data.items()} if isinstance(data, dict) else {}
    return meta, text[end + 4:].lstrip('\n')


def _fact_line(value, key, kind, confidence, quote, at, source, links, fingerprint):
    body = value
    for link in links:
        name = str(link or '').strip()
        if name and name in body and '[[%s]]' % name not in body:
            body = body.replace(name, '[[%s]]' % name, 1)
    meta = '|'.join((
        'fp:%s' % fingerprint,
        'key:%s' % _inline(key),
        'kind:%s' % kind,
        'conf:%.2f' % max(0.0, min(1.0, _float(confidence, 0.5))),
        'at:%s' % round(_float(at, time.time()), 3),
        'src:%s' % _inline(source),
        'quote:%s' % _inline(quote),
    ))
    return '- %s <!-- %s -->' % (body, meta)


def _parse_fact_line(line):
    matched = FACT_LINE.match(line.strip())
    if not matched:
        return None
    meta = {}
    for part in matched.group('meta').split('|'):
        key, _, value = part.partition(':')
        meta[key.strip()] = value.strip()
    body = matched.group('body').strip()
    return {'fp': meta.get('fp', ''), 'kind': meta.get('kind', 'topic'),
            'fact_key': meta.get('key', ''), 'fact_value': LINK.sub(r'\1', body),
            'confidence': _float(meta.get('conf'), 0.5), 'at': _float(meta.get('at')),
            'source': meta.get('src', 'extract'), 'quote': meta.get('quote', ''),
            'links': LINK.findall(body)}


def _fact_id(owner, node, line):
    return sha256('\0'.join((owner, node.as_posix(), line)).encode('utf-8')).hexdigest()


def _read_node(path, *, include_lines=False):
    """节点文件 → (frontmatter, {小节标题: [事实]})；坏行直接跳过，不让一条脏数据拖垮整页。"""
    text = Path(path).read_text('utf-8', 'replace')
    meta, body = _split_frontmatter(text)
    sections, heading = {}, ''
    for line in body.splitlines():
        if line.startswith('## '):
            heading = line[3:].strip()
            sections.setdefault(heading, [])
        elif line.startswith('- '):
            item = _parse_fact_line(line)
            if item:
                if include_lines:
                    item['line'] = line
                sections.setdefault(heading, []).append(item)
    return meta, sections


def _insert_line(text, heading, line):
    lines = text.rstrip('\n').split('\n')
    marker = '## ' + heading
    start = next((i for i, row in enumerate(lines) if row.strip() == marker), None)
    if start is None:
        return '\n'.join(lines + ['', marker, '', line]) + '\n'
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('## ')),
               len(lines))
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, line)
    return '\n'.join(lines) + '\n'


def _node_header(node_type, name, contact, owner, at):
    meta = {'type': node_type, 'name': name, 'contact': contact, 'owner': owner,
            'updated': _stamp(at), 'updated_ts': round(float(at), 3)}
    return _frontmatter(meta) + '\n\n# ' + name + '\n'


def _rewrite_meta(text, changes):
    meta, body = _split_frontmatter(text)
    meta.update(changes)
    return _frontmatter(meta) + '\n\n' + body.lstrip('\n')


def _episode_header(owner, contact, channel_type, day):
    meta = {'type': 'conversations', 'date': day, 'owner': owner, 'contact': contact,
            'channel_type': 'group' if channel_type == 'group' else 'dm'}
    return (_frontmatter(meta) + '\n\n# ' + day + '\n\n'
            + '> 本文件由 Butler 自动写入，记录与「%s」的对话。\n' % contact)


def _quote_block(text):
    return '\n'.join(('> ' + row) if row else '>' for row in str(text).split('\n'))


def _episode_block(contact, channel_type, request_id, user_text, reply_text, outcome, at):
    label = CHANNEL_LABELS.get(channel_type, '私聊')
    head = '## %s · %s · %s' % (time.strftime('%H:%M:%S', time.localtime(at)),
                                _inline(contact, 40), label)
    meta = '|'.join(('rid:%s' % _inline(request_id, 80),
                     'at:%s' % round(float(at), 3),
                     'outcome:%s' % (outcome if outcome in OUTCOMES else 'ok'),
                     'contact:%s' % _inline(contact, 60),
                     'channel:%s' % ('group' if channel_type == 'group' else 'dm')))
    parts = [head, '<!-- %s -->' % meta, '', '**用户**', '', _quote_block(user_text)]
    if reply_text is not None:
        parts += ['', '**助理**', '', _quote_block(reply_text)]
    return '\n'.join(parts) + '\n'


def _section_text(text, start, end):
    at = text.find(start)
    if at < 0:
        return None
    at += len(start)
    stop = text.find(end, at) if end else len(text)
    chunk = text[at:stop]
    lines = []
    for row in chunk.splitlines():
        if row.startswith('> '):
            lines.append(row[2:])
        elif row == '>':
            lines.append('')
    return '\n'.join(lines).strip('\n')


def _parse_day(path):
    """日记文件 → 每轮一条；时间、会话与 request_id 都来自那行 HTML 注释。"""
    text = Path(path).read_text('utf-8', 'replace')
    meta, body = _split_frontmatter(text)
    owner = str(meta.get('owner') or '')
    rows = []
    for block in re.split(r'(?m)^## ', body)[1:]:
        _, _, rest = block.partition('\n')
        comment = re.search(r'<!-- (.*?) -->', rest)
        info = {}
        if comment:
            for part in comment.group(1).split('|'):
                key, _, value = part.partition(':')
                info[key.strip()] = value.strip()
        user_text = _section_text(rest, '**用户**', '**助理**')
        if user_text is None:
            continue
        rows.append({'owner': owner,
                     'contact': info.get('contact', ''),
                     'channel_type': info.get('channel', 'dm'),
                     'request_id': info.get('rid', ''),
                     'user_text': user_text,
                     'reply_text': _section_text(rest, '**助理**', None),
                     'outcome': info.get('outcome', 'ok'),
                     'at': _float(info.get('at'))})
    return rows


def _fallback_kind(template):
    return 'topic' if template.has_kind('topic') else template.kinds[0].key


def _fallback_node(template):
    return 'person' if template.has_node_type('person') else template.node_types[0].key


class KnowledgeStore:
    """vault 的读写入口；读不建目录，写才落盘。"""

    def __init__(self, root, log=None, retention_days=90, template=None):
        self.log = log or (lambda *a, **k: None)
        self.root = Path(root)
        self.retention_days = max(1, min(3650, int(retention_days)))
        # 覆盖层放在 vault 之外，既不会被 facts() 扫到，删掉就是恢复默认。
        self.template = template or load_template(self.root / OVERRIDE_NAME, self.log)
        self._lock = threading.RLock()

    # ---------- 路径 ----------
    @property
    def index_path(self):
        return self.root / 'index.json'

    def owner_dir(self, owner):
        return self.root / owner_slug(owner)

    def vault_dir(self, owner):
        return self.owner_dir(owner) / 'vault'

    def episodes_dir(self, owner):
        return self.vault_dir(owner) / self.template.episode_dir

    def node_path(self, owner, node_type, name):
        return self.vault_dir(owner) / self.template.node_dir(node_type) / (_safe(name) + '.md')

    def index_page_path(self, owner):
        return self.vault_dir(owner) / self.template.index_file

    def _vault(self, entry):
        return self.root / entry['slug'] / 'vault'

    # ---------- 目录缓存 ----------
    def _catalog(self):
        """返回 (owner 表, rebuilt)。rebuilt 表示这份表刚从 vault 数出来，计数已是权威值。"""
        try:
            data = json.loads(self.index_path.read_text('utf-8'))
            owners = data.get('owners')
            if isinstance(owners, dict) and owners:
                return owners, False
        except (OSError, ValueError):
            pass
        return self._recount(), True

    def _save(self, owners):
        _atomic_write(self.index_path,
                      json.dumps({'owners': owners}, ensure_ascii=False, indent=1, sort_keys=True))

    def _touch(self, owner, contact, channel_type, *, episodes=0, facts=0, at=None):
        with self._lock:
            owners, rebuilt = self._catalog()
            entry = owners.get(owner)
            if entry is None:
                entry = {
                    'owner': owner, 'slug': owner_slug(owner),
                    'contact': contact or owner, 'contact_name': contact or owner,
                    'channel_type': 'group' if channel_type == 'group' else 'dm',
                    'episodes': episodes, 'facts': facts, 'extracted_at': 0.0,
                    'first_at': 0.0, 'last_at': 0.0}
            elif not rebuilt:
                # 刚重建的表已经把本次写入数进去了，再加一遍就会翻倍。
                entry['episodes'] = int(entry.get('episodes') or 0) + episodes
                entry['facts'] = int(entry.get('facts') or 0) + facts
            if at:
                entry['first_at'] = min(entry.get('first_at') or at, at)
                entry['last_at'] = max(entry.get('last_at') or 0.0, at)
            owners[owner] = entry
            self._save(owners)

    def _recount(self):
        """index.json 丢了就从 vault 数回来；游标沿旧值，不因重建把已提炼的原文重提一遍。"""
        previous = {}
        try:
            data = json.loads(self.index_path.read_text('utf-8'))
            if isinstance(data.get('owners'), dict):
                previous = data['owners']
        except (OSError, ValueError):
            pass
        owners = {}
        for vault in sorted(self.root.glob('p-*/vault')):
            if not vault.is_dir():
                continue
            owner = contact = ''
            channel = 'dm'
            facts = 0
            last = 0.0
            for node in sorted(vault.glob('*/*.md')):
                if node.parent.name == self.template.episode_dir:
                    continue
                meta, sections = _read_node(node)
                owner = owner or str(meta.get('owner') or '')
                contact = contact or str(meta.get('contact') or '')
                last = max(last, _float(meta.get('updated_ts')))
                facts += sum(len(items) for items in sections.values())
            episodes = 0
            for day in sorted((vault / self.template.episode_dir).glob('*.md')):
                text = day.read_text('utf-8', 'replace')
                meta, _ = _split_frontmatter(text)
                owner = owner or str(meta.get('owner') or '')
                contact = contact or str(meta.get('contact') or '')
                channel = 'group' if meta.get('channel_type') == 'group' else 'dm'
                episodes += text.count('\n## ')
                for found in BLOCK_AT.finditer(text):
                    last = max(last, _float(found.group(1)))
            if not owner:
                continue
            before = previous.get(owner) or {}
            owners[owner] = {'owner': owner, 'slug': vault.parent.name,
                             'contact': contact or owner, 'contact_name': contact or owner,
                             'channel_type': channel, 'episodes': episodes, 'facts': facts,
                             'extracted_at': _float(before.get('extracted_at')),
                             'first_at': _float(before.get('first_at')), 'last_at': last}
        if owners:
            self._save(owners)
        return owners

    def owners(self):
        """目录里的全部人，最近说话的在前。目录为空时返回空表，不建任何东西。"""
        return sorted(self._catalog()[0].values(),
                      key=lambda e: (-_float(e.get('last_at')), e.get('contact') or ''))

    # ---------- 写入 ----------
    def _ensure_vault(self, owner):
        """首次写入时按模板建出目录骨架；已存在的目录不动，也不写标记文件。

        后加的目录不靠这里预建：add_fact 写节点时 _atomic_write 会自己建父目录，
        所以老 vault 不需要迁移也能多出新目录。
        """
        vault = self.vault_dir(owner)
        dirs = [item.directory for item in self.template.node_types]
        dirs.append(self.template.episode_dir)
        if all((vault / name).is_dir() for name in dirs):
            return False
        for name in dirs:
            (vault / name).mkdir(parents=True, exist_ok=True)
        return True

    def record(self, owner, contact, channel_type, request_id, user_text,
               reply_text, outcome, *, at=None):
        """写一轮对话到当天的日记；同一 request_id 重试靠文本里的 rid 忽略。"""
        owner = str(owner or '').strip()
        contact = str(contact or '').strip()
        if not owner or not contact:
            raise ValueError('知识库记录必须有 owner 与 contact')
        stamp = time.time() if at is None else float(at)
        day = time.strftime('%Y-%m-%d', time.localtime(stamp))
        path = self.episodes_dir(owner) / (day + '.md')
        with self._lock:
            self._ensure_vault(owner)
            text = (path.read_text('utf-8', 'replace') if path.is_file()
                    else _episode_header(owner, contact, channel_type, day))
            if request_id and ('rid:%s|' % _inline(request_id, 80)) in text:
                return False
            text = text.rstrip('\n') + '\n\n' + _episode_block(
                contact, channel_type, request_id, user_text, reply_text, outcome, stamp)
            _atomic_write(path, text)
            self._touch(owner, contact, channel_type, episodes=1, at=stamp)
            self.rebuild_index(owner)
        return True

    def add_fact(self, owner, contact, fact_value, *, kind='topic', fact_key='',
                 quote='', episode_at=None, confidence=0.5, source='extract', at=None,
                 subject='', subject_type='person', links=()):
        """写一条事实到它所属实体的节点；同一指纹重复写入被忽略。

        subject 为空时落到当前联系人自己的节点上；links 里的名字会在正文里变成
        [[双链]]，Obsidian 的 graph view 靠它连边。
        """
        owner = str(owner or '').strip()
        contact = str(contact or '').strip()
        value = str(fact_value or '').strip()
        if not owner or not contact or not value:
            raise ValueError('事实必须有 owner、contact 与内容')
        stamp = time.time() if at is None else float(at)
        kind = kind if self.template.has_kind(kind) else _fallback_kind(self.template)
        name = str(subject or '').strip() or contact
        node_type = subject_type if self.template.has_node_type(subject_type) else _fallback_node(self.template)
        fingerprint = sha1(('%s|%s|%s' % (kind, fact_key, value)).encode('utf-8')).hexdigest()[:16]
        path = self.node_path(owner, node_type, name)
        with self._lock:
            if path.is_file():
                text = path.read_text('utf-8', 'replace')
                _, sections = _read_node(path)
                if any(item['fp'] == fingerprint for items in sections.values() for item in items):
                    return False
            else:
                text = _node_header(node_type, name, contact, owner, stamp)
            line = _fact_line(value, fact_key, kind, confidence, quote, stamp,
                              source, links, fingerprint)
            text = _insert_line(text, self.template.section(kind), line)
            _atomic_write(path, _rewrite_meta(text, {'updated': _stamp(stamp),
                                                     'updated_ts': round(stamp, 3)}))
            self._touch(owner, contact, 'dm', facts=1, at=stamp)
            self.rebuild_index(owner)
        return True

    def delete_fact(self, owner, fact_id):
        """Remove one exact line and retain its node, episodes and extraction cursor."""
        if not isinstance(owner, str) or not owner.strip() or len(owner) > 512:
            raise ValueError('知识归属无效')
        if not isinstance(fact_id, str) or not re.fullmatch(r'[0-9a-f]{64}', fact_id):
            raise ValueError('事实编号无效，请刷新知识库')
        with self._lock:
            owners, _ = self._catalog()
            entry = owners.get(owner)
            if entry is not None:
                vault = self._vault(entry)
                vault_root = vault.resolve()
                if not vault_root.is_relative_to(self.root.resolve()) or vault_root.name != 'vault':
                    raise ValueError('知识库目录无效')
                for path in sorted(vault.glob('*/*.md')):
                    if path.parent.name == self.template.episode_dir or not path.resolve().is_relative_to(vault_root):
                        continue
                    try:
                        text = path.read_text('utf-8')
                    except UnicodeDecodeError:
                        continue
                    _, body = _split_frontmatter(text)
                    if not body:
                        continue
                    lines = body.splitlines(keepends=True)
                    node = path.relative_to(vault)
                    matches = [index for index, line in enumerate(lines)
                               if line.startswith('- ') and _parse_fact_line(line)
                               and _fact_id(owner, node, line.rstrip('\n')) == fact_id]
                    if not matches:
                        continue
                    if len(matches) != 1:
                        raise ValueError('节点包含重复内容，无法安全定位这条事实')
                    del lines[matches[0]]
                    _atomic_write(path, text[:-len(body)] + ''.join(lines))
                    try:
                        entry['facts'] = max(0, int(entry.get('facts') or 0) - 1)
                        self._save(owners)
                        self.rebuild_index(owner)
                    except OSError as exc:
                        self.log('事实已删除，索引更新失败: %s', type(exc).__name__)
                        return {'deleted': True, 'indexes_updated': False}
                    return {'deleted': True, 'indexes_updated': True}
        return {'deleted': False, 'indexes_updated': True}

    # ---------- 游标 ----------
    def extracted_at(self, owner):
        """该 owner 已提炼到哪个时刻；游标丢了就当 0，重提一遍也不会产生重复事实。"""
        entry = self._catalog()[0].get(owner) or {}
        return _float(entry.get('extracted_at'))

    def set_extracted_at(self, owner, at):
        with self._lock:
            owners, _ = self._catalog()
            entry = owners.get(owner)
            if entry is None:
                return
            entry['extracted_at'] = round(float(at), 3)
            self._save(owners)

    # ---------- 清理 ----------
    def prune(self, now=None, retention_days=None):
        """删掉过期的日记文件；节点是事实，不参与过期。返回删除的对话条数。"""
        days = self.retention_days if retention_days is None else max(1, min(3650, int(retention_days)))
        cutoff = (time.time() if now is None else float(now)) - days * 86400
        cutoff_day = time.strftime('%Y-%m-%d', time.localtime(cutoff))
        deleted = 0
        for path in sorted(self.root.glob('p-*/vault/' + self.template.episode_dir + '/*.md')):
            if path.stem >= cutoff_day:
                continue
            deleted += path.read_text('utf-8', 'replace').count('\n## ')
            path.unlink()
        if deleted:
            self._recount()
            for entry in self.owners():
                self.rebuild_index(entry['owner'])
        return deleted

    def rebuild_index(self, owner):
        """重写 vault 根的中心索引页：按模板分区列事实、按真实目录列节点、按天列最近对话。

        每一个条目都是一个 [[双链]]，所以即使对话里从没出现过第三方实体，
        Obsidian 的 graph view 也不是一堆孤立点。事实多了只列 index_limit 条，
        超出部分提示条数，避免索引页无限长。

        节点清单遍历 vault 下实际存在的目录，而不是只看模板里的几个：模板改过目录名、
        或旧 vault 用的是旧目录时，历史节点仍然要出现在索引里，不能凭空消失。
        """
        entry = self._catalog()[0].get(owner)
        if not entry:
            return False
        vault = self._vault(entry)
        if not vault.is_dir():
            return False
        rows = []
        for path in sorted(vault.glob('*/*.md')):
            if path.parent.name == self.template.episode_dir:
                continue
            meta, sections = _read_node(path)
            node = str(meta.get('name') or path.stem)
            for items in sections.values():
                rows += [dict(item, node=node) for item in items]
        limit = self.template.index_limit
        lines = [_frontmatter({'type': 'index', 'owner': owner,
                               'contact': entry.get('contact') or '',
                               'updated': _stamp(time.time())}),
                 '', '# ' + self.template.index_title, '',
                 '> ' + self.template.index_note, '']
        known = set()
        for kind in self.template.kinds:
            known.add(kind.key)
            items = [row for row in rows if row['kind'] == kind.key]
            lines += ['## ' + kind.index_label, '']
            if not items:
                lines += ['（还没有）', '']
                continue
            lines += ['- [[%s]] %s' % (row['node'], row['fact_value'])
                      for row in items[:limit]]
            if len(items) > limit:
                lines.append('- 另有 %d 条未列出' % (len(items) - limit))
            lines.append('')
        others = [row for row in rows if row['kind'] not in known]
        if others:
            lines += ['## 其他', '']
            lines += ['- [[%s]] %s' % (row['node'], row['fact_value'])
                      for row in others[:limit]]
            lines.append('')
        lines += ['## 节点', '']
        nodes = 0
        order = [item.directory for item in self.template.node_types]
        extra = sorted(path.name for path in vault.iterdir()
                       if path.is_dir() and path.name != self.template.episode_dir
                       and not path.name.startswith('.') and path.name not in order)
        for directory in order + extra:
            folder = vault / directory
            names = sorted(path.stem for path in folder.glob('*.md')) if folder.is_dir() else []
            if not names:
                continue
            nodes += len(names)
            lines += ['### ' + directory, '']
            lines += ['- [[%s]]' % name for name in names]
            lines.append('')
        if not nodes:
            lines += ['（还没有）', '']
        lines += ['## 最近对话', '']
        days = sorted((vault / self.template.episode_dir).glob('*.md'),
                      reverse=True)[:self.template.index_days]
        if not days:
            lines += ['（还没有）', '']
        else:
            for path in days:
                count = path.read_text('utf-8', 'replace').count('\n## ')
                lines.append('- [[%s]] %d 轮' % (path.stem, count))
            lines.append('')
        _atomic_write(self.index_page_path(owner), '\n'.join(lines).rstrip('\n') + '\n')
        return True

    def close(self):
        """没有常驻连接了，保留方法让调用方不必判断。"""

    # ---------- 查询 ----------
    def episodes_of(self, owner, after_at=0.0, limit=200):
        """取某个 owner 自某时刻之后的新原文，供提炼按批推进。"""
        rows = []
        folder = self.vault_dir(owner) / self.template.episode_dir
        if not folder.is_dir():
            return []
        for path in sorted(folder.glob('*.md')):
            if path.stem < time.strftime('%Y-%m-%d', time.localtime(_float(after_at))):
                continue
            rows += [row for row in _parse_day(path) if row['at'] > _float(after_at)]
        rows.sort(key=lambda r: r['at'])
        rows = rows[:max(1, min(1000, int(limit)))]
        for index, row in enumerate(rows, 1):
            row['id'] = index
        return rows

    def read(self, owner='', query='', limit=50, offset=0, contact='', channel_type=''):
        """原文列表，按时间倒序；指定 owner 时只看他的 vault。"""
        limit = max(1, min(MAX_READ_LIMIT, int(limit)))
        offset = max(0, int(offset))
        rows = []
        for entry in self.owners():
            if owner and entry['owner'] != owner:
                continue
            folder = self._vault(entry) / self.template.episode_dir
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob('*.md'), reverse=True):
                for row in _parse_day(path):
                    row['owner'] = entry['owner']
                    if contact and row['contact'] != contact:
                        continue
                    if channel_type and row['channel_type'] != channel_type:
                        continue
                    if query and query.casefold() not in (
                            row['user_text'] + ' ' + (row['reply_text'] or '')).casefold():
                        continue
                    rows.append(row)
        rows.sort(key=lambda r: (r['at'], r['contact']), reverse=True)
        total = len(rows)
        page = rows[offset:offset + limit]
        return {'rows': page, 'total': total, 'limit': limit, 'offset': offset,
                'has_more': offset + len(page) < total,
                'owners': [e['owner'] for e in self.owners()]}

    def facts(self, owner='', query='', limit=50, offset=0, contact='', *, allowed_owners=None):
        """事实列表，按写入时间倒序；query 同时匹配 key 与内容。"""
        limit = max(1, min(MAX_READ_LIMIT, int(limit)))
        offset = max(0, int(offset))
        rows = []
        for entry in self.owners():
            if owner and entry['owner'] != owner:
                continue
            if allowed_owners is not None and entry['owner'] not in allowed_owners:
                continue
            vault = self._vault(entry)
            if not vault.is_dir():
                continue
            for path in sorted(vault.glob('*/*.md')):
                if path.parent.name == self.template.episode_dir:
                    continue
                meta, sections = _read_node(path, include_lines=True)
                node = str(meta.get('name') or path.stem)
                row_contact = str(meta.get('contact') or entry['contact'])
                if contact and row_contact != contact:
                    continue
                for items in sections.values():
                    for item in items:
                        if query and query.casefold() not in (
                                item['fact_key'] + ' ' + item['fact_value']).casefold():
                            continue
                        rows.append({'owner': entry['owner'], 'contact': row_contact,
                                     'fact_id': _fact_id(entry['owner'], path.relative_to(vault), item['line']),
                                     'node': node, 'kind': item['kind'],
                                     'fact_key': item['fact_key'],
                                     'fact_value': item['fact_value'], 'quote': item['quote'],
                                     'episode_at': item['at'] or None,
                                     'confidence': item['confidence'],
                                     'source': item['source'], 'created': item['at']})
        rows.sort(key=lambda r: (_float(r['created']), r['node']), reverse=True)
        total = len(rows)
        page = rows[offset:offset + limit]
        return {'rows': page, 'total': total, 'limit': limit, 'offset': offset,
                'has_more': offset + len(page) < total,
                'owners': [e['owner'] for e in self.owners()]}

    def sessions(self, owner, kind='episodes'):
        """这个人在哪些会话里留下过数据：私聊与群聊分开列，条数多的在前。"""
        entry = self._catalog()[0].get(owner)
        if not entry:
            return []
        vault = self._vault(entry)
        counts = {}
        if kind == 'facts':
            for path in sorted(vault.glob('*/*.md')):
                if path.parent.name == self.template.episode_dir:
                    continue
                meta, sections = _read_node(path)
                contact = str(meta.get('contact') or entry['contact'])
                counts[contact] = counts.get(contact, 0) + sum(len(v) for v in sections.values())
            return [{'contact': k, 'channel_type': '', 'count': v}
                    for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        for path in sorted((vault / self.template.episode_dir).glob('*.md')):
            for row in _parse_day(path):
                key = (row['contact'], row['channel_type'])
                counts[key] = counts.get(key, 0) + 1
        return [{'contact': k[0], 'channel_type': k[1], 'count': v}
                for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


# ---------- 迁移 ----------
def _checkpoint_legacy(path):
    """改名留底前把 WAL 合并回主库。

    _import_sqlite 用 mode=ro 打开，只读连接读得到 WAL 里的内容却永远不会 checkpoint；
    直接把主库改名，WAL 与 -shm 就与新名字失配，留底库便缺最后几条，回滚会丢数据。
    """
    try:
        with closing(sqlite3.connect(str(path))) as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            db.commit()
    except sqlite3.DatabaseError:
        pass
    for suffix in ('-wal', '-shm'):
        side = Path(str(path) + suffix)
        if side.is_file():
            try:
                side.unlink()
            except OSError:
                pass


def _import_sqlite(store, path, log):
    """把 SQLite 时代的原文与事实搬进 vault；读不出结构就当没有，不中断迁移。"""
    moved = 0
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'kb_episodes' in tables:
            for row in db.execute('SELECT * FROM kb_episodes ORDER BY id'):
                if store.record(row['owner'], row['contact'], row['channel_type'],
                                row['request_id'], row['user_text'], row['reply_text'],
                                row['outcome'], at=row['at']):
                    moved += 1
        if 'kb_facts' in tables:
            for row in db.execute('SELECT * FROM kb_facts ORDER BY id'):
                if store.add_fact(row['owner'], row['contact'], row['fact_value'],
                                  kind=row['kind'], fact_key=row['fact_key'],
                                  quote=row['quote'], episode_at=row['episode_at'],
                                  confidence=row['confidence'], source=row['source'],
                                  at=row['created']):
                    moved += 1
    log('迁移 %s：%d 条', Path(path).name, moved)
    return moved


def _import_memory(store, path, log):
    """把 business.sqlite3 遗留的 memory 表搬成节点事实：旧的一套收进知识库后再废弃。"""
    moved = 0
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'memory' not in tables:
            return 0
        names = {}
        if 'identities' in tables:
            for row in db.execute('SELECT owner,contact FROM identities'):
                names[row['owner']] = row['contact']
        for row in db.execute('SELECT owner,key,value,updated FROM memory'):
            contact = names.get(row['owner']) or str(row['owner']).split(':', 1)[-1]
            if store.add_fact(row['owner'], contact, row['value'], kind='profile',
                              fact_key=row['key'], source='memory-migration',
                              at=row['updated']):
                moved += 1
    log('迁移 memory 表：%d 条', moved)
    return moved


def migrate_legacy(data_dir, log=None):
    """把 SQLite 时代的知识库与遗留 memory 表搬进 vault，成功后把原文件改名留底。"""
    log = log or (lambda *a, **k: None)
    base = Path(data_dir)
    root = base / 'knowledge'
    store = KnowledgeStore(root, log)
    moved = 0
    legacy = base / 'knowledge.sqlite3'
    if legacy.is_file():
        moved += _import_sqlite(store, legacy, log)
        _checkpoint_legacy(legacy)
        legacy.replace(base / 'knowledge.legacy.sqlite3')
    for path in sorted(root.glob('p-*/episodes.sqlite3')):
        moved += _import_sqlite(store, path, log)
        _checkpoint_legacy(path)
        path.replace(path.with_name('episodes.sqlite3.migrated'))
    for path in sorted(root.glob('p-*/facts.sqlite3')):
        moved += _import_sqlite(store, path, log)
        _checkpoint_legacy(path)
        path.replace(path.with_name('facts.sqlite3.migrated'))
    business = base / 'business.sqlite3'
    if business.is_file():
        moved += _import_memory(store, business, log)
    index = root / 'index.sqlite3'
    if index.is_file():
        _checkpoint_legacy(index)
        index.replace(index.with_name('index.sqlite3.migrated'))
    store.close()
    log('知识库迁移完成：%d 条写入 vault', moved)
    return moved
