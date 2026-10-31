---
type: table
module: wxbot
summary: 模型请求批次与最终回复完整性，非发送回执
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/wxbot/queue_schema.py
  line: 34
  anchor: _TABLES = (
- path: src/wxbot/queue_schema.py
  line: 84
  anchor: def initialize(
- path: src/wxbot/queue_schema.py
  line: 149
  anchor: for sql in ('CREATE INDEX
- path: src/wxbot/queue_schema.py
  line: 7
  anchor: VERSION = 10
- path: src/wxbot/queue_store.py
  line: 304
  anchor: def claim_batch(
- path: src/wxbot/queue_store.py
  line: 334
  anchor: def finish_batch_parts(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-queue-batches-format
- raw/changes/2026-10-31-group-identity-nickname
---
# SQLite batches

## 字段清单（VERSION=10 最终结构）

| 字段                          | SQLite 类型/约束/默认                   |
| --------------------------- | --------------------------------- |
| seq                         | INTEGER PRIMARY KEY AUTOINCREMENT |
| id                          | TEXT NOT NULL UNIQUE              |
| contact / text / context    | TEXT NOT NULL                     |
| member_key / member_name    | TEXT NOT NULL DEFAULT ''          |
| reply_mode                  | TEXT NOT NULL DEFAULT 'text'      |
| state                       | TEXT NOT NULL                     |
| created_at                  | REAL NOT NULL                     |
| started_at / finished_at    | REAL，可 NULL                       |
| attempts                    | INTEGER NOT NULL DEFAULT 0        |
| error                       | TEXT NOT NULL DEFAULT ''          |
| reply_text                  | TEXT，可 NULL                       |
| reply_complete / part_count | INTEGER NOT NULL DEFAULT 0        |
| avatar / reply_reason       | TEXT NOT NULL DEFAULT ''（补列）      |
| first_delivery_failure      | REAL，可 NULL（补列）                   |
| delivery_resolution         | TEXT NOT NULL DEFAULT ''（补列）      |
|                             |                                   |

## 关系与索引

所属 [[modules/wxbot]]；batches_state(state,seq)。[[tables/queue-inbox]].batch_id 与 [[tables/queue-outbox]].batch_id 引用 id，inbox 一批多条，outbox 一批多分句。所有读写核心见 [[symbols/queue-store]]。

## 血缘

prepare 合并 inbox 得 text/context/member/回复模式；claim_batch 标记 processing。[[symbols/model-worker]] 把 id 作为 request_id，[[symbols/butler-processor]] 映射 msg_id，Butler 回 meta.msg_id；[[apis/dashboard-workflow]] 将其作为 request_id 关联 trace。

[[symbols/queue-finish]] 保存 reply_text / reply_complete=1 / part_count，并插入 outbox；只有聚合投递状态可表示整轮结束。字段 reply_complete 属模型完整性，不能替代 outbox sent。展示也见 [[apis/dashboard-queue]]。

## 风险与测试

失败模型请求仅 retry_safe 为真才重试；未知结果不重放，超时放行后续消息。first_delivery_failure 以整轮首次失败计算时限，见 [[concepts/delivery-state]]。本地 test_queue_worker.py、test_model_recovery.py、test_reply_delivery_lifecycle.py。

## 代码依据

- `src/wxbot/queue_schema.py:34` — `_TABLES = (`
- `src/wxbot/queue_schema.py:84` — `def initialize(`
- `src/wxbot/queue_schema.py:149` — `for sql in ('CREATE INDEX`
- `src/wxbot/queue_schema.py:7` — `VERSION = 10`
- `src/wxbot/queue_store.py:304` — `def claim_batch(`
- `src/wxbot/queue_store.py:334` — `def finish_batch_parts(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

[[raw/changes/2026-10-31-queue-batches-format]]
