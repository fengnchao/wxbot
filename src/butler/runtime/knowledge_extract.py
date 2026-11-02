"""从 L1 原文提炼知识图谱节点：一批原文交给模型，产出实体、关系与事实写进 vault。

为什么单独一个模块：提炼是离线批处理，跑在 CLI 里，不挂在回复链路上、不新增线程。
为什么不让管理台触发：一次提炼要跑模型几十秒，管理台只读，写路径统一收在 Butler 侧。

`complete` 回调由调用方注入：CLI 传真实模型，测试传假实现，两边共用同一套解析与写入。

产出里的 `subject` 决定这条事实写到哪个节点，`links` 决定正文里生成哪些 [[双链]]——
没有这两项，写出来的只是一堆孤立的事实行，Obsidian 的 graph view 连不起来。
"""
from __future__ import annotations

import json
import re

from butler.runtime.knowledge_template import (DEFAULT_TEMPLATE, LEGACY_KINDS,
                                                LEGACY_NODE_DIRS)

MAX_BATCH = 200
MAX_VALUE = 500
MAX_KEY = 80
MAX_QUOTE = 300
MAX_LINKS = 8
# 默认值；实际提炼用模板里的分类与节点类型。
KINDS = LEGACY_KINDS
NODE_TYPES = tuple(LEGACY_NODE_DIRS)

# 内置安全规则不可删，模板的「## 提炼规则」只能追加在它们后面。
CORE_RULES = (
    '只提取文中「用户」说过、且值得长期保留的信息。助理的回复只用于理解语境，绝不能作为事实来源。',
    '不推测、不补全、不替用户下结论。原文没说的事一律不写。',
    '同一件事在不同时间说法矛盾时，各写一条，不要合并、不要取舍。',
    '寒暄、确认、临时安排（如这一刻的天气、当下的情绪）不算事实，不要输出。',
    'links 只收原文里明确出现过的对象，不要为了连通而编造关系。',
    '确实没有值得记住的内容时，输出 []。',
)

PROMPT_HEAD = """下面是一个人和助理的若干轮对话，每条前面有编号。当前用户的名字是「%s」。
请从中提炼值得长期记住的事实，并把它们挂到知识图谱的节点上。

只输出一个 JSON 数组，不要代码块围栏，不要任何解释。每项字段：
  kind: %s
  subject: 这条事实说的是谁或什么。说当前用户本人时写他的名字「%s」
  subject_type: %s
  key: 这件事的短名字，不超过 20 字；同一件事反复出现时用同一个名字
  value: 一句完整陈述，用第三人称，不超过 100 字；提到别人时写对方名字原文，不要加方括号
  links: 这条事实里提到的其他人、组织或话题，数组，元素形如 {"name":"李四","type":"person"}；
         没有就给 []
  quote: 支撑这条的用户原话片段，不超过 60 字
  confidence: 0 到 1 之间的小数
"""


def build_prompt(template, contact):
    """模板决定分类、节点类型与追加规则；内置安全规则永远在前。"""
    rules = list(CORE_RULES) + list(template.rules)
    numbered = '\n'.join('%d. %s' % (index, rule) for index, rule in enumerate(rules, 1))
    return (PROMPT_HEAD % (contact, template.kind_choices(), contact,
                           template.type_choices())
            + '\n规则：\n' + numbered + '\n\n对话如下：\n')


def _clean(value, limit):
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def _links(raw, types=NODE_TYPES):
    """links 允许字符串或 {"name","type"} 两种写法，模型两种都见过。"""
    items = raw if isinstance(raw, list) else []
    out = []
    for item in items[:MAX_LINKS]:
        if isinstance(item, str):
            name, kind = item, 'person'
        elif isinstance(item, dict):
            name, kind = item.get('name'), item.get('type')
        else:
            continue
        name = _clean(name, MAX_KEY)
        if name:
            out.append({'name': name, 'type': kind if kind in types else 'person'})
    return out


def parse_facts(raw, kinds=None, node_types=None):
    """从模型输出里取出 JSON 数组；容忍围栏与前后废话，坏项直接丢弃。

    kinds/node_types 是模板白名单：不在其中的值会降级到 topic/person，
    而不是直接丢掉整条事实——宁可选错分类，也不能漏记用户说过的话。
    """
    allowed_kinds = tuple(kinds or KINDS)
    allowed_types = tuple(node_types or NODE_TYPES)
    fallback_kind = 'topic' if 'topic' in allowed_kinds else allowed_kinds[0]
    fallback_type = 'person' if 'person' in allowed_types else allowed_types[0]
    text = str(raw or '')
    start, end = text.find('['), text.rfind(']')
    if start < 0 or end <= start:
        return []
    try:
        items = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    facts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = _clean(item.get('value'), MAX_VALUE)
        if not value:
            continue
        kind = str(item.get('kind') or 'topic').strip()
        node_type = str(item.get('subject_type') or 'person').strip()
        try:
            confidence = float(item.get('confidence', 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        facts.append({
            'kind': kind if kind in allowed_kinds else fallback_kind,
            'subject': _clean(item.get('subject'), MAX_KEY),
            'subject_type': node_type if node_type in allowed_types else fallback_type,
            'fact_key': _clean(item.get('key'), MAX_KEY),
            'fact_value': value,
            'links': _links(item.get('links'), allowed_types),
            'quote': _clean(item.get('quote'), MAX_QUOTE),
            'confidence': max(0.0, min(1.0, confidence)),
        })
    return facts


def render(rows):
    """把原文排成带编号的对话；编号让模型能对上 quote，也方便回看。"""
    lines = []
    for row in rows:
        reply = _clean(row.get('reply_text'), 300)
        lines.append('[%s] 用户：%s' % (row.get('id'), _clean(row.get('user_text'), 1000)))
        lines.append('     助理：%s' % (reply or '（无回复）'))
    return '\n'.join(lines)


def extract(store, owner, contact, complete, *, batch=40, log=None, dry_run=False):
    """提炼一个 owner 的一段新原文，返回 (读取条数, 写入条数, 解析条数)。

    游标只在整批成功后才前移：解析出 0 条也算成功，避免同一批反复重试烧模型。
    解析失败（模型给了非 JSON）不前移，下次还能重来。
    """
    log = log or (lambda *a, **k: None)
    batch = max(1, min(MAX_BATCH, int(batch)))
    since = store.extracted_at(owner)
    rows = store.episodes_of(owner, after_at=since, limit=batch)
    if not rows:
        return 0, 0, 0
    last_at = max(float(row['at']) for row in rows)
    template = getattr(store, 'template', None) or DEFAULT_TEMPLATE
    raw = complete(build_prompt(template, contact) + render(rows))
    facts = parse_facts(raw, template.kind_keys, template.node_type_keys)
    if raw and '[' not in str(raw) and ']' not in str(raw):
        log('[%s] 提炼结果无法解析，游标不前移：%r', owner, str(raw)[:120])
        return len(rows), 0, 0
    written = 0
    for fact in facts:
        if dry_run:
            log('[dry-run] %s %s', fact['kind'], fact['fact_value'])
            continue
        if store.add_fact(owner, contact, fact['fact_value'], kind=fact['kind'],
                          fact_key=fact['fact_key'], quote=fact['quote'],
                          episode_at=rows[0].get('at'), confidence=fact['confidence'],
                          subject=fact['subject'], subject_type=fact['subject_type'],
                          links=[link['name'] for link in fact['links']]):
            written += 1
    if not dry_run:
        store.set_extracted_at(owner, last_at)
    return len(rows), written, len(facts)


def extract_all(store, complete, *, batch=40, owner='', log=None, dry_run=False):
    """遍历目录里所有人。单人失败不影响其他人，失败原因写进返回值。"""
    log = log or (lambda *a, **k: None)
    report = []
    for entry in store.owners():
        if owner and entry['owner'] != owner:
            continue
        try:
            read, written, parsed = extract(
                store, entry['owner'], entry['contact'], complete,
                batch=batch, log=log, dry_run=dry_run)
        except Exception as exc:                     # 一个人出错不该中断整批
            log('[%s] 提炼失败：%s', entry['owner'], exc)
            report.append({'owner': entry['owner'], 'contact': entry['contact'],
                           'read': 0, 'written': 0, 'parsed': 0,
                           'error': type(exc).__name__})
            continue
        report.append({'owner': entry['owner'], 'contact': entry['contact'],
                       'read': read, 'written': written, 'parsed': parsed})
    return report
