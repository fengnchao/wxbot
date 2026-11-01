---
type: impact
status: completed
date: '2026-11-01'
---
# 用户知识库改为 Obsidian Markdown 图谱影响分析

## 需求关键词与图谱命中

需求：用户知识不再存平表，改成一人一个 Obsidian vault——实体节点是 Markdown、关系用 `[[双链]]`、原文按天写成日记文件；同时删掉并行的 `memory` 表与工具，只留一套。

图谱命中：[[tables/kb-facts]]、[[tables/kb-episodes]]、[[tables/kb-owners]]、[[symbols/knowledge-extract]]、[[symbols/knowledge-auto]]、[[apis/dashboard-knowledge]]、[[modules/runtime]]、[[modules/identity]]、[[modules/plugin]]、[[concepts/identity-authority]]。

覆盖缺口：图谱没有 `memory` 表、`UserRegistry.recall/change_memory`、`butler-memory` 工具 skill 的词条，也没有 `web/src/components/UserDialog.vue` 的记忆面板。已按源码补齐，入库时新建 [[tables/knowledge-vault]] 取代三张 kb_* 词条。

## 要改的文件、符号与调用方

存储层 `src/butler/runtime/knowledge_store.py` 整体重写：`KnowledgeStore` 保留类名与 `record/facts/read/owners/prune/episodes_of/close` 方法名，内部从 SQLite 换成 vault 文件；游标由 `extracted_upto(owner)->int` 改为 `extracted_at(owner)->float`。

- 写入方：`core.py:304` `_record_episode` → `record`；`knowledge_extract.py:88` `extract` → `episodes_of/add_fact/set_extracted_at`。
- 调度方：`knowledge_auto.py:145` `_pending` 与 `:182` `run_once` 读游标；`__main__.py:60/66` 两个 CLI 子命令。
- 只读投影：`src/dashboard/knowledge_view.py` 从直接读三张表改为委托 `KnowledgeStore`，删除 `read_episodes/_fact_where` 等重复实现。
- 注入方：`core.py:353-357` 由 `registry.recall` 换成 `knowledge.facts(owner=...)`，事件名 `butler_memory` → `butler_knowledge`，字段 `memory_count` → `fact_count`（同步 `dashboard/flow_view.py:15,18,29` 与 `dashboard/workflow_view.py:25`）。

删除的 memory 链路：`business.py` 的 `memory` 表与 `set_memory/delete_memory/memories/runtime_memory/_memory_changed`；`identity/contact_identity.py` 的 `memory_items/conflict_memories/user_memory_variants` 与两处 `memory_version` 自增；`identity/user_registry.py` 的 `recall/change_memory`、`_row` 的 `memory_count`、`link` 的 notes 合并、`adopt_legacy` 的 notes 迁移；`agent/tools.py` 的四个 memory 工具与分发；`plugins/butler-wechat/skills/tools/butler-memory/`。

## 接口与前端契约

`GET /api/knowledge` 与 `GET /api/knowledge/facts` 的响应字段保持不变（`owner/contact/kind/fact_key/fact_value/quote/episode_at/confidence/source/created`），只换数据来源；`FactsView.vue` 不需要改。

删除的接口：`GET /api/contacts/memory`（`dashboard/routes.py:34`）、`GET /api/users/memory`（`:37`）、`dashboard/user_admin.py:15` 的 `/v1/users/memory`、`identity/user_api.py:51,67-68,109-110` 的 `memory_set/memory_delete` 动作。前端 `UserDialog.vue` 的记忆面板、`ContactsView.vue` 与 `contactState.js` 的 `memory_*` 状态一并移除。

## 数据库与字段血缘

`kb_episodes`/`kb_facts`/`kb_owners` 三张表退场，`data/knowledge/*.sqlite3` 在迁移后改名为 `*.migrated` 留底，不再被读写。`business.sqlite3` 的 `memory`、`user_memory_variants` 两张表与 `user_profiles.memory_version` 列退场；`memory_version` 参与会话 scope 哈希（`backends/codex.py:62`、`compatible.py:74`），移除后旧会话 id 失配一次，表现为各自重开一个空会话，可接受。

新增 `data/knowledge/index.json`：只存 owner 目录、条数与提炼游标，可由 vault 重建，不是第二份知识。vault 内节点 frontmatter 带 `owner/name/type`，事实行尾带 `<!-- fp:…|key:…|kind:…|conf:…|at:…|quote:… -->` 去重指纹，等价于原 `kb_facts_fingerprint` 唯一索引。

## 风险、验证、异步任务与回滚

风险一：Markdown 是文本，并发写靠原子替换，没有事务；提取与回复可能同一秒写不同文件，互不覆盖，但同一节点并发写会丢一条。当前单进程写入，风险低。

风险二：`_safe()` 清洗文件名会改变实体名，两个实体清洗后同名会合并成一个节点；节点名写入 frontmatter 保留原名，可核对。

风险三：游标从 `episode.id` 改成时间戳，边界上的同一秒可能重复提取一次；指纹去重保证不产生重复事实。

验证：`tests/butler/test_knowledge_store.py`、`test_knowledge_extract.py`、`test_knowledge_auto.py`、`test_knowledge_capture.py`、`tests/dashboard/test_knowledge_view.py` 五个文件按新语义改写；另跑 `compileall src/butler`、`pytest tests/butler tests/dashboard`。不启动服务、不发微信、不调用模型。

回滚：vault 与 `*.migrated` 都在 `data/` 下，回滚代码即可让旧库重新生效；`memory` 表删除前先在 `data/knowledge/p-*/vault/` 里落成 Markdown，数据不丢。

## 实际改动与 raw 归档

实施结果与分析基本一致，偏差与补充：

- **`FactsView.vue` 是新建而非改动**：分析阶段假设它已存在，实际是本次新建（连同 `KnowledgeView.vue` 与 `web/src/styles/knowledge.css`）。页面结构、类型中文映射、会话 chips 都按新契约重写。
- **`catalogue.validate` 改为降级而非报错**：技能目录跟着安装走，删掉 `butler-memory` 后，策略里残留的白名单条目会被静默剔除并记日志，不再让整份策略判死。`tests/unit/codex/test_codex_foundation.py` 的断言随之改写。
- **事实行的 `node` 字段没有对外暴露**：`KnowledgeStore.facts` 会算出事实所属实体节点，但 `knowledge_view.FACT_FIELDS` 白名单未收录，接口仍只回 10 个字段——图谱的「节点」维度在管理台上看不到，是已知缺口。
- **`merge_users` 不搬 vault**：分析阶段未覆盖。身份合并只动 SQLite，源 vault 留在磁盘且 `index.json` 仍记着它；文件搬动不在事务内，回滚会造成不可恢复的丢失，因此有意不做。
- **`knowledge-migrate` 必须停服手动跑**：不是自动升级步骤，README 与 [[tables/knowledge-vault]] 都已写明。
- **`episodes_of` 签名从 `after_id` 改为 `after_at`**：游标语义从「原文 id 水位」变成时间水位，`knowledge_extract` / `knowledge_auto` 两个调用方一起改。
- **测试补充**：`tests/unit/test_project_wiki.py` 修掉一处写死日期的用例；`web/scripts/smoke.mjs` 的 13 处 memory 断言改写成「入口已下线」。

校验：`pytest tests` 只剩 3 个与本次无关的既有失败；`npm run build` 与 `npm run smoke` 通过（9 个页面）；Hallmark `sloplint --scope app` 对两个新页面 0 FAIL / 0 WARN；图谱 `lint` 为 OK。

raw 归档：[[raw/changes/2026-11-01-knowledge-vault-graph]]（27 个词条已 ingest）。
