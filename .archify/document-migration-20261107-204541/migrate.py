"""Stage and verify the explicitly requested project-document consolidation.

This script never deletes source files. Cleanup is a separate, path-checked step.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
STAGED = WORK / "staged"
DATE = "2026-11-07"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory():
    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, text=True, encoding="utf-8")
    return sorted({s for s in raw.split("\0") if s.lower().endswith(".md") and not s.startswith(".archify/") and (ROOT / s).is_file()})


def checked(relative):
    path = ROOT / relative
    if path.is_symlink() or path.resolve() != ROOT.joinpath(*Path(relative).parts):
        raise ValueError(f"Refusing redirected path: {relative}")
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError(f"Outside repository: {relative}")
    return path


def headings(text):
    """Return Markdown headings, excluding fenced examples and YAML frontmatter."""
    found = []
    fence = None
    front = text.startswith("---\n")
    for i, line in enumerate(text.splitlines(keepends=True)):
        if front:
            if i and line.rstrip() == "---":
                front = False
            continue
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            char = match[1][0]
            if fence is None:
                fence = (char, len(match[1]))
            elif fence[0] == char and len(match[1]) >= fence[1] and not line[match.end():].strip():
                fence = None
            continue
        match = re.match(r"^(#{1,6}) (.+?)\s*$", line)
        if not fence and match:
            found.append((i, len(match[1]), match[2]))
    return found


def readme_node(stack):
    top = stack.get(2, "")
    sub = stack.get(3, "")
    detail = stack.get(4, "")
    if top == "模块与文件职责":
        if sub.startswith("src/butler"):
            if "identity/" in detail: return "identity-tools"
            if "delivery/" in detail or "runtime/" in detail or "telegram/" in detail: return "butler-functions"
            if "backends/" in detail: return "model-backends"
            return "butler"
        if sub.startswith("src/dashboard") or sub.startswith("web/"): return "dashboard"
        if sub.startswith("src/wxbot"):
            if "wechat/" in detail: return "wechat-ui"
            if "processor/" in detail: return "queue-worker"
            return "wxbot"
        if sub.startswith("plugins/"): return "resident-skills"
        return "wxbot"
    if top == "接口与协议": return "dashboard" if "管理台" in sub else "butler"
    if top == "配置": return "configuration"
    if top == "知识库": return "knowledge-vault"
    if top == "管理台": return "identity-tools" if "联系人" in sub else "dashboard"
    if top == "微信 UI 与队列": return "index-tts" if "IndexTTS" in sub else "wechat-ui"
    if top == "Telegram 通道": return "butler-functions"
    if top == "小潮常驻角色": return "resident"
    return "wxbot"


EXACT = {
    "modules/butler": "butler", "modules/common": "wxbot", "modules/dashboard": "dashboard",
    "modules/delivery": "butler-functions", "modules/identity": "identity-tools",
    "modules/models": "model-backends", "modules/plugin": "resident-skills",
    "modules/runtime": "butler-functions", "modules/telegram": "butler-functions",
    "modules/web": "dashboard", "modules/wiki": "wxbot", "modules/wxbot": "wxbot",
    "apis/dashboard-contact-policy": "identity-tools", "apis/dashboard-knowledge": "knowledge-vault",
    "apis/dashboard-queue": "queue-storage", "apis/dashboard-resident-diary": "resident",
    "apis/dashboard-voice-assets": "delivery-voice", "apis/dashboard-workflow": "dashboard",
    "apis/index-tts": "index-tts", "apis/butler-handle": "butler", "apis/butler-handle-stream": "butler",
    "concepts/architecture-node-notes": "wxbot", "concepts/automatic-voice-reply": "delivery-voice",
    "concepts/capture-viewport": "wechat-ui", "concepts/delivery-state": "delivery-pump",
    "concepts/development-baseline": "wxbot", "concepts/group-identity-evidence": "identity-tools",
    "concepts/identity-authority": "identity-tools", "concepts/message-pipeline": "wxbot",
    "concepts/model-error-contract": "model-backends", "concepts/unread-capture-retry": "wechat-ui",
    "concepts/voice-asset-binding": "delivery-voice",
    "symbols/butler-handle": "butler", "symbols/butler-processor": "queue-worker", "symbols/butler-result": "butler",
    "symbols/delivery-handlers": "delivery-pump", "symbols/delivery-pump": "delivery-pump",
    "symbols/knowledge-auto": "conversation-extraction", "symbols/knowledge-extract": "conversation-extraction",
    "symbols/knowledge-template": "knowledge-vault", "symbols/local-model-backend": "model-backends",
    "symbols/mention-selection": "wechat-ui", "symbols/model-worker": "queue-worker",
    "symbols/queue-finish": "outbox-text", "symbols/queue-store": "queue-storage",
    "symbols/reloadable-backend": "model-backends", "symbols/resident-role": "resident",
    "symbols/voice-asset-store": "delivery-voice",
    "tables/kb-episodes": "knowledge-vault", "tables/kb-facts": "knowledge-vault",
    "tables/kb-owners": "knowledge-vault", "tables/knowledge-vault": "knowledge-vault",
    "tables/queue-batches": "queue-worker", "tables/queue-inbox": "inbox", "tables/queue-outbox": "queue-storage",
}


def historical_node(name):
    if "resident" in name or "xiaochao" in name: return "resident"
    if "delivery-handlers" in name: return "delivery-pump"
    if "architecture" in name or "archify" in name or "graph-bootstrap" in name: return "wxbot"
    if "knowledge-auto" in name: return "conversation-extraction"
    if "knowledge" in name: return "knowledge-vault"
    if "contact-enrollment" in name or "group-binding" in name or "contact-policy" in name or "group-identity" in name or "identity-placeholder" in name: return "identity-tools"
    if "index-tts" in name or "indextts" in name or "webui-preset" in name: return "index-tts"
    if "voice" in name: return "delivery-voice"
    if "model" in name: return "model-backends"
    if "mention" in name or "unread" in name: return "wechat-ui"
    if "ui-snapshot" in name or "details-whitelist" in name: return "delivery-pump"
    if "queue-batches" in name: return "queue-worker"
    if "web-global" in name: return "dashboard"
    return "wxbot"


def owner(source):
    if source == "tools/voice-ptt-ops.md": return "delivery-voice"
    if source == "tools/indextts-ops.md": return "index-tts"
    key = source.removeprefix("llm wiki/wxbot/").removesuffix(".md")
    if key in EXACT: return EXACT[key]
    if key == "model-switch-verification": return "model-backends"
    if source.startswith("docs/") or key.startswith(("raw/changes/", "impacts/")):
        return historical_node(Path(source).stem)
    return "wxbot"


def sections(source, text):
    lines = text.splitlines(keepends=True)
    if source != "README.md":
        return [(0, len(lines), owner(source), next((h[2] for h in headings(text)), Path(source).stem))]
    hs = [h for h in headings(text) if h[1] <= 4]
    starts = sorted({0, *(h[0] for h in hs), len(lines)})
    stack = {}
    by_line = {h[0]: h for h in hs}
    result = []
    for a, b in zip(starts, starts[1:]):
        if a in by_line:
            _, level, label = by_line[a]
            stack = {k: v for k, v in stack.items() if k < level}
            stack[level] = label
        result.append((a, b, readme_node(stack), " / ".join(stack.values()) or "项目简介"))
    assert "".join("".join(lines[a:b]) for a, b, _, _ in result) == text
    return result


def outside_fences(text, transform):
    out = []
    fence = None
    for line in text.splitlines(keepends=True):
        m = re.match(r"^\s*(`{3,}|~{3,})", line)
        if m:
            if fence is None: fence = (m[1][0], len(m[1]))
            elif fence[0] == m[1][0] and len(m[1]) >= fence[1] and not line[m.end():].strip(): fence = None
            out.append(line)
        else:
            out.append(line if fence else transform(line))
    return "".join(out)


def prepare():
    if (WORK / "manifest.json").exists() and "--restage" not in sys.argv:
        raise SystemExit("A frozen migration already exists; use verify/apply, do not restage edited sources.")
    if (WORK / "manifest.json").exists():
        frozen = json.loads((WORK / "manifest.json").read_text("utf-8"))
        for item in frozen["sources"] + frozen["notes_before"] + frozen["preserved"]:
            assert sha(checked(item["path"]).read_bytes()) == item["sha256"], item["path"]
    all_md = inventory()
    sources = [s for s in all_md if s == "README.md" or s.startswith(("llm wiki/wxbot/", "docs/")) or s in ("tools/README.md", "tools/voice-ptt-ops.md", "tools/indextts-ops.md")]
    preserved = [s for s in all_md if s not in sources and not s.startswith("architecture-notes/")]
    texts = {s: checked(s).read_text(encoding="utf-8-sig") for s in sources}
    notes = {Path(s).stem: checked(s).read_text(encoding="utf-8-sig") for s in all_md if s.startswith("architecture-notes/")}
    titles = {key: next((h[2] for h in headings(t)), key) for key, t in notes.items()}
    titles.update({"model-backends": "可切换模型后端", "identity-tools": "联系人身份与业务工具", "knowledge-vault": "用户知识 vault", "configuration": "配置管理"})
    chunks = []
    manifest = {"version": 1, "date": DATE, "repository_root": str(ROOT), "sources": [], "preserved": [], "notes_before": [], "parts": [], "notes": {}}
    for source in sources:
        lines = texts[source].splitlines(keepends=True)
        parts = []
        for a, b, node, label in sections(source, texts[source]):
            content = "".join(lines[a:b])
            ident = "doc-" + sha(f"{source}:{a}:{b}".encode())[:14]
            part = {"id": ident, "source": source, "line": a + 1, "end_line": b,
                    "node": node, "label": label, "sha256": sha(content.encode()), "characters": len(content)}
            parts.append(ident)
            chunks.append((part, content))
        manifest["sources"].append({"path": source, "sha256": sha(checked(source).read_bytes()), "bytes": checked(source).stat().st_size, "parts": parts})
    first = {}
    for part, _ in chunks:
        first.setdefault(part["source"], (part["node"] + ".md", part["id"]))
    wiki = {s.removeprefix("llm wiki/wxbot/").removesuffix(".md"): target for s, target in first.items() if s.startswith("llm wiki/wxbot/")}

    def rewrite(content, source):
        def line_rewrite(line):
            def wiki_link(match):
                value, _, alias = match[1].partition("|")
                key = value.split("#", 1)[0].removesuffix(".md")
                target = wiki.get(key)
                if target:
                    return f"[{alias or value}]({target[0]}#{target[1]})"
                return match[0]
            line = re.sub(r"\[\[([^\]\n]+)\]\]", wiki_link, line)
            def md_link(match):
                label, raw = match.groups()
                dest = raw.strip().strip("<>")
                if dest.startswith("#") or urlsplit(dest).scheme or dest.startswith("/"): return match[0]
                bare = unquote(dest.split("#", 1)[0]).replace("\\", "/")
                # Links just rewritten above are already relative to the node folder.
                if re.fullmatch(r"[\w-]+\.md#doc-[a-f0-9]+", dest): return match[0]
                relative = posixpath.normpath(posixpath.join(posixpath.dirname(source), bare))
                target = first.get(relative) or first.get(bare)
                if target: return f"[{label}]({target[0]}#{target[1]})"
                if relative.startswith("llm wiki/wxbot") and (ROOT / relative).is_dir(): return f"[{label}](wxbot.md)"
                actual = ROOT / relative
                if not actual.exists() and (ROOT / bare).exists():
                    relative = bare
                    actual = ROOT / bare
                if actual.exists() and actual.resolve().is_relative_to(ROOT):
                    fragment = "#" + dest.split("#", 1)[1] if "#" in dest else ""
                    rebased = posixpath.relpath(relative, "architecture-notes") + fragment
                    return f"[{label}](<{rebased}>)" if " " in rebased else f"[{label}]({rebased})"
                return match[0]
            return re.sub(r"(?<!!)\[([^\]\n]+)\]\((<[^>\n]+>|[^)\n]+)\)", md_link, line)
        content = outside_fences(content, line_rewrite)
        if content.startswith("---\n"):
            end = content.find("\n---", 4)
            if end != -1:
                content = "```yaml\n" + content[4:end] + "\n```\n" + content[end + 4:].lstrip("\n")
        return outside_fences(content, lambda line: re.sub(r"^(#{1,6})(?= )", lambda m: "#" * min(6, len(m[1]) + 2), line))

    buckets = {key: [] for key in titles}
    for part, content in chunks:
        node = part["node"]
        assert node in buckets, node
        group = "使用说明" if part["source"] == "README.md" else "历史记录" if "/raw/" in part["source"] or "/impacts/" in part["source"] or part["source"].startswith("docs/") else "技术资料"
        body = rewrite(content, part["source"]).rstrip() + "\n"
        block = f'\n<a id="{part["id"]}"></a>\n\n### {part["label"]}\n\n来源：`{part["source"]}:{part["line"]}`。\n\n' + body + f'<!-- end-migrated-part: {part["id"]} -->\n'
        part["rendered_sha256"] = sha(block.encode())
        part["group"] = group
        buckets[node].append((part, block))
        manifest["parts"].append(part)

    STAGED.mkdir(parents=True, exist_ok=True)
    index_lines = []
    for node, title in sorted(titles.items()):
        index_lines.append(f"| [{title}]({node}.md) | {len(buckets[node])} |")
    primary = {
        "wxbot": "项目入口。wxbot 管微信 UI 与持久队列，Butler 管身份、权限、模型编排与业务任务，管理台负责观察与显式管理。安装、运行、发布、开发维护和全部节点索引集中在这里。",
        "model-backends": "统一入口为 wxbot → Butler → ModelBackend。模型切换不迁移联系人、权限、提醒或知识；工具权限仍由业务服务签发与核验。具体协议、错误处理和会话代际见下方资料。",
        "identity-tools": "窗口名、群昵称和头像是身份观察；服务端解析联系人并签发本轮工具上下文。每次执行复核能力、有效期和现行策略，提示词与 API Key 不能授予业务权限。",
        "knowledge-vault": "用户知识为一人一个 Markdown vault，原文、事实与可重建索引分工明确。旧 kb_* SQLite 表已退场；旧表和迁移设计只在历史材料中保留，运行用知识模板仍在插件内。",
        "configuration": "实际配置由本安装的 config.*.toml 提供。管理台显示脱敏值并使用版本校验、备份和原子保存；模型字段影响后续请求，其他启动字段需使用者手动重启相应服务。",
        "delivery-pump": "一张 outbox 按 kind 分派文字、语音、图片、表情处理器，由 DeliveryPump 统一调度并保持同会话顺序。不要把旧图中的 reply_type 或独立文件发件队列当成当前实现。",
        "business-storage": "业务 SQLite 保存联系人、身份、会话、提醒和审计；用户对话原文与长期事实属于独立知识 vault，不把二者混为同一库。身份与字段契约见 [身份与工具](identity-tools.md)，知识存储见 [知识 vault](knowledge-vault.md)。",
        "codex": "Codex 是 Butler 共享模型接口的一个后端，使用本安装所有者自己的登录。后端选型、请求/工具契约、错误及热切换说明统一见 [模型后端](model-backends.md)。",
        "reminders": "提醒由 Butler 业务存储和 ReminderScheduler 管理，到期经 Butler 推送交给 wxbot，不由模型或 UI 线程拥有提醒状态。运行与投递约束见 [Butler 业务功能](butler-functions.md)，工具身份与允许功能见 [身份与工具](identity-tools.md)。",
        "delivery-text": "文字处理器读取同一 outbox 的 text 项，使用既有剪贴板、草稿保护、提及与气泡确认契约。调度和状态见 [统一发件](delivery-pump.md)，回复分句见 [文字发件](outbox-text.md)。",
        "delivery-image": "图片项仍在同一 outbox 中保持同会话顺序，由图片处理器准备和确认。共享契约与实施记录见 [统一发件](delivery-pump.md)，不要把该处理器等同于尚未实现的独立文件队列。",
        "delivery-emoji": "表情项由独立处理器发送，统一调度与回执仍归 DeliveryPump。配置未校准时沿用文字回退；实现和历史依据见 [统一发件](delivery-pump.md) 与 [微信 UI](wechat-ui.md)。",
        "douyin": "刷抖音属于小潮常驻角色的可选活动，聊天到来时让出活动机会，记录经核对的本机日记。配置、浏览器状态、额度、日记接口与验证记录见 [常驻角色](resident.md)。",
        "wechat-client": "微信桌面端是外部 UI，不实现 Butler 的身份授权或业务存储。控件读取、越屏恢复、提及和发送确认见 [微信 UI 主线程](wechat-ui.md)；完整收发顺序见 [项目入口](wxbot.md)。",
    }
    for node, title in sorted(titles.items()):
        lines = [f"# {title}\n", f"\n{primary.get(node, '本文件保存该架构节点的说明、相关契约与历史依据。')}\n",
                 "\n[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)\n",
                 "\n文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。\n"]
        if not buckets[node] and node not in primary:
            parent = "inbox" if node.startswith("inbox-") else "delivery-voice" if node == "outbox-voice" else "queue-storage"
            lines += [f"\n相关采集、字段与状态契约见 [节点资料]({parent}.md)；本节点原有说明保留如下。\n"]
        if node == "wxbot":
            lines += ["\n## 项目文档维护\n\n开发说明仅维护在 architecture-notes/ 的节点文档中。先读本文件及对应节点，核对源码和调用方，再同步节点说明与相关链接。记录 API/字段、数据血缘、前后端消费者、异步任务、测试和回滚，不涉及项写明原因。\n\n旧 llm wiki/wxbot/ 的 Markdown 已迁入节点；其旧 CLI、JSON 快照和 Obsidian 配置属于退役工具资料，不再执行 change/ingest/lint 工作流。保留的源码仅供追溯。运行时的用户知识 vault、角色和 Skill 与开发文档互不混用。\n\n发布包包含 architecture-notes/ 与根 ARCHITECTURE.html，原 README.md 已归入节点。入口为 python -m butler start；进程仍由使用者手动启停。新图的“文档”按钮与旧图继续复用这些 Markdown 文件。\n",
                      "\n## 文档归并实施与验收计划\n\n目标：将项目说明和旧开发知识图谱按节点归并，保留 AGENTS.md、运行用 Skill/角色/模板和许可归属文件。\n\n- [x] 冻结清单与文件摘要，备份原文及既有节点文档。\n- [x] 按模块责任拆分 README，归并 API/表/符号、设计与历史记录，并重定向内部链接。\n- [x] 核对每份来源的全部行有归属，生成节点索引和迁移清单。\n- [ ] 同步 AGENTS 入口、发布白名单与源码文档指针，验证后删除来源 Markdown。\n- [ ] 核对节点绑定、文档链接、保留文件摘要与临时发布包；记录结果。\n\n回滚：本次原文 ZIP、来源摘要与迁移映射保存在 .archify/document-migration-20261107-204541/；恢复前先比较当前节点文件，保留迁移后的用户编辑。\n",
                      "\n## 全部节点索引\n\n| 节点文档 | 迁入资料段数 |\n|---|---|\n" + "\n".join(index_lines) + "\n"]
        if node in notes:
            lines += ["\n## 原图节点说明\n\n" + rewrite(notes[node], "architecture-notes/" + node + ".md").rstrip() + "\n"]
        for group in ("使用说明", "技术资料", "历史记录"):
            selected = [(part, block) for part, block in buckets[node] if part["group"] == group]
            if not selected: continue
            lines += [f"\n## {group}\n\n"]
            if group == "历史记录":
                lines += ["以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。\n\n"]
            lines += [f'- [{part["label"]}](#{part["id"]}) · `{part["source"]}`\n' for part, _ in selected]
            lines += [block for _, block in selected]
        rendered = "".join(lines)
        (STAGED / f"{node}.md").write_text(rendered, encoding="utf-8", newline="\n")
        manifest["notes"][f"architecture-notes/{node}.md"] = {"sha256": sha(rendered.encode()), "bytes": len(rendered.encode()), "parts": [p["id"] for p, _ in buckets[node]]}

    # Full byte-for-byte originals are retained independently from the reorganized text.
    archive_path = WORK / "original-documents.zip"
    if archive_path.exists():
        with zipfile.ZipFile(archive_path) as archive:
            for source in all_md:
                assert archive.read(source) == checked(source).read_bytes(), source
    else:
        with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED) as archive:
            for source in all_md:
                archive.writestr(source, checked(source).read_bytes())
    for source in preserved:
        manifest["preserved"].append({"path": source, "sha256": sha(checked(source).read_bytes())})
    for node in notes:
        source = "architecture-notes/" + node + ".md"
        manifest["notes_before"].append({"path": source, "sha256": sha(checked(source).read_bytes())})
    (WORK / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    catalog = {"version": 1, "date": DATE, "entry": "wxbot.md", "nodes": [{"key": k, "title": titles[k], "file": k + ".md"} for k in sorted(titles)], "legacy_sources": {s: {"file": t[0], "anchor": t[1]} for s, t in first.items()}}
    (STAGED / "index.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sources": len(sources), "parts": len(chunks), "nodes": len(titles), "preserved": len(preserved)}, ensure_ascii=False))


def verify(applied=False):
    if not any(STAGED.glob('*.md')):
        applied = True
    m = json.loads((WORK / "manifest.json").read_text("utf-8"))
    target_root = ROOT / "architecture-notes" if applied else STAGED
    texts = {p.name: p.read_text("utf-8") for p in target_root.glob("*.md")}
    with zipfile.ZipFile(WORK / "original-documents.zip") as archive:
        for source in m["sources"]:
            raw = archive.read(source["path"])
            assert sha(raw) == source["sha256"], source["path"]
            original = raw.decode("utf-8-sig").replace("\r\n", "\n").splitlines(keepends=True)
            intervals = sorted((p for p in m["parts"] if p["source"] == source["path"]), key=lambda p: p["line"])
            cursor = 0
            for part in intervals:
                assert part["line"] == cursor + 1, part
                original_piece = "".join(original[cursor:part["end_line"]])
                assert sha(original_piece.encode()) == part["sha256"], part["id"]
                cursor = part["end_line"]
                text = texts[part["node"] + ".md"]
                marker = f'<a id="{part["id"]}"></a>'
                assert text.count(marker) == 1, part["id"]
                start = text.index("\n", text.index(marker)) + 1
                block_start = text.rfind("\n", 0, text.index(marker))
                end_marker = f'<!-- end-migrated-part: {part["id"]} -->\n'
                assert text.count(end_marker) == 1
                block = text[block_start:text.index(end_marker, start) + len(end_marker)]
                assert sha(block.encode()) == part["rendered_sha256"], part["id"]
            assert cursor == len(original), source["path"]
        for item in m["preserved"]:
            if item["path"] == "AGENTS.md": continue  # Its entry/workflow is intentionally redirected.
            assert sha(checked(item["path"]).read_bytes()) == item["sha256"], item["path"]
    for relative, expected in m["notes"].items():
        actual = (target_root / Path(relative).name).read_bytes()
        assert sha(actual) == expected["sha256"], relative
    print(f'PASS: {len(m["sources"])} complete source documents / {len(m["parts"])} parts / {len(m["notes"])} node documents; original archive and protected files verified')


def apply():
    if not any(STAGED.glob('*.md')):
        raise SystemExit('Migration staging has been cleaned; documents are already installed. Use verify --applied.')
    verify()
    m = json.loads((WORK / "manifest.json").read_text("utf-8"))
    for item in m["sources"] + m["notes_before"]:
        assert sha(checked(item["path"]).read_bytes()) == item["sha256"], f'Changed since snapshot: {item["path"]}'
    for path in STAGED.iterdir():
        if path.suffix not in (".md", ".json"): continue
        target = checked("architecture-notes/" + path.name)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(path.read_bytes())
        os.replace(tmp, target)
    verify(applied=True)
    print("Node documents installed; source deletion has NOT been performed.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    command = sys.argv[1] if len(sys.argv) > 1 else "prepare"
    if command == "prepare": prepare()
    elif command == "verify": verify("--applied" in sys.argv)
    elif command == "apply": apply()
    else: raise SystemExit("Use prepare | verify [--applied] | apply")
