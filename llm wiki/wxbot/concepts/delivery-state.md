---
type: concept
module: wxbot
summary: 完整回复、排队、已发送和结果不确定分别处理
coverage: core
last_verified: 2026-11-03
sources:
- path: src/wxbot/queue_store.py
  line: 339
  anchor: def finish_batch_parts(
- path: src/wxbot/queue_store.py
  line: 630
  anchor: def finish_delivery(
- path: src/wxbot/queue_store.py
  line: 671
  anchor: def retry_failed_deliveries(
- path: src/wxbot/delivery_policy.py
  line: 5
  anchor: def _end_reply(
- path: src/wxbot/queue_worker.py
  line: 183
  anchor: safe=getattr(exc,'retry_safe',False) is True
- path: src/wxbot/ui_contract.py
  line: 65
  anchor: 'class Snapshot:'
- path: src/wxbot/delivery.py
  line: 12
  anchor: def reply_evidence(
- path: src/wxbot/queue_store.py
  line: 21
  anchor: FAILURE_DETAIL_FIELDS =
changes:
- raw/changes/2026-11-03-feat-voice-001-virtual-mic
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-model-error-contract
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
---
# 模型完成与投递状态

## 状态含义

[[tables/queue-batches]].reply_complete 标记模型完整结果；[[tables/queue-outbox]] 的 pending/sending/confirming/sent/blocked/uncertain/skipped 是分句投递阶段。具体允许转换以 QueueStore 实现为准，本页不将状态名当通用可任意流转的枚举。

[[symbols/queue-finish]] 只能保存 processing 批次，写完整分句后重算整轮，不会立即宣称微信已发。UI 输入/提交后仍需要观察确认，见 [[modules/wxbot]] 和 [[symbols/queue-store]]。

## 重试、时限与人工核对

模型失败时 retry_safe 默认 False；已提交结果未知不能自动重放。这套判定与重试上限的完整契约见 [[concepts/model-error-contract]]。投递重试和整轮失败时限是另一套规则：首次失败起计时，过期可结束剩余未发送块并推进后续轮次；_end_reply 对 uncertain/confirming 保留 uncertain + detached/review，不能抹掉不确定证据。

[[apis/dashboard-queue]] 展示剩余时限/动作，[[apis/dashboard-workflow]] 展示当前阶段；它们不能恢复队列。超时默认值从配置及实现读，不在图谱额外写死第二份。

## 发送确认证据与失败码

UI 发件器不因「界面里出现了这段文字」就认定已发送。一次读取产生一个内存快照，每行带只属于本次读取的引用；确认只认 `outbox.baseline` 里不存在、方向为自己、正文一致的行，同一句话别人刚说过或上一轮自己说过都不算新证据。引用缺失、行数为空或被行控件复用（引用不唯一）时整批降级为正文对齐，并把 `confirm_evidence`（`ref`/`text`）与 `ref_available` 写进 `delivery_events.details`。引用不落库：`outbox.baseline` 与 `observations.snapshot` 只保存去掉引用的行，所以重启后自然走正文对齐，不存在旧引用被当成新行的路径。

失败细节另带稳定 `error_code` 与重试语义 `retry`：`after_snapshot` 表示必须重新读界面再试，`never` 表示重放会重复副作用或必然再失败。它们只作诊断，不改 `manual_required`，也不进入 `retry_failed_deliveries` 的筛选 SQL，自动重试次数与时限仍按上一节。失败码表与判定在 `src/wxbot/ui_contract.py`，发件侧入口是 `delivery.reply_evidence`。

## 草稿所有权与提及残留

`outbox.draft_text` 只记录 UI 读回能证明是机器人输入的内容：已核验的正文前缀，或提及失败后读回的字面 `@...` 前缀（对应的 `delivery_events.details` 带 `mention_residue=true`）。`blocked`/`uncertain` 保留该列，`sent` 才清空；下一次投递先 `owned_draft(contact)` 取回，再由 `clear_owned_draft` 在目标窗口清掉。清理只接受与登记值完全相同（可忽略尾随分隔空白）的草稿，用户改写的输入仍 `draft_conflict`，不会误删。无法证明归属的 `\ufffc` 提及对象不登记，继续走人工核对。

## 测试与风险

本地 test_delivery_failure_policy.py / test_reply_delivery_lifecycle.py / test_model_recovery.py，以及快照确认的 test_ui_contract.py。改时限需同步队列维护、只读倒计时和用户配置，不能只改界面；改确认证据要同时看 baseline 的落库形态与 `ref_available` 降级。

## 代码依据

- `src/wxbot/queue_store.py:339` — `def finish_batch_parts(`
- `src/wxbot/queue_store.py:591` — `def finish_delivery(`
- `src/wxbot/queue_store.py:632` — `def retry_failed_deliveries(`
- `src/wxbot/delivery_policy.py:5` — `def _end_reply(`
- `src/wxbot/queue_worker.py:174` — `safe=getattr(exc,'retry_safe',False) is True`
- `src/wxbot/ui_contract.py:65` — `class Snapshot:`
- `src/wxbot/delivery.py:12` — `def reply_evidence(`
- `src/wxbot/queue_store.py:21` — `FAILURE_DETAIL_FIELDS =`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

[[raw/changes/2026-11-01-mention-fallback-unread-retry]]

[[raw/changes/2026-11-02-ui-snapshot-ref-contract]]

[[raw/changes/2026-11-02-mention-picker-gating-residue]]

## 变更

- 2026-11-03: FEAT-VOICE-001 P1 outbox kind=voice（虚拟麦+RALT）；见 [[raw/changes/2026-11-03-feat-voice-001-virtual-mic]]
