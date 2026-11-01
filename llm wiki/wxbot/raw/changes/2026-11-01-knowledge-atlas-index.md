---
type: change
title: 知识库加中心索引页与七类事实分组
pages:
- tables/knowledge-vault
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
- symbols/knowledge-extract
- symbols/knowledge-auto
- modules/web
- apis/dashboard-knowledge
- concepts/message-pipeline
---
# 知识库加中心索引页与七类事实分组

## 目标与背景

`data/knowledge/p-*/vault` 已经是一人一个 Obsidian vault，但新库和纯单聊的 vault 里只有「人物/<联系人>」一个节点加若干天日记：事实行不引用日期，日记不引用节点，Obsidian 的 graph view 里就是两个互不相连的孤立点。目标是「索引之间关联」——图里必须有一张把节点与日记串起来的中心页。

顺带补上点名的分类维度（用户信息、喜好、性格、目标）：原来 `FACT_KINDS` / `FACT_SECTIONS` 只有 profile / preference / relation / event / topic 五类，模型提炼不出「性格」与「目标」。

## 文件与代码位置

- `src/butler/runtime/knowledge_store.py`
  - 常量：`FACT_KINDS`（`:45`）与 `FACT_SECTIONS`（`:46`）扩到七类，新增 `personality`（性格）/ `goal`（目标）；新增 `INDEX_SECTIONS`（`:49`，索引页专用中文标题）、`INDEX_FILE`（`:54`）、`INDEX_LIMIT`（`:55`）、`INDEX_DAYS`（`:56`）。
  - 新增 `index_page_path(owner)`（`:312`）：vault 根下的 `index.md`。
  - 新增 `rebuild_index(owner)`（`:499`–`:559`）：扫节点文件收集全部事实行，按七类分组写成带 `[[双链]]` 的条目，再列出三目录节点与最近 `INDEX_DAYS` 天日记，最后 `_atomic_write` 落盘。
  - 三处调用：`record`（`:427`）、`add_fact`（`:463`）写完各重画一次；`prune`（`:493`）删到东西后遍历 `owners()` 全部重画。
  - 模块 docstring：删掉与实现不符的「事实可以双链溯源」，补 `index.md` 行与「为什么还有 index.md」一段。
- `src/butler/runtime/knowledge_extract.py`：`KINDS`（`:21`）同步扩到七类，`PROMPT`（`:24`）的 kind 行加 `personality（性格/说话方式）` 与 `goal（目标/打算）`。
- `web/src/views/FactsView.vue`：`KINDS`（`:10`）补 `personality: '性格'`、`goal: '目标'`。
- `tests/butler/test_knowledge_store.py`：新增四条（`:144`、`:156`、`:169`、`:181`）。

## 接口与字段

- HTTP 契约不变：`GET /api/knowledge/facts` 的字段与形状没动，只是 `kind` 的取值域从五个变成七个（`profile` / `preference` / `personality` / `goal` / `relation` / `event` / `topic`）。越界值仍在写入时回落 `topic`，接口不会吐出第八种。
- 磁盘格式新增一种文件：`p-<slug>/vault/index.md`，frontmatter 为 `type: index` / `owner` / `contact` / `updated`。它不带 `fp` 注释，`facts()` 只扫 `*/*.md`（跳过日记目录），所以既不会被算成事实，也不会被当成节点。
- 分类标题分两层：节点小节名（`FACT_SECTIONS`，身份/偏好/性格/目标/关系/事件/话题）与索引页标题（`INDEX_SECTIONS`，用户信息/喜好/性格/目标/关系/经历/关注）刻意不同，节点小节改名时旧内容不会留错位置。

## 数据库与迁移

不适用：知识库已不在 SQLite 里，这次只新增一个 Markdown 文件，没有表结构变更、没有迁移脚本。

已有 vault 不需要人工处理：下一条消息（`record`）、下一条事实（`add_fact`）或下一次清理（`prune`）都会顺手把 `index.md` 重画出来。

## 前端消费点

`FactsView.vue` 的类型列通过 `KINDS` 映射中文，`kindOf`（`:207`）查不到时回落「关注话题」。不补这两行，新提炼出的性格与目标会显示成「关注话题」。索引页只在 Obsidian 里看，管理台不渲染它。

## 测试与异步任务

`tests/butler/test_knowledge_store.py` 新增四条：

- `test_index_page_ties_nodes_and_days_together`（`:144`）：索引页落在 vault 根，正文同时含 `[[101]]` 与当天日期双链。
- `test_index_page_groups_facts_by_category`（`:156`）：四类事实分别出现在四个中文标题下。
- `test_index_page_drops_expired_day_links`（`:169`）：`prune` 删掉整天日记后索引页不再留该日期的断链。
- `test_index_page_is_not_counted_as_facts`（`:181`）：索引页不进入 `facts()['total']`。

`pytest tests/butler tests/dashboard` 全绿；`npm.cmd --prefix web run build` 与 `npm.cmd --prefix web run smoke` 通过。

异步任务：`prune` 由 [[symbols/knowledge-auto]] 的调度线程发起，现在每轮清理会多写 N 份索引页（N = 目录里的人数）。这是既有线程内的同步文件写，没有新增线程或队列。

## 风险与回滚

- `rebuild_index` 每次都重扫整份 vault 收集事实：写一轮对话多一次 O(全部节点文件) 扫描。当前规模可以接受；人数或事实量上来后要改成增量维护。
- 索引页有上限：事实每类只列前 40 条（补一行「另有 N 条未列出」），日记只列 10 天。改 `INDEX_LIMIT` / `INDEX_DAYS` 即可，不需要迁移。
- 索引页会被覆盖，文件里已写明「本文件由 Butler 自动重建，手改会被覆盖」；想保留的手写笔记应放到别的文件。
- 回滚：删掉 `rebuild_index` 与三处调用、去掉 `INDEX_*` 常量与两个新 kind，再删 vault 里的 `index.md`。事实与日记都不受影响——索引页是纯派生数据。

[[impacts/2026-11-01-knowledge-atlas-index]]
