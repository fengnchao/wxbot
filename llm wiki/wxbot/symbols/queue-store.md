---
type: symbol
module: wxbot
summary: 短事务管理收件、合批、模型状态与 UI 发件状态
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/wxbot/queue_store.py
  line: 91
  anchor: class QueueStore(
- path: src/wxbot/queue_store.py
  line: 234
  anchor: def capture(
- path: src/wxbot/queue_store.py
  line: 272
  anchor: def prepare(
- path: src/wxbot/queue_store.py
  line: 532
  anchor: def claim_delivery(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
---
# QueueStore

## 职责、签名与入口

`QueueStore(path, *, access='runtime', ...)` 继承 StreamQueue / DeliveryPolicy，连接 SQLite，并按访问模式处理生命周期。运行期模式可能持锁和迁移，不能为了看板读取而直接构造运行模式实例。所属 [[modules/wxbot]]。

## 调用关系

MainInbox.capture 写 [[tables/queue-inbox]]；[[symbols/model-worker]] 的 prepare/claim_batch 处理 [[tables/queue-batches]]；[[symbols/queue-finish]] 写 [[tables/queue-outbox]]；UI delivery 使用 claim_delivery、save_baseline、confirming、finish_delivery 保存可核对结果。各方法持短事务，模型/窗口操作不在数据库事务内执行。

## 副作用与反向消费

SQLite 状态、队列事件和辅助流；只读消费使用 [[apis/dashboard-queue]] / [[apis/dashboard-workflow]]，不要让查询触发 QueueStore.recover。失败/过期/人工处置详见 [[concepts/delivery-state]]。

## 测试

本地 tests/unit/queue/test_queue_store.py、test_queue_migration.py、test_delivery_queue.py。

## 代码依据

- `src/wxbot/queue_store.py:91` — `class QueueStore(`
- `src/wxbot/queue_store.py:234` — `def capture(`
- `src/wxbot/queue_store.py:272` — `def prepare(`
- `src/wxbot/queue_store.py:532` — `def claim_delivery(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
