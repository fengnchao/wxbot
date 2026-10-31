---
type: table
module: wxbot
summary: 原始收件与群成员证据，batch_id 指向合并批次
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
  line: 234
  anchor: def capture(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
---
# SQLite inbox

## 含义、版本和所属

[[modules/wxbot]] 队列库的收件表；schema VERSION=10。最终列来自初始 DDL 加 initialize 的补列，不能只读 CREATE TABLE。数据写入 [[symbols/queue-store]]，不与 Butler 业务库混用。

## 字段清单（最终结构）

| 字段 | SQLite 类型/约束/默认 |
|---|---|
| id | INTEGER PRIMARY KEY AUTOINCREMENT |
| contact / text / member_key | TEXT NOT NULL |
| member_name | TEXT NOT NULL DEFAULT '' |
| reply_mode | TEXT NOT NULL DEFAULT 'text' |
| context | TEXT NOT NULL |
| group_mode | INTEGER NOT NULL |
| received_at | REAL NOT NULL |
| batch_id | TEXT REFERENCES batches(id)，可 NULL |
| avatar / reply_reason | TEXT NOT NULL DEFAULT ''（升级补列） |

## 索引与关系

inbox_unbatched(contact,batch_id,id)；batch_id 声明引用 [[tables/queue-batches]].id。此处记录 DDL 关系，不据此宣称所有连接开启 SQLite 外键强制校验。

## 字段血缘与消费

MainInbox 收件 → QueueStore.capture：窗口标题进入 contact，正文进入 text，UI 观察进入 member_key/member_name/avatar；prepare 将未合批行分配 batch_id 并生成 batches。group_mode 与成员证据最终影响请求 channel_type / member_key，见 [[apis/butler-handle]]，观察数据不能授予身份权限。

只读消费 [[apis/dashboard-queue]] 的 inbox 行和 [[apis/dashboard-workflow]] 的待合并列表。contact 在三个队列表中重复以保留各阶段目标快照，修改含义必须检查全链路。

## 验证与风险

本地 test_queue_store.py / test_queue_migration.py。不要把无 batch_id 当成数据库损坏；它也可能是正常未合批状态。业务身份见 [[concepts/identity-authority]]。

## 代码依据

- `src/wxbot/queue_schema.py:34` — `_TABLES = (`
- `src/wxbot/queue_schema.py:84` — `def initialize(`
- `src/wxbot/queue_schema.py:149` — `for sql in ('CREATE INDEX`
- `src/wxbot/queue_schema.py:7` — `VERSION = 10`
- `src/wxbot/queue_store.py:234` — `def capture(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
