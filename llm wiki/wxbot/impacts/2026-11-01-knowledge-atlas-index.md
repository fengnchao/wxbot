---
type: impact
status: completed
date: '2026-11-01'
---
# 知识库中心索引页与七类事实分组影响分析

## 需求关键词与图谱命中

需求：vault 虽然已经是 Obsidian 图谱，但单聊、新库里只有「人物/<联系人>」与若干天日记两个孤立点，要求「索引之间关联」；同时补上用户点名的分类（用户信息、喜好、性格、目标）。

图谱命中：[[tables/knowledge-vault]]、[[symbols/knowledge-extract]]、[[symbols/knowledge-auto]]、[[apis/dashboard-knowledge]]、[[modules/web]]、[[concepts/message-pipeline]]。

覆盖缺口：图谱没有「中心索引页」这个概念，也没有 `personality` / `goal` 两类事实的记录；本次在 [[tables/knowledge-vault]] 新增「中心索引页」小节，并把三类 kind 白名单一起写清。

## 要改的文件、符号与调用方

- `src/butler/runtime/knowledge_store.py`：新增 `index_page_path`、`rebuild_index` 与四个 `INDEX_*` 常量；`FACT_KINDS` / `FACT_SECTIONS` 扩到七类。调用方是 `record`（[[concepts/message-pipeline]] 的 `_record_episode`）、`add_fact`（[[symbols/knowledge-extract]]）、`prune`（[[symbols/knowledge-auto]] 的调度线程）。
- `src/butler/runtime/knowledge_extract.py`：`KINDS` 与 `PROMPT` 同步七类，否则模型不会产出性格与目标。
- `web/src/views/FactsView.vue`：`KINDS` 中文映射补两项，否则新类型显示成「关注话题」。

## 接口与前端契约

`GET /api/knowledge/facts` 的字段、分页、排序都不变；只有 `kind` 的取值域从五个变七个。前端类型列是纯映射，不新增列、不新增请求。

## 数据库与字段血缘

无表结构变更：`index.md` 是 vault 里的派生文件，frontmatter 只带 `type: index` / `owner` / `contact` / `updated`，没有 `fp`，因此不会进入 `facts()` 的统计，也不会被当成实体节点。分类标题走两套常量（节点小节 vs 索引页标题），互不影响。

## 风险、验证、异步任务与回滚

风险：`rebuild_index` 每写一次就重扫整份 vault，写路径从 O(1) 变成 O(节点文件数)；索引页事实只列前 40 条、日记只列 10 天，超出部分不展示。异步侧 `prune` 会多写 N 份索引页，仍在既有调度线程内。

验证：`tests/butler/test_knowledge_store.py` 新增四条覆盖双链、分类分组、过期断链、不计入事实；`pytest tests/butler tests/dashboard` 全绿；`npm run build` 与 `npm run smoke` 通过。

回滚：删掉 `rebuild_index` 与三处调用及 `INDEX_*` 常量即可，`index.md` 是纯派生文件，删掉不影响任何事实与日记。

## 实际改动与 raw 归档

实施结果与分析一致，附带三处顺带订正（同一批词条行号已因插入点后移）：

- [[tables/knowledge-vault]] 的读符号行号（`read` / `sessions` / `owners` / `set_extracted_at` / `prune` / `close`）与 `episode_owner`、`_recount`、`_import_sqlite` 全部按当前源码重算。
- [[symbols/knowledge-auto]] 把退场名 `extracted_upto` 改成 `extracted_at`，并把 `src/butler/server.py` 的三个行号各减一（与实际 `construct/start/stop` 位置对齐）。
- [[concepts/message-pipeline]] 的旁路支线仍写着 SQLite 的 `p-<slug>/episodes.sqlite3`，改为 vault 的 `对话/YYYY-MM-DD.md` 并补上 `_record_episode` 代号。

raw 归档：[[raw/changes/2026-11-01-knowledge-atlas-index]]。
