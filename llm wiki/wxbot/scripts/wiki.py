"""Local Markdown graph tools. Semantic ingestion is performed by the coding agent."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import yaml

from common.paths import REPO_ROOT

KINDS = {'modules': 'module', 'apis': 'api', 'tables': 'table',
         'symbols': 'symbol', 'concepts': 'concept'}
SECTIONS = ('目标与背景', '文件与代码位置', '接口与字段', '数据库与迁移',
            '前端消费点', '测试与异步任务', '风险与回滚')
LINK = re.compile(r'\[\[([^\]\n]+)\]\]')
SLUG = re.compile(r'[\w\-]+', re.UNICODE)


def today():
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def digest(path):
    # Normalize line endings: Git may convert LF to CRLF on this Windows repo.
    return hashlib.sha256(path.read_text(encoding='utf-8-sig').replace('\r\n', '\n').encode()).hexdigest()


def inside(root, relative):
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError(f'非法相对路径: {relative}')
    pure = PurePosixPath(relative)
    if pure.is_absolute() or '..' in pure.parts or not pure.parts:
        raise ValueError(f'路径越界: {relative}')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'路径越界: {relative}')
    if path != root.resolve().joinpath(*pure.parts):
        raise ValueError(f'拒绝符号链接或目录联接重定向: {relative}')
    return path


def read_note(path):
    text = path.read_text(encoding='utf-8-sig')
    match = re.match(r'\A---\n(.*?)\n---(?:\n|$)', text, re.S)
    if not match:
        raise ValueError(f'缺少 YAML 元信息: {path.name}')
    meta = yaml.safe_load(match[1])
    if not isinstance(meta, dict):
        raise ValueError(f'元信息必须是对象: {path.name}')
    return meta, text


def note_text(meta, body):
    return '---\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + '---\n' + body


def links(text):
    text = re.sub(r'(?ms)^ *(`{3,}|~{3,})[^\n]*\n.*?^ *\1[ \t]*(?:\n|$)', '', text)
    text = re.sub(r'(`+).*?\1', '', text, flags=re.S)
    return {m.split('|', 1)[0].split('#', 1)[0].removesuffix('.md')
            for m in LINK.findall(text) if m.split('|', 1)[0].split('#', 1)[0]}


class Wiki:
    def __init__(self, root):
        self.root = root.resolve()
        self.vault = inside(self.root, 'llm wiki/wxbot')
        if self.vault != self.root / 'llm wiki/wxbot':
            raise ValueError('图谱目录不能通过符号链接重定向到其它目录')
        self.pages = {}
        for folder in KINDS:
            for path in sorted((self.vault / folder).glob('*.md')):
                path = inside(self.vault, path.relative_to(self.vault).as_posix())
                key = path.relative_to(self.vault).with_suffix('').as_posix()
                self.pages[key] = (path, *read_note(path))
        self.state_path = inside(self.vault, 'ingest-state.json')
        self.state = json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {
            'version': 1, 'records': {}, 'pages': {}}
        if (self.state.get('version') != 1 or not isinstance(self.state.get('records'), dict)
                or not isinstance(self.state.get('pages'), dict)):
            raise ValueError('不支持或损坏的 ingest-state.json')

    def source(self, spec):
        relative = spec['path']
        path = inside(self.root, relative)
        if path.relative_to(self.root).as_posix() != PurePosixPath(relative).as_posix():
            raise ValueError(f'来源不能通过符号链接或目录联接重定向: {relative}')
        parts = PurePosixPath(relative).parts
        allowed = parts[0] in {'src', 'web', 'scripts', 'tools', 'plugins'} or relative in {
            'README.md', 'AGENTS.md', 'pyproject.toml'} or relative.startswith('llm wiki/wxbot/scripts/') or (
                len(parts) == 1 and path.name.startswith('config.') and path.name.endswith('.example.toml'))
        if (not allowed or any(p.startswith('.') for p in parts)
                or any(p in {'node_modules', 'dist', '__pycache__'} for p in parts)
                or path.suffix.lower() not in {'.py', '.js', '.mjs', '.vue', '.css', '.md', '.toml', '.ps1'}
                or path.name == 'auth.json' or (path.suffix == '.toml' and path.name.startswith('config.')
                                               and '.example.' not in path.name)):
            raise ValueError(f'禁止读取此来源: {relative}')
        return path

    def structural(self):
        issues = []
        for key, (path, meta, text) in self.pages.items():
            def issue(code, detail):
                issues.append(f'{code}: {key}: {detail}')
            if meta.get('type') != KINDS[key.split('/')[0]]:
                issue('metadata', 'type 与目录不符')
            for field in ('module', 'summary', 'last_verified', 'sources', 'changes'):
                if not meta.get(field):
                    issue('metadata', f'缺少 {field}')
            try:
                date.fromisoformat(str(meta.get('last_verified')))
            except ValueError:
                issue('metadata', 'last_verified 必须是 YYYY-MM-DD')
            if not isinstance(meta.get('sources'), list):
                issue('metadata', 'sources 必须是列表')
            else:
                for spec in meta['sources']:
                    try:
                        source = self.source(spec)
                    except (ValueError, KeyError, TypeError) as exc:
                        issue('source-path', str(exc))
                        continue
                    if not source.is_file():
                        issue('source-missing', spec['path'])
                        continue
                    rows = source.read_text(encoding='utf-8-sig').splitlines()
                    line, anchor = spec.get('line'), spec.get('anchor')
                    if type(line) is not int or not 1 <= line <= len(rows):
                        issue('source-line', f"{spec['path']}:{line}")
                    elif not isinstance(anchor, str) or not anchor or anchor not in rows[line - 1]:
                        issue('source-anchor', f"{spec['path']}:{line} 与锚点不符")
            if not isinstance(meta.get('changes'), list):
                issue('metadata', 'changes 必须是列表')
            else:
                for record in meta['changes']:
                    try:
                        if not record.startswith('raw/changes/') or not inside(self.vault, record + '.md').is_file():
                            issue('provenance', f'找不到修改来源 {record}')
                    except (ValueError, AttributeError, TypeError) as exc:
                        issue('provenance', str(exc))
                for record, saved in self.state['records'].items():
                    if key in saved['pages'] and record not in meta['changes']:
                        issue('provenance-history', f'不可删除历史修改来源 {record}')
            for target in links(text):
                try:
                    if not inside(self.vault, target + '.md').is_file():
                        issue('broken-link', target)
                except ValueError:
                    issue('broken-link', target)
            for relation, reverse in (('calls', 'called_by'), ('called_by', 'calls')):
                targets = meta.get(relation, [])
                if not isinstance(targets, list):
                    issue('relation', f'{relation} 必须是列表')
                    continue
                for target in targets:
                    if not isinstance(target, str) or target not in self.pages:
                        issue('relation', f'{relation}: 缺少词条 {target}')
                    elif key not in self.pages[target][1].get(reverse, []):
                        issue('reverse-link', f'{target} 缺少 {reverse}: {key}')
        # Only explicit architectural dependencies participate; Markdown backlinks do not.
        visited, active = set(), set()
        def visit(key):
            if key in active:
                issues.append(f'dependency-cycle: {key}')
                return
            if key in visited:
                return
            active.add(key)
            for target in self.pages[key][1].get('depends_on', []):
                if target not in self.pages:
                    issues.append(f'dependency-missing: {key}: {target}')
                else:
                    visit(target)
            active.remove(key)
            visited.add(key)
        for key in self.pages:
            visit(key)
        incoming = set().union(*(links(text) for _, _, text in self.pages.values())) if self.pages else set()
        for key, (_, meta, _) in self.pages.items():
            if key not in incoming and meta.get('root') is not True:
                issues.append(f'orphan-page: {key}: 没有词条入链，请从所属模块链接')
        # Entry pages were checked above; also check navigation, raw, and impact reports.
        for path in sorted(self.vault.rglob('*.md')):
            relative = path.relative_to(self.vault)
            if relative.parts[0] in {*KINDS, 'templates', '.obsidian'}:
                continue
            path = inside(self.vault, relative.as_posix())
            for target in links(path.read_text(encoding='utf-8-sig')):
                try:
                    exists = inside(self.vault, target + '.md').is_file()
                except ValueError:
                    exists = False
                if not exists:
                    issues.append(f'broken-link: {relative.with_suffix("").as_posix()}: {target}')
        return issues

    def audit(self):
        issues = self.structural()
        for path in sorted((self.vault / 'raw/changes').glob('*.md')):
            path = inside(self.vault, path.relative_to(self.vault).as_posix())
            key = path.relative_to(self.vault).with_suffix('').as_posix()
            record = self.state['records'].get(key)
            if record is None:
                issues.append(f'pending-change: {key}')
            elif digest(path) != record['sha256']:
                issues.append(f'raw-modified: {key}: 请新增更正记录，勿改写已入库历史')
        for key in self.state['records']:
            if not inside(self.vault, key + '.md').is_file():
                issues.append(f'raw-missing: {key}')
        for key, (path, meta, _) in self.pages.items():
            saved = self.state['pages'].get(key)
            if saved is None:
                issues.append(f'untracked-page: {key}')
                continue
            if digest(path) != saved['sha256']:
                issues.append(f'page-drift: {key}: 词条变更尚未入库')
            for relative, old in saved['sources'].items():
                source = self.source({'path': relative})
                if source.is_file() and digest(source) != old:
                    issues.append(f'source-drift: {key}: {relative}: 需要对照代码复核并新增修改记录')
        for key in self.state['pages'].keys() - self.pages.keys():
            issues.append(f'page-missing: {key}: 请通过迁移记录修复引用，禁止静默遗失')
        return issues

    def append_log(self, action, title, detail):
        with inside(self.vault, 'changelog.md').open('a', encoding='utf-8', newline='\n') as out:
            out.write(f'\n## [{today()}] {action} | {title}\n\n{detail}\n')

    def index(self):
        rows = ['# 项目知识图谱', '', '先读 [[guide]]；覆盖范围见 [[coverage]]。代码是事实源，词条是经过核对的导航。', '']
        for folder, kind in KINDS.items():
            rows += [f'## {folder} / {kind}', '', '| 词条 | 简介 | 首个来源 | 最后核对 |', '|---|---|---|---|']
            for key, (_, meta, _) in sorted(self.pages.items()):
                if key.startswith(folder + '/'):
                    source = meta['sources'][0]
                    summary = str(meta['summary']).replace('|', ' / ').replace('\n', ' ')
                    rows.append(f"| [[{key}]] | {summary} | `{source['path']}:{source['line']}` | {meta['last_verified']} |")
            rows.append('')
        rows += ['## 影响分析与台账', '', '影响报告包含待核对的草稿，不能当成已验证的业务结论。', '']
        for folder in ('impacts', 'raw/changes'):
            rows += [f'- [[{p.relative_to(self.vault).with_suffix("").as_posix()}]]'
                     for p in sorted((self.vault / folder).glob('*.md'))]
        inside(self.vault, 'index.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')

    def ingest(self, name):
        if not SLUG.fullmatch(name):
            raise ValueError('ingest 只接受 raw/changes 中的文件名（不含 .md）')
        record_key = 'raw/changes/' + name
        record_path = inside(self.vault, record_key + '.md')
        meta, text = read_note(record_path)
        old = self.state['records'].get(record_key)
        if old:
            if digest(record_path) != old['sha256']:
                raise ValueError('raw-modified: 已入库修改记录不能覆写；请新增更正记录')
            issues = self.audit()
            if issues:
                return issues
            print('already-ingested: ' + record_key)
            return []
        issues = self.structural()
        if meta.get('type') != 'change' or not meta.get('title'):
            issues.append('change-metadata: 需要 type: change 与 title')
        headings = {m.group(1): m.group(2).strip() for m in
                    re.finditer(r'^## ([^\n]+)\n(.*?)(?=^## |\Z)', text, re.M | re.S)}
        for section in SECTIONS:
            if not headings.get(section) or '待填写' in headings[section]:
                issues.append(f'change-section: 缺少内容: {section}')
        pages = meta.get('pages')
        if not isinstance(pages, list) or not pages:
            issues.append('change-pages: pages 必须列出本次已核对并更新的词条')
            pages = []
        for key in pages:
            if not isinstance(key, str) or key not in self.pages:
                issues.append(f'change-page: 不存在 {key}')
            elif record_key not in self.pages[key][1].get('changes', []):
                issues.append(f'provenance: {key} 未声明本次修改来源 {record_key}')
        # Existing immutable records must still match, even when ingesting a new one.
        for key, saved in self.state['records'].items():
            path = inside(self.vault, key + '.md')
            if not path.is_file() or digest(path) != saved['sha256']:
                issues.append(f'raw-modified: {key}')
        if issues:
            return issues
        for key in pages:
            path, page, _ = self.pages[key]
            self.state['pages'][key] = dict(sha256=digest(path), sources={
                spec['path']: digest(self.source(spec)) for spec in page['sources']})
        self.state['records'][record_key] = dict(sha256=digest(record_path), pages=pages, date=today())
        self.index()
        self.append_log('ingest', str(meta['title']), f'来源：[[{record_key}]]\n\n' +
                        '、'.join(f'[[{key}]]' for key in pages))
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'ingested: {record_key} ({len(pages)} pages)')
        return []

    def query(self, keywords, depth, limit, save):
        terms = [term.casefold() for term in keywords if term.strip()]
        if not terms:
            raise ValueError('至少输入一个非空关键词')
        scores = {key: sum(3 * (term in key.casefold() or term in str(meta.get('summary', '')).casefold())
                           + (term in text.casefold()) for term in terms)
                  for key, (_, meta, text) in self.pages.items()}
        hits = sorted((key for key in scores if scores[key]), key=lambda key: (-scores[key], key))[:limit]
        selected, frontier = set(hits), set(hits)
        edges = {key: links(text) & self.pages.keys() for key, (_, _, text) in self.pages.items()}
        for _ in range(depth):
            neighbors = set().union(*(edges[key] for key in frontier)) if frontier else set()
            neighbors.update(key for key, targets in edges.items() if targets & frontier)
            frontier = neighbors - selected
            selected.update(frontier)
        body = ['# 改前影响面候选（draft）', '', '关键词：' + '、'.join(keywords), '',
                '以下是检索候选，须读词条并核对当前代码后补齐报告。', '']
        for key in hits + sorted(selected - set(hits)):
            _, meta, _ = self.pages[key]
            refs = '、'.join(f"`{s['path']}:{s['line']}`" for s in meta.get('sources', []))
            body += [f'- [[{key}]]：{meta.get("summary", "")}；{refs}']
        if not hits:
            body += ['未命中；回到源码定位，记录覆盖缺口，建档后再做影响分析。']
        body += ['', '## 要改的文件与调用方', '', '待核对：上述候选及其调用关系。', '',
                 '## 接口与前端消费点', '', '待核对：请求/响应字段、页面、类型与兼容性。', '',
                 '## 数据库与字段血缘', '', '待核对：表/字段、迁移及冗余来源；不涉及时写明不涉及。', '',
                 '## 测试、异步任务与风险', '', '待核对：覆盖、定时任务、消费者、回滚和已知盲区。', '']
        rendered = '\n'.join(body)
        if save:
            if not SLUG.fullmatch(save):
                raise ValueError('save 必须是安全的短主题名，不含路径')
            path = inside(self.vault, f'impacts/{today()}-{save}.md')
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8') as out:
                out.write(note_text(dict(type='impact', status='draft', date=today()), rendered))
            self.append_log('query', save, f'报告：[[impacts/{path.stem}]]')
            self.index()
        print(rendered)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=REPO_ROOT, help='默认 common.paths.REPO_ROOT；测试可指定临时库')
    sub = parser.add_subparsers(dest='command', required=True)
    query = sub.add_parser('query', help='关键词查询，双向展开关联；默认只读')
    query.add_argument('keywords', nargs='+')
    query.add_argument('--depth', type=int, choices=(0, 1, 2), default=1)
    query.add_argument('--limit', type=int, default=8)
    query.add_argument('--save', metavar='SLUG', help='显式保存 draft 影响报告并追加 query 日志')
    change = sub.add_parser('change', help='创建追加式修改记录骨架，禁止覆写')
    change.add_argument('slug')
    change.add_argument('--title', required=True)
    change.add_argument('--date', default=today())
    ingest = sub.add_parser('ingest', help='核对已人工更新的词条，登记来源快照并刷新索引/日志')
    ingest.add_argument('record', help='raw/changes 内文件名，不含 .md')
    sub.add_parser('lint', help='只读一致性巡检；发现问题退出 1')
    sub.add_parser('status', help='只读查看覆盖与未入库修改记录')
    args = parser.parse_args(argv)
    try:
        wiki = Wiki(args.repo_root)
        if args.command == 'query':
            if not 1 <= args.limit <= 100:
                raise ValueError('limit 必须在 1..100')
            wiki.query(args.keywords, args.depth, args.limit, args.save)
        elif args.command == 'change':
            if not SLUG.fullmatch(args.slug):
                raise ValueError('slug 不得含路径')
            date.fromisoformat(args.date)
            path = inside(wiki.vault, f'raw/changes/{args.date}-{args.slug}.md')
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8') as out:
                out.write(note_text(dict(type='change', title=args.title, pages=[]),
                                   f'# {args.title}\n\n' + '\n'.join(f'## {s}\n\n待填写\n' for s in SECTIONS)))
            wiki.append_log('change', args.title, f'来源：[[raw/changes/{path.stem}]]')
            print(path)
        elif args.command in ('lint', 'ingest'):
            issues = wiki.audit() if args.command == 'lint' else wiki.ingest(args.record)
            print('\n'.join(issues) if issues else 'OK')
            return int(bool(issues))
        else:
            print(f'pages: {len(wiki.pages)}; ingested changes: {len(wiki.state["records"])}')
            print('\n'.join(i for i in wiki.audit() if i.startswith('pending-change:')) or 'pending changes: 0')
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError) as exc:
        print(f'wiki-error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
