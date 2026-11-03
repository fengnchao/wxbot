---
type: table
module: wxbot
summary: 逐分句发件与不确定结果审计，包含迁移新增字段
coverage: core
last_verified: 2026-11-03
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
- path: src/wxbot/queue_schema.py
  line: 22
  anchor: OUTBOX_SQL =
- path: src/wxbot/queue_store.py
  line: 630
  anchor: def finish_delivery(
- path: src/wxbot/queue_store.py
  line: 21
  anchor: FAILURE_DETAIL_FIELDS =
- path: src/wxbot/delivery.py
  line: 523
  anchor: details.update(confirm_evidence=evidence
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-03-feat-voice-001-virtual-mic
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
---
# SQLite outbox

## 字段清单（VERSION=10 最终结构）

| 字段 | SQLite 类型/约束/默认 |
|---|---|
| seq | INTEGER PRIMARY KEY AUTOINCREMENT |
| id | TEXT NOT NULL UNIQUE |
| contact / text / state | TEXT NOT NULL |
| batch_id | TEXT REFERENCES batches(id)，可 NULL（主动推送） |
| created_at / not_before | REAL NOT NULL |
| baseline | TEXT，可 NULL |
| submitted_at / finished_at / failed_at | REAL，可 NULL |
| error | TEXT NOT NULL DEFAULT '' |
| submitted_text / draft_text | TEXT，可 NULL |
| part_seq | INTEGER NOT NULL DEFAULT 1 |
| resolution | TEXT NOT NULL DEFAULT '' |
| kind | TEXT NOT NULL DEFAULT 'text' |
| retries / detached / manual_required | INTEGER NOT NULL DEFAULT 0 |
| mention_name | TEXT NOT NULL DEFAULT '' |
| package_id | TEXT REFERENCES delivery_packages(id)，可 NULL |
| media_id / media_path | TEXT NOT NULL DEFAULT '' |

## 索引与关系

UNIQUE(batch_id,part_seq)，outbox_state(state,seq)。batch_id 指向 [[tables/queue-batches]]；SQLite 中 NULL 的批次不构成这个唯一键下的去重保障。package_id 关联 delivery_packages（尚未独立建页）；媒体相关字段不能拿模型任意文件路径填充。

## 字段血缘

[[symbols/queue-finish]] 将完整 reply parts 逐项写 text/part_seq，群 mention_name 仅第一条；UI 发件器写 baseline/submitted_text/submitted_at 并核对新增自身气泡后记 state。`baseline` 保存的是去掉快照引用的行（引用只属于一次读取，不跨重启）；发送确认把 `confirm_evidence`（`ref`/`text`）与 `ref_available` 写进该行的 `delivery_events.details`，失败写 `error_code` / `retry`，提及失败且能证明字面残留时另写 `mention_residue`，白名单见 `FAILURE_DETAIL_FIELDS`。实际投递规则见 [[concepts/delivery-state]]。

`draft_text` 只在 UI 读回能证明是机器人输入时写入：已核验的正文前缀，或提及失败后读回的字面 `@...` 前缀。`blocked`/`uncertain` 保留该值，下一次发件前由 `owned_draft(contact)` 取回并清理；只有 `sent` 才清空。

[[apis/dashboard-queue]] 的 outbox、rounds、events 和 [[apis/dashboard-workflow]] 读取状态/时间/分句进度；前端不得从“存在 outbox”推断已发送。所属 [[modules/wxbot]]，执行器 [[symbols/queue-store]]。

## 风险与测试

uncertain/confirming 记录需要保守保留及人工核对，不能任意自动重放；detached 标记与超时/关闭轮次有关。本地 test_delivery_queue.py、test_delivery_failure_policy.py、test_queue_migration.py。

## 代码依据

- `src/wxbot/queue_schema.py:34` — `_TABLES = (`
- `src/wxbot/queue_schema.py:84` — `def initialize(`
- `src/wxbot/queue_schema.py:149` — `for sql in ('CREATE INDEX`
- `src/wxbot/queue_schema.py:7` — `VERSION = 10`
- `src/wxbot/queue_schema.py:22` — `OUTBOX_SQL =`
- `src/wxbot/queue_store.py:591` — `def finish_delivery(`
- `src/wxbot/queue_store.py:21` — `FAILURE_DETAIL_FIELDS =`
- `src/wxbot/delivery.py:389` — `details.update(confirm_evidence=evidence, ref_available=by_ref)`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

[[raw/changes/2026-11-01-mention-fallback-unread-retry]]

[[raw/changes/2026-11-02-ui-snapshot-ref-contract]]

[[raw/changes/2026-11-02-mention-picker-gating-residue]]

## 变更

- 2026-11-03: FEAT-VOICE-001 P1 outbox kind=voice（虚拟麦+RALT）；见 [[raw/changes/2026-11-03-feat-voice-001-virtual-mic]]
