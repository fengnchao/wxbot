---
type: table
module: butler
summary: 已退场——L2 事实表被 vault 里的「人物/组织/话题」节点 Markdown 取代，只保留迁移读入口
coverage: core
last_verified: '2026-11-02'
sources:
- path: src/butler/runtime/knowledge_store.py
  line: 50
  anchor: FACT_KINDS = LEGACY_KINDS
- path: src/butler/runtime/knowledge_store.py
  line: 755
  anchor: 'def _import_sqlite(store, path, log):'
- path: src/butler/runtime/knowledge_store.py
  line: 767
  anchor: 'if ''kb_facts'' in tables:'
- path: src/butler/runtime/knowledge_store.py
  line: 779
  anchor: 'def _import_memory(store, path, log):'
- path: src/butler/runtime/knowledge_store.py
  line: 734
  anchor: 'def _checkpoint_legacy(path):'
changes:
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-01-knowledge-atomic-retry
- raw/changes/2026-11-02-knowledge-graph-template
---
# SQLite kb_facts（已退场）

**这张表不再被写入，也不再被读取。** L2 事实现在写在 vault 的实体节点里——`人物/…`、`组织/…`、`话题/…` 三个目录下的 Markdown，一条事实一行，行尾 HTML 注释带去重指纹与出处。当前形态见 [[tables/knowledge-vault]]。

保留这一页只为迁移：`_import_sqlite` 仍按旧列名把事实读出来喂给 `add_fact`。

## 它曾经是什么

SQLite 时代的 L2 事实层：从 L1 原文提炼出的、值得长期记住的陈述——身份背景、偏好习惯、与他人的关系、约定与发生过的事、长期关注的话题。每个 owner 一个库 `data/knowledge/p-<slug>/facts.sqlite3`，与原文分库是因为两者生命周期不同：原文按 `retention_days` 过期，事实不跟着消失。

`kind` 白名单当年是 `FACT_KINDS`（现在 `src/butler/runtime/knowledge_store.py:50` 只剩兼容常量 `FACT_KINDS = LEGACY_KINDS`）；越界值在 `add_fact` 里回落成 `topic`。当前白名单实际来自模板 [[symbols/knowledge-template]]，见 [[tables/knowledge-vault]]。

**唯一键建在指纹上而不是 `fact_key` 上**：指纹是 `sha1(kind|fact_key|fact_value)`。同一件事的同一说法只留一条；措辞不同的矛盾陈述（「喜欢美式」与「更喜欢拿铁」）各留一条，不互相覆盖——谁对谁错要靠人和时间判断，库不该替他们做决定。这条设计原样带进了 vault：指纹变成行尾注释里的 `fp`。

## 退场后的替代

| 旧 | 新 |
|---|---|
| 表 `kb_facts`，一行一条事实 | 实体节点 `…md` 正文的一行 `- 陈述 <!-- fp:… -->` |
| `owner` / `contact` 列 | 节点 frontmatter 的 `owner` / `contact` |
| `kind` 列 | 正文按 `FACT_SECTIONS` 分小节，小节即 kind |
| `fact_key` / `fact_value` | 行内陈述文本 + 注释里的 `key:` |
| `quote` / `confidence` / `source` / `episode_at` | 注释里的 `quote:` / `conf:` / `src:` / `at:` |
| `fingerprint` + 部分唯一索引 | 行尾注释的 `fp:`，写入前扫一遍已有行 |
| `created` 排序 | 节点 frontmatter 的 `updated` / `updated_ts` |

**新增了表里没有的两样东西**：`subject`（这条事实挂到哪个节点）与 `links`（正文里生成哪些 `[[双链]]`）。没有它们，写出来的只是一堆孤立的事实行，Obsidian 的 graph view 连不起来——这正是改版的原因。

## 仅存的读取路径：迁移

`migrate_legacy(data_dir)` → `_import_sqlite`（`src/butler/runtime/knowledge_store.py:755`）逐行读 `kb_facts`（`:767`）并调 `add_fact(...)`，`source` 与 `created` 原样带过去。搬完改名留底：

| 旧文件 | 处理 |
|---|---|
| `data/knowledge.sqlite3` | 搬完改名 `knowledge.legacy.sqlite3` |
| `data/knowledge/p-*/facts.sqlite3` | 搬完改名 `facts.sqlite3.migrated` |

事实库同样是 WAL 模式，改名之前会先 `_checkpoint_legacy`（`:734`）合并 WAL；否则留底库可能连 `kb_facts` 表都读不出来（首次真实迁移踩到过，见 [[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]）。

同一支迁移还顺带收编另一套存储：`_import_memory`（`:779`）把 `business.sqlite3` 里遗留的 `memory` 表逐条搬成 `kind=profile`、`source=memory-migration` 的节点事实，原表保留不动。

2026-11-02 的模板化不改变迁移语义：`_import_sqlite` 仍按旧表的七类 kind 原样交给 `add_fact`，这些 kind 仍在内置模板里；即使安装者删掉其中一类，历史事实也只在读取时按原节点展示，不会被改写或丢弃。

## 代码依据与修改来源

- `src/butler/runtime/knowledge_store.py:50` — `FACT_KINDS = LEGACY_KINDS`（兼容默认值；实际白名单来自模板）
- `src/butler/runtime/knowledge_store.py:755` — `def _import_sqlite(store, path, log):`
- `src/butler/runtime/knowledge_store.py:767` — `if 'kb_facts' in tables:`
- `src/butler/runtime/knowledge_store.py:779` — `def _import_memory(store, path, log):`
- `src/butler/runtime/knowledge_store.py:734` — `def _checkpoint_legacy(path):`

[[raw/changes/2026-11-01-knowledge-sharding]]
[[raw/changes/2026-11-01-knowledge-sessions]]
[[raw/changes/2026-11-01-knowledge-auto]]
[[raw/changes/2026-11-01-knowledge-vault-graph]]
[[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]
[[raw/changes/2026-11-01-knowledge-atlas-index]]
[[raw/changes/2026-11-01-knowledge-atomic-retry]]
[[raw/changes/2026-11-02-knowledge-graph-template]]
