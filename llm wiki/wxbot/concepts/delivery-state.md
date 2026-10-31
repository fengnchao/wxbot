---
type: concept
module: wxbot
summary: 完整回复、排队、已发送和结果不确定分别处理
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/wxbot/queue_store.py
  line: 334
  anchor: def finish_batch_parts(
- path: src/wxbot/queue_store.py
  line: 586
  anchor: def finish_delivery(
- path: src/wxbot/queue_store.py
  line: 627
  anchor: def retry_failed_deliveries(
- path: src/wxbot/delivery_policy.py
  line: 5
  anchor: def _end_reply(
- path: src/wxbot/queue_worker.py
  line: 174
  anchor: safe=getattr(exc,'retry_safe',False) is True
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
---
# 模型完成与投递状态

## 状态含义

[[tables/queue-batches]].reply_complete 标记模型完整结果；[[tables/queue-outbox]] 的 pending/sending/confirming/sent/blocked/uncertain/skipped 是分句投递阶段。具体允许转换以 QueueStore 实现为准，本页不将状态名当通用可任意流转的枚举。

[[symbols/queue-finish]] 只能保存 processing 批次，写完整分句后重算整轮，不会立即宣称微信已发。UI 输入/提交后仍需要观察确认，见 [[modules/wxbot]] 和 [[symbols/queue-store]]。

## 重试、时限与人工核对

模型失败时 retry_safe 默认 False；已提交结果未知不能自动重放。投递重试和整轮失败时限是另一套规则：首次失败起计时，过期可结束剩余未发送块并推进后续轮次；_end_reply 对 uncertain/confirming 保留 uncertain + detached/review，不能抹掉不确定证据。

[[apis/dashboard-queue]] 展示剩余时限/动作，[[apis/dashboard-workflow]] 展示当前阶段；它们不能恢复队列。超时默认值从配置及实现读，不在图谱额外写死第二份。

## 测试与风险

本地 test_delivery_failure_policy.py / test_reply_delivery_lifecycle.py / test_model_recovery.py。改时限需同步队列维护、只读倒计时和用户配置，不能只改界面。

## 代码依据

- `src/wxbot/queue_store.py:334` — `def finish_batch_parts(`
- `src/wxbot/queue_store.py:586` — `def finish_delivery(`
- `src/wxbot/queue_store.py:627` — `def retry_failed_deliveries(`
- `src/wxbot/delivery_policy.py:5` — `def _end_reply(`
- `src/wxbot/queue_worker.py:174` — `safe=getattr(exc,'retry_safe',False) is True`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
