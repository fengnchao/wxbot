---
type: symbol
module: wxbot
summary: 短事务管理收件、合批、模型状态与 UI 发件状态
coverage: core
last_verified: '2026-11-02'
sources:
- path: src/wxbot/queue_store.py
  line: 91
  anchor: class QueueStore(
- path: src/wxbot/queue_store.py
  line: 239
  anchor: def capture(
- path: src/wxbot/queue_store.py
  line: 277
  anchor: def prepare(
- path: src/wxbot/queue_store.py
  line: 537
  anchor: def claim_delivery(
- path: src/wxbot/queue_store.py
  line: 21
  anchor: FAILURE_DETAIL_FIELDS =
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
---
# QueueStore

## 职责、签名与入口

`QueueStore(path, *, access='runtime', ...)` 继承 StreamQueue / DeliveryPolicy，连接 SQLite，并按访问模式处理生命周期。运行期模式可能持锁和迁移，不能为了看板读取而直接构造运行模式实例。所属 [[modules/wxbot]]。

## 调用关系

MainInbox.capture 写 [[tables/queue-inbox]]；[[symbols/model-worker]] 的 prepare/claim_batch 处理 [[tables/queue-batches]]；[[symbols/queue-finish]] 写 [[tables/queue-outbox]]；UI delivery 使用 claim_delivery、save_baseline、confirming、finish_delivery 保存可核对结果。各方法持短事务，模型/窗口操作不在数据库事务内执行。

`forget_session` 是 `pending_sessions` 除 capture 之外唯一的删除路径，专供「未读始终读不到可采内容」的放弃场景，否则该联系人的 prepare 永远被跳过；重试与放弃规则见 [[concepts/unread-capture-retry]]。

`FAILURE_DETAIL_FIELDS` 是 `delivery_events.details` 的白名单：只接受标量键，字符串截断 256 字符。发件失败写 `error_code` / `retry`，发送确认写 `confirm_evidence` / `ref_available`，提及失败留下可认领字面草稿时写 `mention_residue`；管理台只读投影复用同一份常量。`save_baseline` 保存的是去掉快照引用的行（`ui_contract.persisted_rows`），所以引用不跨重启。见 [[concepts/delivery-state]]。

## 副作用与反向消费

SQLite 状态、队列事件和辅助流；只读消费使用 [[apis/dashboard-queue]] / [[apis/dashboard-workflow]]，不要让查询触发 QueueStore.recover。失败/过期/人工处置详见 [[concepts/delivery-state]]。

## 测试

本地 tests/unit/queue/test_queue_store.py、test_queue_migration.py、test_delivery_queue.py。

## 代码依据

- `src/wxbot/queue_store.py:91` — `class QueueStore(`
- `src/wxbot/queue_store.py:239` — `def capture(`
- `src/wxbot/queue_store.py:277` — `def prepare(`
- `src/wxbot/queue_store.py:537` — `def claim_delivery(`
- `src/wxbot/queue_store.py:21` — `FAILURE_DETAIL_FIELDS =`
- `src/wxbot/queue_store.py:229` — `def forget_session(self, contact):`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

[[raw/changes/2026-10-31-group-identity-nickname]]

[[raw/changes/2026-11-01-mention-fallback-unread-retry]]

[[raw/changes/2026-11-02-ui-snapshot-ref-contract]]

[[raw/changes/2026-11-02-mention-picker-gating-residue]]
