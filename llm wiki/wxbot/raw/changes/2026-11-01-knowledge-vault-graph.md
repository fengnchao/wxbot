---
type: change
title: 用户知识库改为一人一个 Obsidian vault 并删除 memory 链路
pages:
- tables/knowledge-vault
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
- apis/dashboard-knowledge
- symbols/knowledge-extract
- symbols/knowledge-auto
- modules/butler
- modules/runtime
- modules/dashboard
- modules/identity
- modules/plugin
- modules/web
- modules/wiki
- modules/common
- modules/models
- apis/butler-handle
- apis/butler-handle-stream
- apis/dashboard-queue
- apis/dashboard-workflow
- symbols/butler-handle
- symbols/butler-result
- symbols/local-model-backend
- concepts/message-pipeline
- concepts/identity-authority
- concepts/group-identity-evidence
- concepts/model-error-contract
---
# 用户知识库改为一人一个 Obsidian vault 并删除 memory 链路

## 目标与背景

用户要的是**知识图谱**：实体之间由索引互相关联，能用 Obsidian 打开、看到 graph view。旧实现是三张平表（`kb_episodes` / `kb_facts` / `kb_owners`），只能存字段，存不出拓扑——`kb_facts` 里连「这条事实说的是谁」都没有独立字段，关系更无从表达。

同时项目里存在第二套互不相通的「个人记忆」：`business.sqlite3` 的 `memory` 表 + `memory_get/set/search` 三个工具 + `butler-memory` 技能 + 管理台人物详情的记忆页签。两套存储对同一个用户各记一份，改一处不同步另一处。

本次把两者合并为一套：知识库改成**一人一个 vault**（实体是 Markdown，关系是正文里的双链），并彻底删除 memory 全链路。

## 文件与代码位置

存储层（新增）：

- `src/butler/runtime/knowledge_store.py` — `KnowledgeStore` 全部重写：`owner_slug`（`:63`）、`_safe`（`:69`）、`_atomic_write`（`:93`）、事实行序列化 `_fact_line`（`:128`）与解析 `_parse_fact_line`（`:146`）、日记块 `_episode_block`（`:216`）、`record`（`:394`）、`add_fact`（`:415`）、`episodes_of`（`:485`）、`read`（`:501`）、`facts`（`:530`）、`sessions`（`:568`）、迁移 `_import_sqlite`（`:593`）/`_import_memory`（`:617`）/`migrate_legacy`（`:639`）。

提炼链路（改）：

- `src/butler/runtime/knowledge_extract.py` — `PROMPT`（`:24`）要求模型额外输出 `subject` / `subject_type` / `links`；`parse_facts`（`:72`）校验这三项；`_links`（`:55`）归一两种写法；游标从 `extracted_upto`（原文 id）换成 `extracted_at`（时刻），`extract`（`:120`）用 `last_at = max(row['at'])` 推进。
- `src/butler/runtime/knowledge_auto.py` — `_pending`（`:145`）改用 `episodes_of(after_at=store.extracted_at(...))` 算积压；`_prune`（`:238`）只删过期日记文件。

业务侧（改）：

- `src/butler/agent/core.py` — `_recall` 改为知识召回（走 `KnowledgeStore`），`_record_episode` 改为 `record` 写 vault。
- `src/butler/agent/tools.py` — 删除 `memory_get` / `memory_set` / `memory_search` 及其 schema；`TOOL_SCHEMAS` 只剩 8 项，`READ_TOOLS` 相应收缩。
- `src/butler/agent/catalogue.py` — `validate()` 从抛 `ValueError` 改为降级剔除（白名单里未安装的技能记日志后移除），因为 `butler-memory` 技能目录已删。
- `src/butler/business.py` — 删除 `memories` / `set_memory` 等读写方法。
- `src/butler/__main__.py` — `knowledge-migrate` 子命令接 `migrate_legacy`（`:57`）。
- `src/butler/server.py` — `GET` / `POST /v1/knowledge/extract`（`:141` / `:321`）。

插件（删）：

- `plugins/butler-wechat/skills/tools/butler-memory/SKILL.md` — 整目录删除。

管理台（改）：

- `src/dashboard/knowledge_view.py` — 只读投影重写为对 `KnowledgeStore` 的委托：`owners`（`:32`）、`read`（`:46`）、`facts`（`:60`）；`_ro` / `_sessions` / `_owners_from_index` / `_owners_from_disk` / `_episode_sessions` / `_fact_sessions` 全部删除。
- `src/dashboard/api/knowledge.py` — `_view`（`:10`）直接构造 `ctx.KnowledgeView(cfg.data_path() / 'knowledge')`。
- `src/dashboard/api/contacts.py`、`src/dashboard/api/support.py` — 删除 `/api/contacts/memory` 读写与合并预览里的记忆字段。
- `src/dashboard/flow_view.py` — 阶段名 `butler_memory` 改为 `butler_knowledge`，摘要字段 `memory_count` / `memory_conflicts` 改为 `fact_count`。
- `src/dashboard/routes.py` — 知识三条 GET + 一条 POST 保持原位（`:43`–`:45`、`:66`）。

前端（改/增）：

- 新增 `web/src/views/KnowledgeView.vue`（对话记录）、`web/src/views/FactsView.vue`（知识库）、`web/src/styles/knowledge.css`。
- `web/src/components/UserDialog.vue`、`ContactMergeDialog.vue`、`ContactsView.vue` — 删除记忆页签、记忆编辑弹窗与记忆字段。
- `web/src/components/WorkflowTrace.vue`、`web/src/flow.js` — 阶段标签改「知识召回」，`memory_count` 改 `fact_count`。
- `web/scripts/smoke.mjs` — 断言改为「个人记忆入口已下线」。

文档与工具：

- `README.md` — 知识库章节改为 vault 形态与 `knowledge-migrate` 步骤。
- `tools/probe_codex.py` — 探针里去掉 memory 工具。

## 接口与字段

对外 HTTP 契约**形状不变**，只是数据源换了：

- `GET /api/knowledge` — 原文行 7 字段 `owner` / `at` / `contact` / `channel_type` / `user_text` / `reply_text` / `outcome`。`request_id` 不再外露。
- `GET /api/knowledge/facts` — 事实行 10 字段，`node`（事实所属实体节点）虽然由 `KnowledgeStore.facts` 算出，但投影层白名单未收录，**当前不返回**。
- `GET/POST /api/knowledge/extract` — 状态字段与 202/400/409/503 语义完全不变。
- `owners[]` 每项 `{owner, name, contact, channel_type, episodes, facts, last_at, sessions}` 不变。

被删除的接口：

- `GET /api/contacts/memory`、`POST /api/contacts/memory` — 连同 `memory_set` 动作一起下线。
- 合并预览响应里的 `memory_count` / `memory_conflicts` 字段删除，`rules` 文案改为「保留目标人物；群身份与窗口并入，窗口现有策略保持原行为。」。

工具接口：

- Agent 可见工具从 11 项降到 8 项，`memory_get` / `memory_set` / `memory_search` 不再存在；策略里的 `allowed_tools` 含这些名字时按未安装处理（`catalogue.validate` 降级剔除）。

## 数据库与迁移

三张表全部退场，改由文件承担：

| 旧 | 新 |
|---|---|
| `data/knowledge/p-*/episodes.sqlite3`（`kb_episodes`） | `p-*/vault/对话/YYYY-MM-DD.md` |
| `data/knowledge/p-*/facts.sqlite3`（`kb_facts`） | `p-*/vault/{人物,组织,话题}/*.md` 的事实行 |
| `data/knowledge/index.sqlite3`（`kb_owners`） | `data/knowledge/index.json`（可重建缓存） |
| `business.sqlite3` 的 `memory` 表 | 迁移成 `kind=profile`、`source=memory-migration` 的节点事实 |

迁移入口 `python -m butler knowledge-migrate`（`migrate_legacy`，`knowledge_store.py:639`）。**必须在停服状态下手动执行一次**，否则旧库里的原文与事实不会出现在 vault 里。迁移幂等：`record` 靠 `rid` 判重、`add_fact` 靠 `fp` 判重。原文件搬完改名留底（`knowledge.legacy.sqlite3`、`episodes.sqlite3.migrated`、`facts.sqlite3.migrated`、`index.sqlite3.migrated`），不删除。

没有 schema 版本号：Markdown frontmatter 与 `index.json` 都允许未知键原样保留。

## 前端消费点

- `web/src/views/KnowledgeView.vue` — 对话记录页，`apiGet('/api/knowledge?...')`（`:61`）。左栏人列表 + 会话 chips，右栏原文行。
- `web/src/views/FactsView.vue` — 知识库页，`apiGet('/api/knowledge/facts?...')`（`:98`）；自动提炼状态条 `loadExtract()`（`:111`）/ `runExtract()`（`:121`）调 `/api/knowledge/extract`。
- `web/src/router.js` — 两页路由与导航标签（「对话记录」「知识库」）。
- `web/src/components/ContactsView.vue` — 人物详情 `TABS` 去掉 `memory`，不再有记忆页签。
- `web/src/components/UserDialog.vue` — 删除记忆编辑表单与「记忆编辑」按钮。
- `web/src/components/ContactMergeDialog.vue` — 合并预览不再显示记忆条数/冲突。
- `web/src/components/WorkflowTrace.vue` + `web/src/flow.js` — 工作流阶段 `butler_knowledge` 显示为「知识召回」，摘要显示 `fact_count`。

## 测试与异步任务

本地用例（`tests/` git-ignored）：

- `tests/butler/test_knowledge_store.py` — 双链生成、指纹去重、`prune` 不动节点事实、`index.json` 重建。
- `tests/butler/test_knowledge_extract.py` — 解析容错、游标前进/不前移、幂等、dry-run。
- `tests/butler/test_knowledge_auto.py` — 调度选人、退避、HTTP 状态与单次手动触发。
- `tests/dashboard/test_knowledge_view.py` — 只读投影、空态不建目录、会话筛选、四条路由与 503 门禁。
- `tests/unit/codex/test_codex_foundation.py` — 工具集换成 `reminder_*`，`catalogue.validate` 改为降级断言。
- `tests/unit/test_project_wiki.py` — 修正写死日期的用例。
- `web/scripts/smoke.mjs` — 9 个页面渲染断言，`npm run smoke` 通过。

异步任务：提炼仍在 Butler 进程内的后台线程（`ExtractScheduler`），间隔、批量、`min_backlog`、空闲让路、指数退避全部沿用；`prune` 仍由同一把跨进程锁串行化，只删日记文件，节点事实不参与过期。

## 风险与回滚

风险：

1. **合并用户不搬 vault**：`merge_users` 只合并身份与窗口，源 vault 仍留在磁盘且 `index.json` 仍记着它，新人看不到被合并者的历史。有意为之——文件搬动不在 SQLite 事务内，回滚会造成不可恢复的丢失。
2. **没有事务**：同一节点的并发写会丢一条；当前只有 Butler 单进程写入。
3. **游标是时刻**：同一秒内晚到的原文可能被跳过。
4. **管理台查询是 O(全部文件)**：`q` 与 `owner` 都在内存过滤，一次请求遍历所有人整个 vault。
5. **必须手动迁移**：升级后忘了跑 `knowledge-migrate`，界面会显示「还没记录过」而不是报错，容易被误判成数据丢了。

回滚：

- 代码回滚到上一版本即可恢复旧的 SQLite 读写路径；迁移把源文件改名而非删除，`knowledge.legacy.sqlite3` / `episodes.sqlite3.migrated` / `facts.sqlite3.migrated` 可直接改回原名。
- vault 目录是新增产物，回滚后不会被旧代码读取，可以直接保留或手工归档。
- `business.sqlite3` 的 `memory` 表在迁移中**只读不删**，回滚后旧代码仍能读到自己那套记忆。

[[tables/knowledge-vault]]
