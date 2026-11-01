---
type: change
title: 自动提炼：进程内调度器、跨进程单飞与管理台状态
pages: [apis/butler-handle, apis/butler-handle-stream, apis/dashboard-knowledge, apis/dashboard-queue,
  apis/dashboard-workflow, concepts/model-error-contract, modules/butler, modules/dashboard,
  modules/models, modules/runtime, modules/web, modules/wiki, symbols/butler-handle,
  symbols/butler-result, symbols/knowledge-auto, symbols/knowledge-extract, tables/kb-episodes,
  tables/kb-facts, tables/kb-owners]
---
# 自动提炼：进程内调度器、跨进程单飞与管理台状态

## 目标与背景

[[symbols/knowledge-extract]] 之前只有一条人工链路：`python -m butler knowledge-extract`。
没人记得敲命令，[[tables/kb-episodes]] 里的原文就一直不变成 [[tables/kb-facts]] 里的事实；
本地实测 2 条原文、0 条事实。

本轮把「什么时候提炼」交给 Butler 进程内的一个单线程调度器（方案 A），并把过期原文清理并入同一调度器；
人工命令保留，但和调度器共用一把跨进程锁，避免同一批原文被送两次模型。

## 文件与代码位置

- `src/butler/runtime/knowledge_auto.py`（新增）
  - `LOCK_STALE_SECONDS`（`:21`）、`acquire`（`:29`）、`release`（`:62`）：O_EXCL 建锁，mtime 超过 30 分钟视为上次进程崩溃并回收。
  - `ExtractScheduler`（`:71`）：`status`（`:124`）、`_pending`（`:145`）、`run_once`（`:163`）、
    `_record`（`:199`）、`_prune`（`:238`）、`_round`（`:258`）、`_loop`（`:276`）、`start`、`stop`、`trigger`（`:320`）。
- `src/butler/config.py`
  - `Config` 新增 9 个字段（`:75`–`:84`）：`knowledge_auto_extract`、`knowledge_extract_interval_minutes`、
    `knowledge_extract_batch`、`knowledge_extract_max_owners`、`knowledge_extract_min_backlog`、
    `knowledge_extract_idle_seconds`、`knowledge_extract_retry_minutes`、`knowledge_auto_prune`、
    `knowledge_prune_interval_hours`。
  - 路径方法 `knowledge_extract_state_path`（`:172`）、`knowledge_extract_audit_path`（`:176`）、
    `knowledge_extract_lock_path`（`:179`）。
  - `load()` 新增 `bounded`（`:221`）逐项校验区间；`auto_extract` / `auto_prune` 默认 `False`（`:228`、`:229`）。
- `src/butler/server.py`
  - GET `/v1/knowledge/extract`（`:142`）、POST 同名（`:322`）。
  - `make_handler(..., extract=None)`（`:51`）；`serve()` 构造（`:477`）、`start()`（`:488`）、`stop()`（`:496`）。
- `src/butler/agent/hermes.py:73` 与 `src/butler/runtime/concurrency.py:17`：`extract` 不再落进 `chat` 作用域，
  与 `heartbeat` 并列单列，避免常驻提炼累积聊天上下文、也避免和回复抢同一把会话锁。
- `src/butler/__main__.py:74`：CLI 提炼先抢同一把锁，抢不到输出 `自动提炼正在运行，稍后再试` 并返回 1。
- `src/dashboard/api/knowledge.py`：`extract_status`（`:47`）、`extract_trigger`（`:57`）。
- `src/dashboard/api/support.py`：把心跳那次的转发抽成 `_butler_post` 公共函数，`trigger_butler_heartbeat` 与新的 `trigger_butler_extract` 共用；非本机模式的报错文案顺带从「当前模式的心跳由对端管理台维护」统一成「当前模式由对端管理台维护」。
- `src/dashboard/routes.py`：GET 路由（`:47`）、POST 路由（`:68`），并加入 GET/POST 门禁清单（`:18`、`:25`）。
- `src/dashboard/config_view.py:53`：`BT_DEFAULTS['knowledge']`，配置页可编辑这组开关。
- `src/dashboard/config_schema.py:92`–`:101`：字段中文名、含义与取值范围。
- `web/src/views/FactsView.vue`：`extractLine`（`:53`）、`loadExtract`（`:111`）、`runExtract`（`:121`）、
  状态条模板（`:259`）。
- `web/src/styles/knowledge.css:41`：`.extract-bar` 一节，只用既有令牌。
- `web/src/views/ConfigurationView.vue:14`、`:134`：新增「知识库」分类并归位 `butler.knowledge`。

### 连带修正的词条锚点

本批往 `server.py`（新增两个路由分支与两个参数）、`routes.py`（新增三行 GET、一行 POST）、
`config_schema.py`（新增知识库字段表）、`config_view.py`（新增分类）、`README.md`（新增知识库一节）
里插了行，一批既有词条的行号因此后移。这里只改锚点与代码依据，不改结论：
[[apis/butler-handle]]、[[apis/butler-handle-stream]]、[[apis/dashboard-queue]]、[[apis/dashboard-workflow]]、
[[symbols/butler-handle]]、[[symbols/butler-result]]、[[concepts/model-error-contract]]、[[modules/butler]]、
[[modules/dashboard]]、[[modules/models]]、[[modules/wiki]]、[[tables/kb-facts]]。

## 接口与字段

Butler 新增两个端点，都要求既有 Bearer token：

| 方法 | 路径 | 语义 |
|---|---|---|
| GET | `/v1/knowledge/extract` | `enabled`、`knowledge_enabled`、`auto_extract`、`auto_prune`、`interval_minutes`、`batch`、`max_owners`、`min_backlog`、`idle_seconds`、`next_run_at`、`last_run_at`、`last_report`、`failures`、`last_error`、`next_prune_at` |
| POST | `/v1/knowledge/extract` | `{owner?, batch?, dry_run?}`；202 启动，409 `busy`，503 调度器未启用 |

管理台 `GET /api/knowledge/extract` 透传 Butler 响应并补 `available`；Butler 不可达时返回
`{available: false, error}`（200，不是 500），前端按降级处理。`POST /api/knowledge/extract` 只透传
`owner` / `batch` / `dry_run`；参数合法性由 Butler 判（非整数 `batch`、非布尔 `dry_run`、超长 `owner` 各回 400），
管理台把 400/409 原样往上递。

单轮判定顺序写在 `_round`（`src/butler/runtime/knowledge_auto.py:258`）：开关 → 到点 → 最近
`idle_seconds` 内无人说话 → 有积压 → 抢到跨进程锁。前四条不满足只推迟（`deferred` / `no_backlog` / `skipped`），
不算失败；只有模型调用与写库异常才累加 `failures` 并按
`min(6h, retry_minutes * 2^(failures-1))` 退避。

## 数据库与迁移

不涉及。没有新增表、列或索引，[[tables/kb-owners]] 的 `extracted_upto` 仍是唯一游标，
[[tables/kb-episodes]] 的 `at` 仍是 prune 的唯一依据。

新增的是运行时文件，都在 `data/cache/`：`knowledge_extract_state.json`（下次时间、失败计数、上次报告）、
`knowledge_extract_audit.jsonl`（只记事件、条数与错误类型）、`knowledge_extract.lock`（跨进程单飞）。
它们不入库、不进发布包。

## 前端消费点

- 知识库页顶部新增一行状态：开关是否打开、上次提炼时间与写入条数、下次时间；失败时显示错误类型与重试时间。
  实现是 `extractLine` 计算属性，不摆装饰性状态灯。
- 「立即提炼」按钮只在拿到 Butler 状态时出现；触发后先给即时反馈，4 秒刷新状态、15 秒刷新事实表格。
  Butler 无此端点（旧进程）时显示「读不到自动提炼状态」并隐藏按钮，页面其余部分照常只读展示。
- 配置管理新增「知识库」分类，11 个字段可编辑；`auto_extract` / `auto_prune` 以布尔下拉呈现，
  保存后提示需自行重启 Butler。
- `web/scripts/smoke.mjs` 新增 `/api/knowledge/extract` 假数据与 `/api/configuration` 的 knowledge 段，
  断言状态条文案、按钮存在且可点、点击后确实发了一次 POST，以及「知识库」分类能显示字段。

## 测试与异步任务

- 新增 `tests/butler/test_knowledge_auto.py`（10 项）：无积压不调模型、写事实后游标前移且使用 `extract` 会话、
  `min_backlog` 门禁、模型失败指数退避且不前移游标、CLI 持锁时调度器跳过、`trigger` 忙时返回 `busy`、
  默认关不启线程、最近有消息时顺延、配置越界报错，以及一条真 HTTP 用例（状态可读、三种非法参数各 400、
  合法触发 202 且后台释放单飞锁、忙时 409）。
- `tests/dashboard/test_knowledge_view.py` 的真 HTTP 用例扩到四条路由：自动提炼 GET 包 `available`、
  POST 去空白后转发、409 透传、Butler 不可达时 GET 仍 200 而 POST 503、远程模式四条全 503。
- 既有 `tests/butler`、`tests/dashboard`、`tests/integration` 全部通过；`npm run build` 与 `npm run smoke` 通过。
- 新增异步任务：`butler-knowledge-extract`（定时轮）与 `butler-knowledge-extract-manual`（手动触发）
  两个 daemon 线程，随 `serve()` 启停；它们不写微信队列、不碰 UI。

## 风险与回滚

- 调度器在 Butler 进程内，**必须重启 Butler 才会启用**；旧进程不认新端点，管理台自动降级为只读状态。
- 模型费用：只在「有积压 + 消息间隙 + 抢到锁」时调用；失败退避上限 6 小时，不会每分钟重试。
- 提炼与回复共用模型后端，`ReloadableBackend.request()` 只做引用计数，后台提炼不阻塞回复；
  但切换模型需要等在飞的提炼调用结束。
- 锁文件残留在 `data/cache/` 时，30 分钟后自动回收，不需要人工删除。
- 回滚：把 `[knowledge] auto_extract` 改回 `false` 重启 Butler 即可停线程；撤掉新端点与前端状态条不影响既有
  CLI 与只读页面。
