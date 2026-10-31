---
type: api
module: dashboard
summary: 队列分页诊断，展示状态和可用动作而不执行恢复
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/dashboard/routes.py
  line: 42
  anchor: ("GET", "/api/queue", queue.read)
- path: src/dashboard/api/queue.py
  line: 10
  anchor: 'def read(ctx):'
- path: src/dashboard/queue_view.py
  line: 22
  anchor: def read(self, *, contact=
- path: src/dashboard/queue_view.py
  line: 170
  anchor: def _row(
- path: web/src/views/QueueView.vue
  line: 248
  anchor: apiGet('/api/queue?'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
---
# GET /api/queue

## 请求

GET `/api/queue`；可选 contact（字符串过滤）、state（默认 all）、scope、order；limit 默认 50，视图截在 1..200；offset 默认 0 且非负；inbox_offset/batches_offset/outbox_offset/rounds_offset 单独分页，telegram_offset 默认 0。路由 → api.queue.read → QueueView.read；HTTP 访问控制属于 [[modules/dashboard]]。

## 响应

`read_only: true`、database、at、status/error、contacts、counts、pages、inbox/batches/outbox、events、actions_enabled、failure_timeout_seconds；成功读取还含 rounds；处理器添加 telegram。pages 各表 total/offset/limit/has_more。missing/error 状态可能缺少正常读取的扩展字段，前端须容忍。

`_row` 投影状态、part_count/sent_parts/completed_parts、时限和允许动作。actions_enabled 仅在 schema 最新时开启，GET 本身不执行动作；写动作走独立 API 及确认头。

## 消费与表

[[modules/web]] 的 QueueView.vue 使用 apiGet 消费；无 TypeScript DTO，实际字段消费者就在 Vue 和共用 JS 中。对应 [[tables/queue-inbox]]、[[tables/queue-batches]]、[[tables/queue-outbox]]，batch_id 保持反向关联。展示与 [[apis/dashboard-workflow]] 是不同投影。

## 测试与风险

本地 tests/dashboard/test_queue_actions.py、test_queue_cleanup_actions.py、test_flow_view.py 和 web/scripts/smoke.mjs。表变更需兼容旧库只读展示；不得为了 GET 成功而创建/迁移队列。生命周期见 [[concepts/delivery-state]]。

## 代码依据

- `src/dashboard/routes.py:42` — `("GET", "/api/queue", queue.read)`
- `src/dashboard/api/queue.py:10` — `def read(ctx):`
- `src/dashboard/queue_view.py:22` — `def read(self, *, contact=`
- `src/dashboard/queue_view.py:170` — `def _row(`
- `web/src/views/QueueView.vue:248` — `apiGet('/api/queue?'`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
