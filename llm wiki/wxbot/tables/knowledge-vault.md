---
type: table
module: butler
summary: 用户知识图谱的存储形态——一人一个 Obsidian vault，节点是 Markdown，关系是正文里的双链
coverage: core
last_verified: '2026-11-01'
sources:
- path: src/butler/runtime/knowledge_store.py
  line: 1
  anchor: 用户知识图谱：一人一个 Obsidian vault
- path: src/butler/runtime/knowledge_store.py
  line: 74
  anchor: 'def owner_slug(owner):'
- path: src/butler/runtime/knowledge_store.py
  line: 80
  anchor: 'def _safe(name, fallback=''未命名''):'
- path: src/butler/runtime/knowledge_store.py
  line: 104
  anchor: 'def _atomic_write(path, text):'
- path: src/butler/runtime/knowledge_store.py
  line: 286
  anchor: 'class KnowledgeStore:'
- path: src/butler/runtime/knowledge_store.py
  line: 408
  anchor: def record(self, owner, contact, channel_type, request_id, user_text,
- path: src/butler/runtime/knowledge_store.py
  line: 430
  anchor: def add_fact(self, owner, contact, fact_value, *, kind='topic', fact_key='',
- path: src/butler/runtime/knowledge_store.py
  line: 565
  anchor: 'def episodes_of(self, owner, after_at=0.0, limit=200):'
- path: src/butler/runtime/knowledge_store.py
  line: 610
  anchor: 'def facts(self, owner='''', query='''', limit=50, offset=0, contact=''''):'
- path: src/butler/runtime/knowledge_store.py
  line: 49
  anchor: INDEX_SECTIONS
- path: src/butler/runtime/knowledge_store.py
  line: 54
  anchor: INDEX_FILE
- path: src/butler/runtime/knowledge_store.py
  line: 312
  anchor: 'def index_page_path(self, owner):'
- path: src/butler/runtime/knowledge_store.py
  line: 499
  anchor: 'def rebuild_index(self, owner):'
- path: src/butler/runtime/knowledge_store.py
  line: 673
  anchor: 'def _checkpoint_legacy(path):'
- path: src/butler/runtime/knowledge_store.py
  line: 740
  anchor: 'def migrate_legacy(data_dir, log=None):'
- path: src/dashboard/knowledge_view.py
  line: 22
  anchor: 'class KnowledgeView:'
- path: src/dashboard/routes.py
  line: 43
  anchor: '"GET", "/api/knowledge", knowledge.read'
changes:
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-vault-alignment
- raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint
- raw/changes/2026-11-01-knowledge-atlas-index
---
# 用户知识库：一人一个 Obsidian vault

## 含义与磁盘布局

用户知识不再是数据库表，而是**一人一个 Obsidian vault**：实体是 Markdown 文件，实体之间的关系只由正文里的双链（Obsidian 的 wikilink 语法）表达。实现只有一份，见 [[modules/runtime]] 里的 `KnowledgeStore`。

```text
data/knowledge/
  index.json                 目录缓存：owner 列表、原文/事实条数、提炼游标
  p-<slug>/vault/            Obsidian vault 根，只放 .md
    人物/冯草草.md           实体节点（type: person）
    组织/鸭王集训营.md       type: org
    话题/AI 编程.md          type: topic
    对话/2026-11-01.md       当天的对话原文；与实体节点之间没有双链
    index.md                 中心索引页：按类别列事实、按目录列节点、按天列日记
```

`<slug>` 由 `sha1(owner)[:16]` 加前缀 `p-` 得到（`:74`）。owner 里带冒号和中文，不适合当目录名，且名字不需要反查——反查靠写进每个文件 frontmatter 的 `owner` 字段。

**为什么一人一个 vault**：任何一个人的数据损坏、被单独导出或整体清空，都不牵连别人；Obsidian 一次只开一个 vault，一个人的图也不会被别人的节点淹没。

## 为什么是 Markdown 而不是表

知识图谱的价值在关联，而 Obsidian 的 graph view 只从正文的双链连边——表能存字段，存不出拓扑。旧的 `kb_episodes` / `kb_facts` / `kb_owners` 三张表已退场，留档说明见 [[tables/kb-episodes]]、[[tables/kb-facts]]、[[tables/kb-owners]]。

原文也写成 Markdown（按天一个文件）：按天归档把文件数量压到每年 365 个，不至于把图挤满。

**事实不生成指向日记的双链**：溯源靠事实行尾注释的 `at` 与 `quote`，而不是把日期节点挂上去——每个事实都向时间线拉一条边的话，图会被日期节点淹没。因此日记文件自己连不到任何节点。

**但没有孤立点**：vault 根还有一张 `index.md`，它按类别列出全部事实（每条都指向所属人物节点）、按目录列出节点、按天列出最近十天的日记。所有文件都挂到这一张中心页上，graph view 才是连通的——新库、单聊、还没有第三方实体的时候尤其依赖它。

## 文件格式

**实体节点**（`人物/组织/话题` 三个目录）：frontmatter 带 `type` / `name` / `contact` / `owner` / `updated` / `updated_ts`，正文 `# 标题` 下按 `FACT_SECTIONS`（`:46`）分七个小节——身份、偏好、性格、目标、关系、事件、话题。每条形如：

```text
- 喜欢喝美式，不加糖。 <!-- fp:1a2b…|key:咖啡|kind:preference|conf:0.80|at:1767225600.0|src:extract|quote:我一般只要美式 -->
```

行尾 HTML 注释是这项设计的**唯一去重键**：`fp` 为 `sha1(kind|fact_key|value)[:16]`（`:447`），重复写入直接跳过（`:454`）。措辞不同的矛盾陈述各留一条，库不替人判断谁对——这与旧 `kb_facts_fingerprint` 部分唯一索引等价。

**对话日记**（`对话/YYYY-MM-DD.md`）：frontmatter 带 `type: conversations` / `date` / `owner` / `contact` / `channel_type`；正文每轮一个 `## 时间 · 联系人 · 私聊|群聊` 块，块内注释记录 `rid` / `at` / `outcome` / `contact` / `channel`，正文用 `**用户**` / `**助理**` 加引用块。同一 `request_id` 重试靠文本里是否已有 `rid:…|` 判重（`:421`），不需要事务。

**中心索引页**（`index.md`，`INDEX_FILE` 见 `:54`）：frontmatter 只有 `type: index` / `owner` / `contact` / `updated`，正文依次是七类事实、三目录节点、最近十天日记。分类标题取 `INDEX_SECTIONS`（`:49`），和节点里的小节名刻意不同——节点用「身份/偏好」，索引页用「用户信息/喜好」，改一处不会让旧内容留错位置。每个事实条目只列前 `INDEX_LIMIT`（40）条，超出补一行「另有 N 条未列出」，避免索引页无限长；日记只列 `INDEX_DAYS`（10）天。索引页不写事实行、不带 `fp`，所以 `facts()` 不把它算进事实条数。

`_safe()`（`:80`）清洗文件名：把控制字符与 `<>:"/\\|?*#^[]` 一律替换成 `-`，压缩空白，去掉首尾空格与点号，截断 60 字——这些字符会破坏 Obsidian 的链接语法。清洗后同名会合并成一个节点，因此事件原名另存 frontmatter `name`，可人工核对。

## 关联、索引与一致性

- **没有外键**：关系就是正文里的双链，`add_fact` 的 `links` 参数把实体名写成链接（`:458`）。原文会被 `prune` 清理，事实不引用原文 id，只存 `at` 时间戳，所以原文过期不会让事实失效。
- **没有 schema 版本号**：Markdown 文件自带 frontmatter，未知键原样保留（`_rewrite_meta` 只更新 `updated`/`updated_ts`）。
- **`index.json` 是缓存不是数据源**：只存计数与游标；文件丢了 `_recount()`（`:355`）从 vault 现数回来，游标沿用旧值，不会把已提炼的原文重提一遍。
- **没有事务**：每次写入先落同目录临时文件再 `os.replace`（`:104`），读侧永远看到完整文件。同一节点的并发写会丢一条，当前只有单进程写入。

## 字段血缘（vault → 对象 → API → 前端）

- `owner` / `contact` / `channel_type`：由身份体系签发；`episode_owner()`（`:65`）优先用 `memory_owner`，没有身份就落到 `anon:dm|group:<名字>` 独立命名空间，绝不挂到别人名下。
- 读原文：`KnowledgeStore.read`（`:581`）跨 vault 归并，返回 `owner` / `contact` / `channel_type` / `request_id` / `user_text` / `reply_text` / `outcome` / `at`。
- 读事实：`KnowledgeStore.facts`（`:610`）遍历节点小节，多返回 `node` 与 `kind`；`query` 同时匹配 `fact_key` 与 `fact_value`。
- 会话维度：`sessions()`（`:648`）按 `contact`(+`channel_type`) 统计，左栏的「私聊/群聊」分组来自这里。
- 只读投影 [[apis/dashboard-knowledge]] 只做转发：`KnowledgeView`（`src/dashboard/knowledge_view.py:22`）把 `KnowledgeStore` 的三个读接口原样透出，不再自己解析文件。

## 冗余与迁移

`index.json` 与 vault 内容冗余，但方向明确：vault 是权威，索引可重建。`contact` 与 `owner` 并存不是冗余——前者是展示名，后者是身份稳定键。

`migrate_legacy(data_dir)`（`:740`）把 SQLite 时代的数据搬进 vault，成功后把原文件改名留底，不删：

| 旧文件 | 处理 |
|---|---|
| `data/knowledge.sqlite3` | 读 `kb_episodes` / `kb_facts` 写入 vault，改名为 `knowledge.legacy.sqlite3` |
| `data/knowledge/p-*/episodes.sqlite3` | 同上，改名为 `episodes.sqlite3.migrated` |
| `data/knowledge/p-*/facts.sqlite3` | 同上，改名为 `facts.sqlite3.migrated` |
| `data/knowledge/index.sqlite3` | 只改名 `index.sqlite3.migrated` |
| `data/business.sqlite3` 的 `memory` 表 | 每条搬成 `kind=profile` 的事实，`source=memory-migration`，原表保留 |

迁移是幂等的：`record` 与 `add_fact` 都靠 `rid` / `fp` 判重。**升级后必须在停服状态手动跑一次 `python -m butler knowledge-migrate`**，否则旧库里的原文与事实不会出现在 vault 里。

**留底前必须 checkpoint**：`_import_sqlite`（`:694`）用 `mode=ro` 只读 URI 打开旧库，读得到 WAL 里的行却永远不会把 WAL 合并回主库；紧接着 `replace` 改名后，`-wal` / `-shm` 的名字还停在旧文件名上，SQLite 不再认这对边车，留底库就成了空壳——实测 `facts.sqlite3.migrated` 不带 WAL 时连 `kb_facts` 表都读不出来。所以四处改名之前都先调 `_checkpoint_legacy`（`:673`）：用读写连接跑 `PRAGMA wal_checkpoint(TRUNCATE)`，再清掉残留边车。这段缺陷在首次真实迁移后才发现，见 [[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]。

## 读写符号与测试

写：`record`（`:408`）追加日记块；`add_fact`（`:430`）追加节点事实行；`set_extracted_at`（`:472`）推进提炼游标；`prune`（`:482`）只删过期日记文件，节点事实不参与过期。

每次写完都调 `rebuild_index`（`:499`）重画中心索引页；`prune` 删到东西时也会把所有人的索引页重画一遍，免得索引里留着已删除日记的断链。

读：`owners`（`:402`）、`episodes_of`（`:565`）、`read`（`:581`）、`facts`（`:610`）、`sessions`（`:648`）。`close()`（`:561`）保留为空方法，让调用方不必区分新旧实现。

调用方：[[concepts/message-pipeline]] 的 `_record_episode` 调 `record`；[[symbols/knowledge-extract]] 调 `episodes_of` / `add_fact` / `set_extracted_at`；[[symbols/knowledge-auto]] 调 `extracted_at` 与 `prune`。

本地用例（`tests/` 不入 Git）：`test_knowledge_store.py` 覆盖双链生成、指纹去重、`prune` 不动事实、索引重建、索引页分类分组、过期日记不留断链、索引页不计入事实条数；`test_knowledge_extract.py` 覆盖解析容错与游标；`test_knowledge_view.py` 覆盖只读投影与 HTTP 路由。

## 代码依据与修改来源

- `src/butler/runtime/knowledge_store.py:1` — 模块说明：一人一个 Obsidian vault
- `src/butler/runtime/knowledge_store.py:74` — `def owner_slug(owner):`
- `src/butler/runtime/knowledge_store.py:80` — `def _safe(name, fallback='未命名'):`
- `src/butler/runtime/knowledge_store.py:104` — `def _atomic_write(path, text):`
- `src/butler/runtime/knowledge_store.py:286` — `class KnowledgeStore:`
- `src/butler/runtime/knowledge_store.py:408` — `def record(self, owner, contact, channel_type, request_id, user_text,`
- `src/butler/runtime/knowledge_store.py:430` — `def add_fact(self, owner, contact, fact_value, *, kind='topic', fact_key='',`
- `src/butler/runtime/knowledge_store.py:565` — `def episodes_of(self, owner, after_at=0.0, limit=200):`
- `src/butler/runtime/knowledge_store.py:610` — `def facts(self, owner='', query='', limit=50, offset=0, contact=''):`
- `src/butler/runtime/knowledge_store.py:49` — `INDEX_SECTIONS`（索引页的七类中文小标题）
- `src/butler/runtime/knowledge_store.py:54` — `INDEX_FILE = 'index.md'`
- `src/butler/runtime/knowledge_store.py:312` — `def index_page_path(self, owner):`
- `src/butler/runtime/knowledge_store.py:499` — `def rebuild_index(self, owner):`
- `src/butler/runtime/knowledge_store.py:673` — `def _checkpoint_legacy(path):`
- `src/butler/runtime/knowledge_store.py:740` — `def migrate_legacy(data_dir, log=None):`
- `src/dashboard/knowledge_view.py:22` — `class KnowledgeView:`
- `src/dashboard/routes.py:43` — `("GET", "/api/knowledge", knowledge.read),`

[[raw/changes/2026-11-01-knowledge-vault-graph]]

[[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]

[[raw/changes/2026-11-01-knowledge-atlas-index]]
