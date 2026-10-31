---
type: symbol
module: wxbot
summary: 领取批次、调用模型并保存回复，绝不访问 UI
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/wxbot/queue_worker.py
  line: 43
  anchor: def process_once(
- path: src/wxbot/queue_worker.py
  line: 141
  anchor: reply = self.router.handle_reply(
- path: src/wxbot/queue_worker.py
  line: 99
  anchor: self.store.finish_batch_parts(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
calls:
- symbols/butler-processor
- symbols/queue-finish
called_by: []
---
# ModelWorker.process_once

## 签名与调用方

`ModelWorker.process_once(self)` 返回是否处理一个批次；由 worker._run 循环调用。所属 [[modules/wxbot]]。依赖 [[symbols/queue-store]]。

## 调用与输出

prepare/claim_batch → Router → [[symbols/butler-processor]]（使用 Butler 模型时）→ [[symbols/queue-finish]]。根据回复模式选择表情、静默或文本；事件模式可以持久化增量，只有 sendable 文本进入流式队列。

## 副作用与风险

读写 [[tables/queue-batches]]、[[tables/queue-outbox]] 及辅助流记录，网络发生在适配器；无 UI 操作。完整回复必须与已流出前缀一致。异常交 fail_batch，retry_safe 默认 False，未知结果不自动重放。定时维护恢复安全失败/过期投递，细节见 [[concepts/delivery-state]]。

## 测试

本地 tests/unit/queue/test_queue_worker.py、test_queue_concurrency.py、tests/unit/model_stream/test_model_stream_pipeline.py。

## 代码依据

- `src/wxbot/queue_worker.py:43` — `def process_once(`
- `src/wxbot/queue_worker.py:141` — `reply = self.router.handle_reply(`
- `src/wxbot/queue_worker.py:99` — `self.store.finish_batch_parts(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
