---
type: symbol
module: wxbot
summary: 完整分句入 outbox，模型完成和发送完成分开
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/wxbot/queue_store.py
  line: 334
  anchor: def finish_batch_parts(
- path: src/wxbot/queue_store.py
  line: 316
  anchor: def _insert_delivery(
- path: src/wxbot/queue_store.py
  line: 354
  anchor: def _recompute_batch(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
calls: []
called_by:
- symbols/model-worker
---
# QueueStore.finish_batch_parts

## 签名与关系

`finish_batch_parts(batch_id, parts, *, now, delay=0, reply_text=None, mention_name='')`；由 [[symbols/model-worker]] 和 QueueStore.finish_batch 调用，属于 [[symbols/queue-store]] / [[modules/wxbot]]。

## 输入及副作用

parts 必须是完整、非空字符串的 tuple（允许空 tuple 表示无需文本）；仅接受 processing 批次，拒绝重复保存模型结果。事务内逐句写 [[tables/queue-outbox]]，更新 [[tables/queue-batches]] 的 reply_text/reply_complete/part_count，再重算聚合状态。

群 @ 目标使用服务解析后的 mention_name，且仅第一分句携带；不使用观察昵称或模型文本来选收件人。入库完成不等于微信已发送，见 [[concepts/delivery-state]]。

## 测试

本地 tests/unit/queue/test_multipart_flow.py、test_queue_store.py、tests/butler/test_reply_delivery_lifecycle.py。

## 代码依据

- `src/wxbot/queue_store.py:334` — `def finish_batch_parts(`
- `src/wxbot/queue_store.py:316` — `def _insert_delivery(`
- `src/wxbot/queue_store.py:354` — `def _recompute_batch(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
