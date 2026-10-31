---
type: api
module: dashboard
summary: 队列与 Telegram 工作流只读聚合及前端消费
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/dashboard/routes.py
  line: 39
  anchor: ("GET", "/api/workflow", workflow.read)
- path: src/dashboard/api/workflow.py
  line: 10
  anchor: 'def read(ctx):'
- path: src/dashboard/workflow_view.py
  line: 52
  anchor: 'def read(self, *, now=None):'
- path: web/src/views/WorkflowView.vue
  line: 356
  anchor: fetch('/api/workflow',
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
---
# GET /api/workflow

## 方法、输入与实现

GET `/api/workflow`，本接口没有业务查询 DTO；走 [[modules/dashboard]] HTTP 的访问控制。routes → api.workflow.read → WorkflowView.read，并合入 TelegramView.workflow，最后脱敏。此端点不初始化或修复数据库。

## 响应摘要

顶层 `status/error`、`sources`、`nodes`、`messages`、`counts`、`backend/model` 以及 active_more/history_more 标识；counts 来自真实队列与 Telegram 聚合，不是合成指标。messages 的具体结构由 WorkflowView._message 和 Telegram 投影决定，两类消息不能视为同一 DTO。读取失败用 status/error 表明，处理器配置异常返回 500。

## 消费与字段血缘

[[modules/web]] 的 `WorkflowView.vue` 刷新函数 fetch 本接口，列表筛选和选中消息使用消息 id/request_id；队列 batch id 来自 [[tables/queue-batches]]，推送项以 `push:` 前缀区分。正文/实时输出分别通过 `/api/workflow-content?id=...`、`/api/workflow-stream?id=...&after=...` 读取，本页未逐字段建档这些端点。

## 表、测试与风险

只读 [[tables/queue-inbox]] / [[tables/queue-batches]] / [[tables/queue-outbox]] 及结构流转事件。相关本地 tests/dashboard/test_workflow_view.py、test_workflow_content.py、tests/unit/model_stream/test_model_stream_view.py 和 web/scripts/smoke.mjs。改状态/聚合时对照 [[concepts/delivery-state]]，不要将模型完成投影为微信发送成功。

## 代码依据

- `src/dashboard/routes.py:39` — `("GET", "/api/workflow", workflow.read)`
- `src/dashboard/api/workflow.py:10` — `def read(ctx):`
- `src/dashboard/workflow_view.py:52` — `def read(self, *, now=None):`
- `web/src/views/WorkflowView.vue:356` — `fetch('/api/workflow',`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
