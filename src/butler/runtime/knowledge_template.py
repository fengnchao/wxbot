"""知识图谱模板：一份 Markdown 决定 vault 的目录、分类、索引与提炼口径。

两层来源，前者优先：

    data/knowledge/template.md                        页面可编辑的覆盖层
    plugins/butler-wechat/knowledge/graph-template.md  随插件分发的内置默认

两层都读不到时退回本模块里的 ``DEFAULT_TEMPLATE``（与改造前的硬编码行为一致）。

为什么模板不控制事实行的格式：事实行尾的 HTML 注释是 `FACT_LINE` 的解析契约，
改了格式就再也读不回历史事实。模板只决定「写到哪里、叫什么、按什么口径提炼」。

为什么解析分严格与宽松：页面保存要看到「第 24 行：未知节点类型」，所以
`parse_template` 抛带行号的错误；运行时要保证对话能记下来，所以 `load_template`
解析失败只告警一次并回退默认。
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import threading
from pathlib import Path

import yaml

from common.paths import REPO_ROOT

BUILTIN_TEMPLATE = REPO_ROOT / 'plugins' / 'butler-wechat' / 'knowledge' / 'graph-template.md'
OVERRIDE_NAME = 'template.md'
MAX_TEMPLATE_BYTES = 256 * 1024

MAX_KINDS = 20
MAX_NODE_TYPES = 12
MAX_RULES = 20
MAX_HINT = 120
MAX_RULE = 200
MAX_PROMPT = 2400
MAX_NAME = 60

# 改造前写死在 knowledge_store.py 里的默认值，保留成常量供回退与兼容引用。
LEGACY_KINDS = ('profile', 'preference', 'personality', 'goal', 'relation', 'event', 'topic')
LEGACY_SECTIONS = {'profile': '身份', 'preference': '偏好', 'personality': '性格',
                   'goal': '目标', 'relation': '关系', 'event': '事件', 'topic': '话题'}
LEGACY_INDEX = {'profile': '用户信息', 'preference': '喜好', 'personality': '性格',
                'goal': '目标', 'relation': '关系', 'event': '经历', 'topic': '关注'}
LEGACY_NODE_DIRS = {'person': '人物', 'org': '组织', 'topic': '话题'}

KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,31}$')
BAD_RE = re.compile(r'[\x00-\x1f<>:"/\\|?*#^\[\]]')
SEPARATOR_RE = re.compile(r'^:?-{2,}:?$')

NODE_ALIASES = {'type': ('type', '类型'), 'directory': ('目录', 'dir'),
                'description': ('说明', '描述', 'desc')}
KIND_ALIASES = {'kind': ('kind', '分类'), 'section': ('节点小节', 'section', '小节'),
                'index_label': ('索引分类', 'index', '索引'),
                'hint': ('提炼指引', 'hint', '指引')}


class TemplateError(ValueError):
    """模板不合法；errors 是 [{line, message}]，供页面定位。"""

    def __init__(self, errors):
        self.errors = tuple(dict(item) for item in errors)
        super().__init__('；'.join(item['message'] for item in self.errors))


@dataclass(frozen=True)
class Kind:
    key: str
    section: str
    index_label: str
    hint: str = ''


@dataclass(frozen=True)
class NodeType:
    key: str
    directory: str
    description: str = ''


@dataclass(frozen=True)
class GraphTemplate:
    id: str
    version: int
    episode_dir: str
    index_file: str
    index_title: str
    index_note: str
    index_limit: int
    index_days: int
    node_types: tuple
    kinds: tuple
    rules: tuple

    @property
    def kind_keys(self):
        return tuple(item.key for item in self.kinds)

    @property
    def node_type_keys(self):
        return tuple(item.key for item in self.node_types)

    @property
    def node_dirs(self):
        return {item.key: item.directory for item in self.node_types}

    def kind(self, key):
        return next((item for item in self.kinds if item.key == key), None)

    def has_kind(self, key):
        return self.kind(key) is not None

    def section(self, key):
        item = self.kind(key)
        return item.section if item else '其他'

    def index_label(self, key):
        item = self.kind(key)
        return item.index_label if item else '其他'

    def node_type(self, key):
        return next((item for item in self.node_types if item.key == key), None)

    def has_node_type(self, key):
        return self.node_type(key) is not None

    def node_dir(self, key):
        item = self.node_type(key)
        return item.directory if item else self.node_types[0].directory

    def node_label(self, key):
        item = self.node_type(key)
        return item.directory if item else str(key)

    def type_choices(self):
        return ' | '.join('%s（%s）' % (item.key, item.description) if item.description
                          else item.key for item in self.node_types)

    def kind_choices(self):
        return ' | '.join('%s（%s）' % (item.key, item.hint) if item.hint
                          else item.key for item in self.kinds)

    def summary(self):
        return {'id': self.id, 'version': self.version,
                'index_title': self.index_title, 'episode_dir': self.episode_dir,
                'kinds': [{'key': k.key, 'label': k.index_label,
                           'section': k.section, 'hint': k.hint} for k in self.kinds],
                'node_types': [{'key': n.key, 'label': n.directory,
                                'description': n.description} for n in self.node_types],
                'rules': len(self.rules)}


DEFAULT_TEMPLATE = GraphTemplate(
    id='default', version=1, episode_dir='对话', index_file='index.md',
    index_title='知识索引', index_note='本文件由 Butler 自动重建，手改会被覆盖。',
    index_limit=40, index_days=10,
    node_types=(NodeType('person', LEGACY_NODE_DIRS['person'], '具体的人：用户本人、朋友、同事、家人'),
                NodeType('org', LEGACY_NODE_DIRS['org'], '公司、团队、群、机构'),
                NodeType('topic', LEGACY_NODE_DIRS['topic'], '长期关注的领域或兴趣')),
    kinds=tuple(Kind(key, LEGACY_SECTIONS[key], LEGACY_INDEX[key]) for key in LEGACY_KINDS),
    rules=())


# ---------- 解析 ----------
def _frontmatter(lines):
    """返回 (meta, 正文起始行下标)。没有 frontmatter 时 meta 为空、正文从头开始。"""
    if not lines or lines[0].strip() != '---':
        return {}, 0
    for index in range(1, len(lines)):
        if lines[index].strip() == '---':
            block = '\n'.join(lines[1:index])
            try:
                data = yaml.safe_load(block) or {}
            except yaml.YAMLError as exc:
                raise TemplateError([{'line': 1, 'message': 'frontmatter 不是合法 YAML：%s' % exc}])
            if not isinstance(data, dict):
                raise TemplateError([{'line': 1, 'message': 'frontmatter 必须是键值对'}])
            return {str(k): v for k, v in data.items()}, index + 1
    raise TemplateError([{'line': 1, 'message': 'frontmatter 没有结束的 ---'}])


def _sections(lines, start):
    """按二级标题切块，保留原始行号，供报错定位。"""
    blocks, name = {}, ''
    for index in range(start, len(lines)):
        raw = lines[index]
        if raw.startswith('## '):
            name = raw[3:].strip()
            blocks.setdefault(name, [])
            continue
        if name:
            blocks[name].append((index + 1, raw))
    return blocks


def _cells(raw):
    text = raw.strip()
    if text.startswith('|'):
        text = text[1:]
    if text.endswith('|'):
        text = text[:-1]
    return [cell.strip() for cell in text.split('|')]


def _table(blocks, heading, aliases, errors, required=True):
    """解析一个二级标题下的表格，返回 [{字段: 值, '_line': 行号}]。"""
    rows = blocks.get(heading)
    if rows is None:
        if required:
            errors.append({'line': 0, 'message': '缺少「## %s」小节' % heading})
        return []
    lines = [(no, text) for no, text in rows if text.strip().startswith('|')]
    if len(lines) < 3:
        errors.append({'line': lines[0][0] if lines else 0,
                       'message': '「## %s」需要表头、分隔行和至少一行数据' % heading})
        return []
    header = _cells(lines[0][1])
    mapping, missing = {}, False
    for field, names in aliases.items():
        for name in names:
            if name in header:
                mapping[field] = header.index(name)
                break
        if field in ('description', 'hint'):
            continue
        if field not in mapping:
            errors.append({'line': lines[0][0],
                           'message': '「## %s」缺少「%s」列' % (heading, aliases[field][0])})
            missing = True
    if missing:
        return []
    out = []
    for no, text in lines[1:]:
        cells = _cells(text)
        if cells and all(SEPARATOR_RE.match(cell or '-') for cell in cells):
            continue
        if len(cells) < len(header):
            cells += [''] * (len(header) - len(cells))
        row = {field: (cells[index] if index < len(cells) else '')
               for field, index in mapping.items()}
        row['_line'] = no
        out.append(row)
    if not out:
        errors.append({'line': lines[0][0], 'message': '「## %s」没有数据行' % heading})
    return out


def _key(value, label, line, errors):
    key = str(value or '').strip()
    if not KEY_RE.match(key):
        errors.append({'line': line, 'message': '%s「%s」不合法，需匹配小写字母开头的 ^[a-z][a-z0-9_]{0,31}$'
                                                % (label, key or '空')})
        return ''
    return key


def _name(value, label, line, errors):
    text = str(value or '').strip()
    if not text:
        errors.append({'line': line, 'message': label + '不能为空'})
        return ''
    if BAD_RE.search(text):
        errors.append({'line': line, 'message': label + '不能包含 [] | # ^ 或路径分隔符：' + text})
        return ''
    if len(text) > MAX_NAME:
        errors.append({'line': line, 'message': '%s超过 %d 字：%s' % (label, MAX_NAME, text)})
        return ''
    return text


def _int(meta, key, default, low, high, errors):
    value = meta.get(key, default)
    if isinstance(value, bool):
        value = default
    try:
        value = int(value)
    except (TypeError, ValueError):
        errors.append({'line': 2, 'message': '%s 必须是整数' % key})
        return default
    if not low <= value <= high:
        errors.append({'line': 2, 'message': '%s 需在 %d 到 %d 之间' % (key, low, high)})
        return default
    return value


def _text(meta, key, default):
    value = meta.get(key, default)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


# ---------- 校验 ----------
def parse_template(text):
    """严格解析：任何问题都抛 TemplateError（带行号），供编辑页面展示。"""
    raw = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    if len(raw.encode('utf-8')) > MAX_TEMPLATE_BYTES:
        raise TemplateError([{'line': 0, 'message': '模板超过 %d KB' % (MAX_TEMPLATE_BYTES // 1024)}])
    lines = raw.split('\n')
    meta, start = _frontmatter(lines)
    errors = []
    blocks = _sections(lines, start)
    node_rows = _table(blocks, '节点目录', NODE_ALIASES, errors)
    kind_rows = _table(blocks, '分类', KIND_ALIASES, errors)
    rules = []
    for no, line in blocks.get('提炼规则', []):
        body = line.strip()
        if not body.startswith(('- ', '*')):
            continue
        rule = body[2:].strip()
        if not rule:
            continue
        if len(rule) > MAX_RULE:
            errors.append({'line': no, 'message': '提炼规则超过 %d 字' % MAX_RULE})
            continue
        rules.append(rule)
    if len(rules) > MAX_RULES:
        errors.append({'line': 0, 'message': '提炼规则最多 %d 条' % MAX_RULES})

    node_types, seen_types, dirs = [], set(), set()
    for row in node_rows:
        key = _key(row.get('type'), '节点类型 ', row['_line'], errors)
        directory = _name(row.get('directory'), '节点目录', row['_line'], errors)
        if not key or not directory:
            continue
        if key in seen_types:
            errors.append({'line': row['_line'], 'message': '节点类型重复：' + key})
            continue
        if directory in dirs:
            errors.append({'line': row['_line'], 'message': '节点目录重复：' + directory})
            continue
        seen_types.add(key)
        dirs.add(directory)
        node_types.append(NodeType(key, directory, str(row.get('description') or '').strip()[:MAX_NAME]))

    kinds, seen_kinds = [], set()
    for row in kind_rows:
        key = _key(row.get('kind'), '事实分类 ', row['_line'], errors)
        section = _name(row.get('section'), '节点小节', row['_line'], errors)
        label = _name(row.get('index_label'), '索引分类', row['_line'], errors)
        hint = str(row.get('hint') or '').strip()
        if hint and len(hint) > MAX_HINT:
            errors.append({'line': row['_line'], 'message': '提炼指引超过 %d 字' % MAX_HINT})
            hint = hint[:MAX_HINT]
        if not key or not section or not label:
            continue
        if key in seen_kinds:
            errors.append({'line': row['_line'], 'message': '事实分类重复：' + key})
            continue
        seen_kinds.add(key)
        kinds.append(Kind(key, section, label, hint))

    if not node_types:
        errors.append({'line': 0, 'message': '至少需要一个节点目录'})
    elif len(node_types) > MAX_NODE_TYPES:
        errors.append({'line': 0, 'message': '节点目录最多 %d 个' % MAX_NODE_TYPES})
    if not kinds:
        errors.append({'line': 0, 'message': '至少需要一个事实分类'})
    elif len(kinds) > MAX_KINDS:
        errors.append({'line': 0, 'message': '事实分类最多 %d 个' % MAX_KINDS})
    if node_types and 'person' not in seen_types:
        errors.append({'line': 0, 'message': '必须保留 person 节点类型，作为 subject_type 的兜底'})
    if kinds and 'topic' not in seen_kinds:
        errors.append({'line': 0, 'message': '必须保留 topic 分类，作为 kind 的兜底'})

    episode_dir = _name(_text(meta, 'episode_dir', '对话'), '对话目录', 2, errors)
    index_file = str(_text(meta, 'index_file', 'index.md'))
    if BAD_RE.search(index_file) or '/' in index_file or '\\' in index_file:
        errors.append({'line': 2, 'message': 'index_file 只能是不含路径的文件名'})
        index_file = 'index.md'
    elif not index_file.lower().endswith('.md'):
        errors.append({'line': 2, 'message': 'index_file 必须是 .md 文件'})
    if episode_dir in dirs:
        errors.append({'line': 2, 'message': '对话目录不能与节点目录重名：' + episode_dir})

    size = (sum(len(item.hint) for item in kinds) + sum(len(rule) for rule in rules)
            + sum(len(item.description) for item in node_types))
    if size > MAX_PROMPT:
        errors.append({'line': 0, 'message': '说明与规则合计 %d 字，超过提炼提示词上限 %d 字'
                                            % (size, MAX_PROMPT)})
    version = _int(meta, 'version', 1, 1, 999, errors)
    index_limit = _int(meta, 'index_limit', 40, 1, 200, errors)
    index_days = _int(meta, 'index_days', 10, 1, 90, errors)
    if errors:
        raise TemplateError(errors)

    return GraphTemplate(
        id=_text(meta, 'id', 'custom'), version=version,
        episode_dir=episode_dir, index_file=index_file,
        index_title=_text(meta, 'index_title', '知识索引'),
        index_note=_text(meta, 'index_note', '本文件由 Butler 自动重建，手改会被覆盖。'),
        index_limit=index_limit, index_days=index_days,
        node_types=tuple(node_types), kinds=tuple(kinds), rules=tuple(rules))


# ---------- 加载 ----------
_CACHE, _WARNED = {}, set()
_CACHE_LOCK = threading.Lock()


def _warn_once(key, log, message):
    if log is None:
        return
    with _CACHE_LOCK:
        if key in _WARNED:
            return
        _WARNED.add(key)
    log(message)


def _read(path, log):
    path = Path(path)
    try:
        stat = path.stat()
    except OSError:
        return None
    stamp = (str(path), stat.st_mtime_ns, stat.st_size)
    with _CACHE_LOCK:
        hit = _CACHE.get(stamp)
    if hit is not None:
        return hit
    try:
        text = path.read_text('utf-8', 'replace')
    except OSError:
        return None
    try:
        template = parse_template(text)
    except TemplateError as exc:
        _warn_once(stamp, log, '知识图谱模板无效，已回退默认：%s（%s）' % (path, exc))
        return None
    with _CACHE_LOCK:
        for key in [k for k in _CACHE if k[0] == str(path)]:
            _CACHE.pop(key, None)
        _CACHE[stamp] = template
    return template


def resolve_template(override=None, log=None):
    """返回 (模板, 实际生效来源, 路径)；来源是 override / plugin / builtin。

    覆盖层存在但解析失败时，真实生效的是内置模板，所以来源必须是 plugin，
    否则页面会把一份无效的覆盖层当成当前生效内容。
    """
    for path, source in ((override, 'override'), (BUILTIN_TEMPLATE, 'plugin')):
        if path is None:
            continue
        template = _read(path, log)
        if template is not None:
            return template, source, Path(path)
    _warn_once('__fallback__', log, '没有可用的知识图谱模板文件，使用代码内置默认')
    return DEFAULT_TEMPLATE, 'builtin', None


def load_template(override=None, log=None):
    """取当前生效模板；覆盖层坏了退回内置，内置坏了退回常量，绝不抛异常。"""
    return resolve_template(override, log)[0]


def mtime(path):
    try:
        return round(Path(path).stat().st_mtime, 3)
    except OSError:
        return 0.0
