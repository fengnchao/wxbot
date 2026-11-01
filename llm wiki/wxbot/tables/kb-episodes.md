---
type: table
module: butler
summary: 已退场——SQLite 时代的 L1 原文表，现由 vault 里的「对话/YYYY-MM-DD.md」承担，只保留迁移读入口
coverage: core
last_verified: '2026-11-01'
sources:
- path: src/butler/runtime/knowledge_store.py
  line: 44
  anchor: OUTCOMES = ('ok', 'error', 'silent')
- path: src/butler/runtime/knowledge_store.py
  line: 694
  anchor: 'def _import_sqlite(store, path, log):'
- path: src/butler/runtime/knowledge_store.py
  line: 700
  anchor: 'if ''kb_episodes'' in tables:'
- path: src/butler/runtime/knowledge_store.py
  line: 740
  anchor: 'def migrate_legacy(data_dir, log=None):'
- path: src/butler/runtime/knowledge_store.py
  line: 673
  anchor: 'def _checkpoint_legacy(path):'
- path: src/butler/__main__.py
  line: 57
  anchor: 'if args.command==''knowledge-migrate'':'
changes:
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint
- raw/changes/2026-11-01-knowledge-atlas-index
---
# SQLite kb_episodes（已退场）

**这张表不再被写入，也不再被读取。** L1 原文现在落在每个人的 vault 里：`对话/YYYY-MM-DD.md`，一天一个文件，一轮对话一个 `##` 块。当前形态见 [[tables/knowledge-vault]]。

保留这一页只为迁移：`migrate_legacy` 仍按旧列名把 SQLite 里的行读出来喂给 vault。

## 它曾经是什么

SQLite 时代的 L1 原文层：一条记录等于一轮对话（用户说了什么、机器人回了什么、这轮成功与否），每个 owner 一个库 `data/knowledge/p-<slug>/episodes.sqlite3`。

`outcome` 只有 `ok` / `error` / `silent` 三个值（`OUTCOMES`，`src/butler/runtime/knowledge_store.py:44`）：`silent` 是模型选择不回，`error` 是处理抛错，`reply_text` 为 NULL 表示这轮没有产出回复——三者不是同一件事。

## 退场后的替代

| 旧 | 新 |
|---|---|
| 表 `kb_episodes`，一行一轮 | 日记文件 `对话/YYYY-MM-DD.md`，`## 时间 · 联系人 · 私聊 / 群聊` 块 |
| `id INTEGER PRIMARY KEY` 定序去重 | 没有自增 id；块首注释里的 `at` 与 `rid` 定序去重 |
| `outcome` 列 | 块首注释 `rid` / `at` / `outcome` / `contact` / `channel` |
| 部分唯一索引 `kb_episodes_request` | 读该天文件，看文本里是否已有 `rid:…` |
| `prune` 按 `at < cutoff` 删行 | `prune` 按保留期删整天文件 |

原文按天归档而不是一轮一文件：一年 365 个文件，不至于把 Obsidian 的图挤满。

## 仅存的读取路径：迁移

`migrate_legacy(data_dir)`（`src/butler/runtime/knowledge_store.py:740`）→ `_import_sqlite`（`:694`）在旧库里发现 `kb_episodes` 表（`:700`）就逐行读，调 `KnowledgeStore.record(...)` 写进 vault；搬完把旧库改名留底、不删：

| 旧文件 | 处理 |
|---|---|
| `data/knowledge.sqlite3` | 搬完改名 `knowledge.legacy.sqlite3` |
| `data/knowledge/p-*/episodes.sqlite3` | 搬完改名 `episodes.sqlite3.migrated` |

改名之前会先 `_checkpoint_legacy`（`:673`）合并 WAL：旧库是 WAL 模式时，直接把主库改名会让 `-wal` 失配，留底库就只剩改名前的旧页（详见 [[tables/knowledge-vault]] 与 [[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]）。

入口只有一个：`python -m butler knowledge-migrate`（`src/butler/__main__.py:57`）。迁移幂等，重复跑不会写出重复块。

## 代码依据与修改来源

- `src/butler/runtime/knowledge_store.py:44` — `OUTCOMES = ('ok', 'error', 'silent')`
- `src/butler/runtime/knowledge_store.py:694` — `def _import_sqlite(store, path, log):`
- `src/butler/runtime/knowledge_store.py:700` — `if 'kb_episodes' in tables:`
- `src/butler/runtime/knowledge_store.py:740` — `def migrate_legacy(data_dir, log=None):`
- `src/butler/runtime/knowledge_store.py:673` — `def _checkpoint_legacy(path):`
- `src/butler/__main__.py:57` — `if args.command=='knowledge-migrate':`

[[raw/changes/2026-11-01-knowledge-episodes]]
[[raw/changes/2026-11-01-knowledge-sharding]]
[[raw/changes/2026-11-01-knowledge-sessions]]
[[raw/changes/2026-11-01-knowledge-auto]]
[[raw/changes/2026-11-01-knowledge-vault-graph]]
[[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]
[[raw/changes/2026-11-01-knowledge-atlas-index]]
