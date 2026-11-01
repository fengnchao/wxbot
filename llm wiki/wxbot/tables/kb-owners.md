---
type: table
module: butler
summary: 已退场——owner 目录与提炼游标改为可重建的 index.json，SQLite 索引库只在迁移时被改名留底
coverage: core
last_verified: '2026-11-01'
sources:
- path: src/butler/runtime/knowledge_store.py
  line: 297
  anchor: 'def index_path(self):'
- path: src/butler/runtime/knowledge_store.py
  line: 319
  anchor: 'def _catalog(self):'
- path: src/butler/runtime/knowledge_store.py
  line: 334
  anchor: 'def _touch(self, owner, contact, channel_type, *, episodes=0, facts=0,
    at=None):'
- path: src/butler/runtime/knowledge_store.py
  line: 355
  anchor: 'def _recount(self):'
- path: src/butler/runtime/knowledge_store.py
  line: 763
  anchor: index = root / 'index.sqlite3'
- path: src/butler/runtime/knowledge_store.py
  line: 673
  anchor: 'def _checkpoint_legacy(path):'
changes:
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint
- raw/changes/2026-11-01-knowledge-atlas-index
---
# SQLite kb_owners（已退场）

**这张表连同 `data/knowledge/index.sqlite3` 一起退场。** 目录现在是一个 JSON 文件 `data/knowledge/index.json`，仍然只做枚举不做存储；`index.sqlite3` 若还存在，迁移时只改名留底、不读内容。当前形态见 [[tables/knowledge-vault]]。

## 它曾经是什么

索引库的唯一表，不是数据本体，只是**目录**：谁有库、目录名是什么、展示名是什么、有多少条、最后说话是什么时候、提炼到哪一条。

**为什么曾经要有索引库**：`owner` 形如 `user:<uuid>` / `anon:group:产品群`，带冒号和中文，不能直接当目录名，所以目录名是散列 `p-` 加 `sha1(owner)` 前 16 位（`owner_slug`，`src/butler/runtime/knowledge_store.py:74`）。散列不可逆，必须有地方记「这个散列是谁」，否则只读侧无法列出可筛选的人，也无法显示展示名。

**为什么不把原文和事实塞进索引库**：那就退回到「一个库装所有人」，一个人的损坏牵连所有人。

## 退场后的替代：index.json

同一个位置、同一份职责，换成了 JSON（`index_path`，`:297`）：

```json
{"owners": {"user:<uuid>": {"owner", "slug", "contact", "contact_name",
                            "channel_type", "episodes", "facts",
                            "extracted_at", "first_at", "last_at"}}}
```

| 旧列 | 新字段 | 变化 |
|---|---|---|
| `owner` PRIMARY KEY | `owners` 字典的键 | 从行变成键 |
| `slug` UNIQUE | `slug` | 不变 |
| `contact` / `contact_name` | 同名字段 | 不变 |
| `channel_type` | 同名字段 | 不变 |
| `episodes` / `facts` | 同名字段 | 仍是冗余计数 |
| `extracted_upto`（原文 id 水位） | `extracted_at`（时刻水位） | **语义变了**：没有自增 id，游标只能按时间推进 |
| `first_at` / `last_at` | 同名字段 | 不变 |

**为什么敢用 JSON**：这张表规模等于联系人数，整份读写比维护连接便宜；更重要的是它是**缓存**——`_catalog()`（`:319`）读不出来就调 `_recount()`（`:355`）扫一遍 `p-*/vault` 现数回来，游标沿用旧值，不会把已提炼的原文重提一遍。SQLite 版也有重建，但重建是例外路径；这里重建是一等公民。

**仍然没有 schema 版本号**：未知键原样保留，加字段不需要改表。

目录多一个用途：`prune` 删完成天日记后要遍历 `owners()`（`:402`）把每人的 `vault/index.md` 重画一遍，否则索引页里会留着已删除日记的断链。删行本身不经过目录，但「删完之后还要修哪些人」靠它枚举。

## 仅存的接触点：迁移

`migrate_legacy` 最后一步（`:763`）：`data/knowledge/index.sqlite3` 存在就先 `_checkpoint_legacy`（`:673`）合并 WAL，再改名成 `index.sqlite3.migrated`。**不读内容**——各 owner 的库搬进 vault 时 `_touch`（`:334`）已经把新目录建好了，计数从真实文件数出来，旧索引只是垃圾；但垃圾也要是可打开的文件，否则回收站里的就不是备份。

## 代码依据与修改来源

- `src/butler/runtime/knowledge_store.py:74` — `def owner_slug(owner):`
- `src/butler/runtime/knowledge_store.py:297` — `def index_path(self):`
- `src/butler/runtime/knowledge_store.py:319` — `def _catalog(self):`
- `src/butler/runtime/knowledge_store.py:334` — `def _touch(self, owner, contact, channel_type, *, episodes=0, facts=0, at=None):`
- `src/butler/runtime/knowledge_store.py:355` — `def _recount(self):`
- `src/butler/runtime/knowledge_store.py:763` — `index = root / 'index.sqlite3'`
- `src/butler/runtime/knowledge_store.py:673` — `def _checkpoint_legacy(path):`

[[raw/changes/2026-11-01-knowledge-sharding]]
[[raw/changes/2026-11-01-knowledge-sessions]]
[[raw/changes/2026-11-01-knowledge-auto]]
[[raw/changes/2026-11-01-knowledge-vault-graph]]
[[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]
[[raw/changes/2026-11-01-knowledge-atlas-index]]
