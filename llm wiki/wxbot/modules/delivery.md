---
type: module
module: delivery
summary: 主动推送、补发、媒体与提醒归业务服务所有
coverage: overview
last_verified: '2026-10-31'
sources:
- path: src/butler/delivery/push.py
  line: 19
  anchor: def push_to_wxbot(
- path: src/butler/delivery/reminders.py
  line: 5
  anchor: 'class ReminderScheduler:'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
---
# Butler 投递业务

## 范围与边界

`src/butler/delivery/` 负责主动推送、补发、媒体和提醒。push_to_wxbot 将主动推送交给 wxbot 外发 HTTP 服务；最终 UI 发件由 [[modules/wxbot]] 拥有，Butler 不操作窗口。

## 关系与缺口

属于 [[modules/butler]]；消息处理先认领补发再调用模型，见 [[symbols/butler-handle]]。wxbot 出站持久化见 [[tables/queue-outbox]]。主动推送/媒体端点、提醒业务表和调度字段仍待完整建档；本概览不代表这些接口已完成契约巡检。

## 代码依据

- `src/butler/delivery/push.py:19` — `def push_to_wxbot(`
- `src/butler/delivery/reminders.py:5` — `class ReminderScheduler:`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
