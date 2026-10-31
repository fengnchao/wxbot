---
type: module
module: dashboard
summary: 聚合运行事实，读取队列不初始化或迁移数据库
coverage: overview
last_verified: '2026-10-31'
sources:
- path: src/dashboard/routes.py
  line: 26
  anchor: ROUTES = (
- path: src/dashboard/queue_view.py
  line: 15
  anchor: 'class QueueView:'
- path: src/dashboard/workflow_view.py
  line: 41
  anchor: 'class WorkflowView:'
- path: src/dashboard/config_view.py
  line: 90
  anchor: 'class ConfigView:'
- path: src/dashboard/config_editor.py
  line: 153
  anchor: def _access_changes(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-model-access-switch
depends_on:
- modules/common
---
# 管理台 HTTP 与投影

## 范围与入口

`src/dashboard/`：server 组装 HTTP 服务，http 负责传输、鉴权/同源和静态文件；routes.ROUTES 是单张路由表；api 只做胶水，view/action 承担投影与明确动作。

## 对外接口及消费方

[[apis/dashboard-workflow]] 被 [[modules/web]] 的 WorkflowView 消费；[[apis/dashboard-queue]] 被 QueueView 消费。数据库是 [[modules/wxbot]] 的队列，视图使用 SQLite `mode=ro`；GET 不允许初始化、迁移或恢复。

## 边界与缺口

写操作需专用动作头、JSON、明确 acknowledge、可信 Host 和同源；队列写操作和联系人写操作不在本批接口词条范围。身份管理归 [[modules/identity]]，不是页面自行授予。配置与业务操作细节仍见 README 和实际处理器。

配置投影的 `model_access` 是页面唯一的接入方式来源：`current` 由 `config_schema.access_provider()` 推导（`[model].provider` 优先，否则按 `[agent].provider` 回退），`fields` 与 `notes` 覆盖全部接入方式。保存时 `config_editor._access_changes()` 把接入方式展开成 `[agent].provider` 和 `[model].backend` 再落盘，Codex 用 `op:default` 删掉多余协议字段，因此三个字段不会各行其是。

## 代码依据

- `src/dashboard/routes.py:26` — `ROUTES = (`
- `src/dashboard/queue_view.py:15` — `class QueueView:`
- `src/dashboard/workflow_view.py:41` — `class WorkflowView:`
- `src/dashboard/config_view.py:90` — `class ConfigView:`
- `src/dashboard/config_editor.py:153` — `def _access_changes(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

[[raw/changes/2026-10-31-model-access-switch]]
