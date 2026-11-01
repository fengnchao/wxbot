---
type: change
title: 知识库拆分为一人一库并新增提炼事实库
pages: [tables/kb-episodes, tables/kb-facts, tables/kb-owners, apis/dashboard-knowledge,
  apis/butler-handle, apis/dashboard-queue, apis/dashboard-workflow,
  concepts/message-pipeline, concepts/model-error-contract,
  symbols/knowledge-extract, symbols/butler-handle, symbols/butler-result,
  modules/butler, modules/dashboard, modules/web, modules/runtime]
---
# 知识库拆分为一人一库并新增提炼事实库

## 目标与背景

上一批（[[raw/changes/2026-11-01-knowledge-episodes]]）把 L1 原文放进单库 `data/knowledge.sqlite3`。这带来两个问题：任何一个人的数据损坏、被导出或整体清空都会牵连所有人；而原文按保留期过期，正好会把「从原文提炼出来的长期事实」一起删掉。

所以本次做三件事：

1. **一人一库**：`data/knowledge/index.sqlite3` 只当目录，每个 owner 一个 `p-<slug>/` 目录，目录下原文与事实各一个库。
2. **新增 L2 事实层**：`kb_facts` 存从原文提炼出的画像、偏好、关系、约定与长期话题，不随原文过期。
3. **只读投影与管理台按新结构重做**，并新增「知识库」一页。

**边界同样重要**：仍然不改对话 prompt、不改记忆注入、不挂常驻线程。提炼是人工触发的 CLI；既有的 `business.sqlite3` 里 `memory` 表（模型在对话中主动调工具写的 L2）完全没有动。两套事实各走各的入口，本批不合并。

## 文件与代码位置

- `src/butler/runtime/knowledge_store.py` — 全量重写（159 行 → 478 行）。
  - `:32` `EPISODES_SCHEMA`、`:49` `FACTS_SCHEMA`、`:70` `INDEX_SCHEMA` 三套建表脚本。
  - `:95` `owner_slug`，`:118` `_connect`，`:135` `_ensure_column`，`:144` `read_episodes`（现在只查单个库，不再带 owner 过滤参数以外的跨库语义）。
  - `:157` `KnowledgeStore`：`:181` `_open`（按 kind+owner 缓存连接）、`:218` `_touch_owner`、`:262` `extracted_upto` / `:270` `set_extracted_upto`、`:276` `record`、`:303` `add_fact`、`:332` `prune`、`:347` `_rebuild_counts`、`:373` `read`、`:400` `facts`、`:430` `episodes_of`。
  - `:441` `migrate_legacy(data_dir)` 模块级函数。
- `src/butler/runtime/knowledge_extract.py` — 新文件（139 行）：`:19` `PROMPT`、`:44` `parse_facts`、`:78` `render`、`:88` `extract`、`:120` `extract_all`。
- `src/butler/agent/core.py:114` — `Butler.__init__` 里库根从 `data/knowledge.sqlite3` 改成 `data/knowledge`（目录）。
- `src/butler/__main__.py:53` — `knowledge-prune` / `knowledge-migrate` 共用分支，`:66` 新增 `knowledge-extract` 分支；`:15` 命令白名单、`:22` 附近的 `--owner/--batch/--dry-run` 参数。
- `src/dashboard/knowledge_view.py` — 全量重写（39 行 → 175 行）：`:23` `_ro`、`:33` `KnowledgeView`、`:44` `_owners_from_index`、`:59` `_owners_from_disk`、`:85` `read`、`:119` `facts`。
- `src/dashboard/api/knowledge.py` — `:10` `_view`、`:16` `read`、`:25` `facts`。
- `src/dashboard/routes.py:17`（`BUSINESS_GET`）、`:43`/`:44`（两条 GET 路由）。
- `web/src/views/KnowledgeView.vue` — 左栏由 `contacts: string[]` 改为 `owners: object[]`，筛选参数 `contact` → `owner`。
- `web/src/views/FactsView.vue` — 新页面（168 行）。
- `web/src/router.js:8`、`web/src/App.vue:8`/`:18`/`:45`/`:70` — 注册「知识库」页、远端模式隐藏、搜索框占位符。
- `web/src/styles/knowledge.css` — 两页共用；补 `.fact-table` 与右栏焦点环。
- `web/scripts/smoke.mjs` — `/api/knowledge` 假数据改 `owners` 结构，新增 `/api/knowledge/facts`，导航断言 7 → 8。
- `tests/conftest.py:138` — `make_home` 造 `Config` 时补 `data_dir=str(root/'data')`。

**明确不写入的位置**：`business.sqlite3` 的 `memory` 表、`user_memory_variants`、`user_profiles.memory_version` 一律不动；`_handle_request` 的落库调用点与异常包装维持原样（只是 store 内部换了路径）。

**图谱伴生更新**：`core.py` 与 `routes.py` 本批只做了同行替换（库根路径字符串、新增两条路由），但 `source-drift` 按整文件 digest 比对，所以引用了这两个文件的 7 个词条一并复核并追加本记录：[[apis/butler-handle]]、[[apis/dashboard-queue]]、[[apis/dashboard-workflow]]、[[concepts/message-pipeline]]、[[concepts/model-error-contract]]、[[symbols/butler-handle]]、[[symbols/butler-result]]。复核结论：锚点行号全部未漂移（`core.py` 的 `:65` / `:70` / `:210` / `:252` / `:266` / `:301` / `:317`，`routes.py` 的 `:39` / `:42`），正文只补了路径与端点数量，原有契约结论不变。

## 接口与字段

`GET /api/knowledge` 与新增的 `GET /api/knowledge/facts` 对称：

- 参数由 `contact` 改为 `owner`（精确匹配身份稳定键）；`owner` 非法值只会在内存里筛出空集，不进 SQL。
- 响应里 `contacts[]` 换成 `owners[]`，每项 `{owner, name, contact, channel_type, episodes, facts, last_at}`，供左栏列出可筛选的人。
- 事实行字段：`owner` / `contact` / `kind` / `fact_key` / `fact_value` / `quote` / `episode_at` / `confidence` / `source` / `created`。`fingerprint` 与 `id` 都不对外返回：前者是内部去重键，后者只用于同一秒内的稳定排序。
- `read` 的行集合与上一批一致，仍是 `at` / `contact` / `channel_type` / `user_text` / `reply_text` / `outcome`；`owner` 仍不外露。

**库不存在仍是空态**：`available: false` 加空数组，只读侧绝不建目录建表。索引库缺失或损坏时退回扫 `p-*/episodes.sqlite3`，从库内 `distinct owner` 反推目录。

## 数据库与迁移

```
data/knowledge/
  index.sqlite3            kb_owners：目录名、展示名、条数、时间范围、提炼游标
  p-<slug>/
    episodes.sqlite3       kb_episodes（L1 原文，按 retention_days 过期）
    facts.sqlite3          kb_facts（L2 事实，长期有效）
```

`slug = 'p-' + sha1(owner)[:16]`：`owner` 形如 `user:<uuid>` / `anon:group:产品群`，带冒号和中文，不能直接当目录名；反查由索引库负责。

索引变化：`kb_episodes_at` 改为 `(at DESC, id DESC)`（分页直接吃索引）；部分唯一索引从 `(owner, request_id)` 收紧成 `(request_id)`——每个库已经只装一个人，owner 维度冗余了。`kb_episodes_owner_at` 删除，同理。

`kb_facts` 的唯一索引建在 `fingerprint = sha1(kind|fact_key|fact_value)` 上而不是 `fact_key` 上：同一件事的同一说法只留一条，措辞不同的矛盾陈述各留一条，不互相覆盖。

扩展方式：`extracted_upto` 用 `_ensure_column` 补（`CREATE TABLE IF NOT EXISTS` 已存在时不会改结构），老索引库打开即补列。

迁移：`python -m butler knowledge-migrate` 把旧的 `data/knowledge.sqlite3` 逐条 `record` 进新结构，成功后原名改 `data/knowledge.legacy.sqlite3` 留底并清掉 `-wal/-shm`。只处理一次；旧库不存在直接返回 0，不建任何东西。

## 前端消费点

`KnowledgeView.vue` 与新的 `FactsView.vue` 共用 `knowledge.css`：左栏 `.user` 列表、右栏表格、固定 50 条分页。

`FactsView.vue` 六列：时间 / 联系人 / 类型 / 事实 / 原话 / 置信。`kind` 映射成「身份背景 / 偏好习惯 / 关系 / 约定事件 / 关注话题」，置信度显示成百分比，低于 50% 的行降权并在页脚计数。左栏条文案是「群聊，N 条原文，M 条事实」（逗号分隔，不用中点串）。

左栏项带 `tabindex="0"` + `role="button"` + 回车/空格键处理，`:focus-visible` 用既有强调色画内焦点环——键盘也要能选人。

两页都只在 `available=false` 时显示空态与「事实由 `python -m butler knowledge-extract` 整理」的说明，**页面上没有触发按钮**：提炼要跑模型几十秒，不能挂在 HTTP 请求里。

## 测试与异步任务

- `tests/butler/test_knowledge_store.py`（14 项）：分库落盘位置、`owner_slug` 稳定、prune 只删原文不删事实、跨库按时间归并、`add_fact` 指纹去重与矛盾陈述并存、`migrate_legacy` 拆分与留底。
- `tests/dashboard/test_knowledge_view.py`（9 项）：空态不建目录、空文件按空态、跨库分页、索引缺失降级扫目录、坏库抛 `RuntimeError`、`facts` 独立读、相对 `data_dir` 仍能 `mode=ro` 打开、两条 HTTP 路由的 200 与远端模式 503。
- `tests/butler/test_knowledge_capture.py`（6 项）：新增「两个联系人落在两个库」。
- `tests/butler/test_knowledge_extract.py`（9 项）：解析容错（围栏、坏项、非 JSON）、游标只在成功后前移、空数组算成功、重复提炼幂等、dry-run 不写库不前移、单人失败不中断整批、owner 过滤。
- `web/scripts/smoke.mjs`：8 个导航标签、两个页面的行数与关键文案。

**没有异步任务**：`knowledge-prune` / `knowledge-migrate` / `knowledge-extract` 都是人工触发的 CLI 子命令，不在 `serve()` 里挂线程。

顺带修掉一处测试污染：`tests/conftest.py` 的 `make_home` 原来没传 `data_dir`，`Config` 默认值是 `'data'`，于是每个调 `butler.handle()` 的用例都把假对话写进仓库真实的 `data/knowledge/`。补上临时目录后，全量 pytest 跑完真实库零新增。

## 风险与回滚

- 目录数量：N 个联系人 = N 个目录 + 3 个库文件，量大时 `read()` 要遍历所有库再归并。每库各自 `LIMIT offset+limit` 后归并切片，正确但不是最优；量级上来需要索引库兜住分页。
- 索引库是单点：丢了不影响数据，但会退化成扫目录（事实条数显示为 0，因为事实库不在降级路径里反查）。
- 事实层没有写权限收口：`add_fact` 由提炼 CLI 调用，管理台只有只读路由，目前不存在从 HTTP 侧写入的可能。
- 隐私：`owner` 仍未确认身份时落 `anon:<channel_type>:<contact>`；事实行带 `quote`（用户原话片段），与原文同源同级，不外泄给未授权方。
- 回滚：删掉 `knowledge_extract.py` 与 `FactsView.vue`，把 `knowledge_store.py` 恢复成单库版本、`core.py:114` 路径改回 `data/knowledge.sqlite3`，管理台与前端去掉 facts 相关改动即可。旧库没有删除，`knowledge.legacy.sqlite3` 可直接改名回滚。
