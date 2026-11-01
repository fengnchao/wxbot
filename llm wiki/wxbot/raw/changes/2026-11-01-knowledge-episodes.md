---
type: change
title: L1 聊天原文落库与只读看板
pages: [tables/kb-episodes, apis/dashboard-knowledge, modules/butler, modules/dashboard, modules/web,
  apis/butler-handle, apis/dashboard-queue, apis/dashboard-workflow, symbols/butler-handle,
  symbols/butler-result, concepts/message-pipeline, concepts/model-error-contract]
---
# L1 聊天原文落库与只读看板

## 目标与背景

三层知识库（L1 原文 → L2 事实 → L3 图谱）的第一步，只做原文沉淀：每轮对话写一条记录，管理台能按联系人翻看。

**边界是这次改动最重要的部分**：不抽取、不改 prompt、不新增线程、不动现有批次状态机。写库失败只记日志，绝不影响回复——上一轮的模型失败契约（[[concepts/model-error-contract]]）不能因为多了一个落库动作而被削弱。

原文必须落在独立库：`business.sqlite3` 每次启动整库备份，把聊天原文塞进去会让备份体积随时间失控。

## 文件与代码位置

- `src/butler/runtime/knowledge_store.py` — 新文件。`episode_owner`、`read_episodes`、`KnowledgeStore`（`_connect` / `_transaction` / `record` / `prune` / `read`），建表 SQL 在 `_SCHEMA`。
- `src/butler/agent/core.py:114` — `Butler.__init__` 构造 `self.knowledge`，`retention_days` 取自配置。
- `src/butler/agent/core.py:270` — `_handle_request` 里 `c = None` 提前初始化：异常可能发生在认人之前，落库要靠 `contact_name` 兜底。
- `src/butler/agent/core.py:293` — try 块内 `result` 赋值之后落 `ok` / `silent`。
- `src/butler/agent/core.py:298` — except 分支 `raise` 之前落 `error`，`reply=None`。
- `src/butler/agent/core.py:304` — 新增 `_record_episode`，内部 `try/except Exception` 全包，失败只 `self.log`，禁止上抛。
- `src/butler/config.py:73` — 新增 `knowledge_enabled` / `knowledge_retention_days` 两个默认值。
- `src/butler/config.py:192` — `load()` 读 `[knowledge]`，`retention_days` 校验为 1..3650 的整数。
- `src/butler/__main__.py:50` — 新增 `knowledge-prune` 子命令。
- `src/dashboard/knowledge_view.py` — 新文件，只读投影 `KnowledgeView`。
- `src/dashboard/api/knowledge.py` — 新文件，`read(ctx)` 胶水。
- `src/dashboard/routes.py:17`、`:43` — `BUSINESS_GET` 与 `ROUTES` 各加一条。
- `src/dashboard/server.py:49` — 导入 `KnowledgeView`，使其可通过 `RequestContext` 命名空间解析取到。
- `web/src/views/KnowledgeView.vue`、`web/src/styles/knowledge.css` — 新页面与窄屏样式。
- `web/src/router.js:7`、`web/src/App.vue:9`/`:18`/`:43`/`:67` — 注册页面、共享搜索框占位符、远端模式下隐藏。
- `config.butler.toml` — 新增 `[knowledge] enabled = true` / `retention_days = 90`（本地运行配置，不入 Git）。

**明确不写入的位置**：`_handle` 内部各 return 点（会重复记）、群聊的 `public` 群上下文快照（那是**其他成员**的发言，写进当前 owner 会造成跨人泄漏）、`handle()` 的 `ModelConfigurationError` 分支（没经过模型，不属于对话）。

## 接口与字段

新增 `GET /api/knowledge`，参数 `contact`（精确）、`q`（`user_text` / `reply_text` 的 LIKE，`%` 与 `_` 转义）、`limit`（默认 50，截断 1..200）、`offset`。响应 `{available, rows[], total, contacts[], limit, offset, has_more}`，行内只有 `at` / `contact` / `channel_type` / `user_text` / `reply_text` / `outcome`；`owner` 与 `request_id` 不对外暴露。

**库不存在返回 `available: false` 而不是 404/500**：P0 默认就没有历史，空态不是错误。只有真正读不动（`sqlite3.Error`）才折成 `500` 且带 `read_only: true`，与 `/api/queue` 同形。

**`handle` 的契约一个字都没改**：请求体、响应字段、`meta.reply_complete`、`retry_safe` 全部维持原样，wxbot 适配器与队列 worker 不需要任何配合改动。

## 数据库与迁移

新库 `cfg.data_path()/'knowledge.sqlite3'`，单表 `kb_episodes`，详见 [[tables/kb-episodes]]。

三个索引：`(owner, at DESC)` 供按人翻页、`(at)` 供清理扫描、部分唯一 `(owner, request_id) WHERE request_id <> ''` 供 `INSERT OR IGNORE` 去重。

**没有 schema 版本号，也没有迁移**：`CREATE TABLE IF NOT EXISTS` 一次建齐。**刻意不加 `state` 列**——P0 没有抽取流程，列一旦存在就会被误读成"这里有状态机"；P1 需要时 `ALTER TABLE ADD COLUMN state TEXT NOT NULL DEFAULT 'raw'` 补即可。

**库文件由第一次写入创建**（`KnowledgeStore._connect` 惰性连接），因此 `enabled=false` 时一个字节都不落盘。只读侧永远不建库、不建表。

## 前端消费点

`KnowledgeView.vue` 新增 `/knowledge` 一页，登记进共享导航壳的「消息监控」组。纯只读：不提供删除、编辑、导出，也没有任何 POST 路由。

四状态齐备：加载中、空态（`available=false` 显示「尚未记录任何对话」而非报错）、错误、有数据。表格列是时间 / 联系人 / 用户 / 机器人，`outcome='error'` 的行降权并标注「本轮失败」，`silent` 标「未回复」。分页固定 50，上一页 / 下一页。

联系人筛选采用**左侧栏列表**而不是下拉框：项目 shell 本来就是侧栏制（QueueView / JobsView / ContactsView 一致），下拉会和侧栏重复同一功能，所以按现有 shell 走。

窄屏（≤560px）四列塞不进一屏，改为按行堆叠并给原文/回复补「用户」「机器人」标签，而不是让人横向拖动去找回复。

`web/dist/` 随本次一并更新。

## 测试与异步任务

本地用例（`tests/` 不入 Git）：

- `tests/butler/test_knowledge_store.py` — 写入与 `request_id` 去重、跨 owner 同 ID 各自成立、空 ID 不去重、owner 退化四种情形、prune 边界（恰好到期保留）、分页与筛选、`limit` 上限截断、`%` 当字面量。
- `tests/dashboard/test_knowledge_view.py` — 库不存在时 `available=false` 且**不创建文件**、空文件无表按空态、不返回 `owner`/`request_id`、筛选分页、损坏文件抛 `RuntimeError`。
- `tests/butler/test_knowledge_capture.py` — 假 backend 正常一轮断言行数与 `outcome='ok'`、未知联系人落 `anon:dm:101`、后端抛错时写 `outcome='error'` 且异常照常上抛、写库自身抛异常时回复仍正常返回、`enabled=false` 时不落盘。

`web/scripts/smoke.mjs` 增加对话记录页断言：渲染行数、原文与回复可见、失败标注、分页总数、按联系人筛选。不使用真实微信、不读写真实剪贴板。

**没有异步任务**：`knowledge-prune` 是人工触发的 CLI 子命令，不挂常驻线程，也不在 `serve()` 启动时跑。P0 数据量小，等 P4 的调度器接管。

## 风险与回滚

- 体积与保留期：原文只增不减直到执行 `knowledge-prune`，默认保留 90 天。`retention_days` 上限锁在 3650，避免配置写错成天文数字。
- 隐私：`owner` 未确认身份时落 `anon:<channel_type>:<contact>`，不会把匿名发言挂到某个真人名下；群聊只记当前轮的用户原文，不记其他成员的上下文快照。只读页不返回 `owner`，界面上看不到内部身份键。
- 写入链路：`_record_episode` 全部异常吞掉并只记一行日志，所以知识库故障不会拖垮回复；用例显式覆盖了"写库抛异常时回复照常返回"。
- 检索：`q` 走 LIKE 全表扫，P0 量级可接受；量级上来后需要换 FTS，属于 P1 的事。
- 回滚：删掉两个 dashboard 新文件与 web 页面、恢复 `routes.py` / `server.py` / `router.js` / `App.vue`，并把 `core.py` 的三处调用与 `_record_episode` 去掉即可。库文件独立，回滚不需要动 `business.sqlite3`；不删库就只是留下一个不再被读的表。
