---
type: module
module: web
summary: 共享导航壳和现有请求封装的管理界面
coverage: overview
last_verified: '2026-10-31'
sources:
- path: web/src/router.js
  line: 4
  anchor: 'export '
- path: web/src/api.js
  line: 19
  anchor: 'export '
- path: web/src/views/WorkflowView.vue
  line: 356
  anchor: fetch('/api/workflow',
- path: web/src/views/QueueView.vue
  line: 248
  anchor: apiGet('/api/queue?'
- path: web/src/views/ConfigurationView.vue
  line: 37
  anchor: const backendName =
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch
depends_on:
- modules/dashboard
---
# Vue 管理台

## 范围与依赖

`web/` 是 Vue 3/Vite 管理台；源码 `web/src/`，构建目录 `web/dist/` 由管理台提供 `/app/`。入口/页面注册步骤在根 README。导航由 router.js 和 App.vue 共同登记；请求封装见 api.js。

## API 消费映射

- WorkflowView.vue 的刷新请求消费 [[apis/dashboard-workflow]]，全文和实时事件分别读 workflow-content / workflow-stream；不是直接调用 Butler handle API。
- QueueView.vue 消费 [[apis/dashboard-queue]]；重试/确认已发/丢弃是另外的显式动作，不能把只读投影当成发送成功证据。

## 维护约束

UI 修改按根 AGENTS 的 Hallmark 流程，保留现有设计系统；构建和 smoke 后一起交付 dist。配置管理页现在按模型草稿显示适用字段，保存反馈区分模型热生效和需要重启的字段。见 [[modules/models]]；其它页面字段契约仍待建档。

配置页的「模型后端」分类只有一个接入方式下拉（`[model].provider`）。选项中文名与说明来自接口的 `model_access`，页面不维护第二份映射表：`model_access.fields` 决定哪些连接字段显示，`model_access.notes` 显示当前接入方式的说明。`butler.agent.provider` 已移入「高级配置」，避免同一件事出现两个下拉；`model.provider` 行不受兼容降级影响，否则选过 Codex 就无法切回。

## 代码依据

- `web/src/router.js:4` — `export `
- `web/src/api.js:19` — `export `
- `web/src/views/WorkflowView.vue:356` — `fetch('/api/workflow',`
- `web/src/views/QueueView.vue:248` — `apiGet('/api/queue?'`
- `web/src/views/ConfigurationView.vue:37` — `const backendName =`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch]]
