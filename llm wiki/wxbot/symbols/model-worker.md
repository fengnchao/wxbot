---
type: symbol
module: wxbot
summary: 领取批次、调用模型并保存回复，绝不访问 UI
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/wxbot/queue_worker.py
  line: 46
  anchor: def process_once(
- path: src/wxbot/queue_worker.py
  line: 152
  anchor: reply = self.router.handle_reply(
- path: src/wxbot/queue_worker.py
  line: 102
  anchor: self.store.finish_batch_parts(
- path: src/wxbot/queue_worker.py
  line: 120
  anchor: voice_media = resolve_queued_media_path(policy)
changes:
- raw/changes/2026-11-03-indextts-enqueue-media
- raw/changes/2026-11-03-feat-voice-003-model-worker-drift
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-03-feat-voice-001-anchor-refresh
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-11-05-group-auto-voice
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

非流式完整回复在联系人投递模式不是 off 时入语音条。`outbox.media_path` 只在 `tts_provider=fixture` 时写 `fixture_wav`；`indextts` 等投递时合成的提供者留空，以便发件调用 `prepare`。无可用音色绑定则模式视为 off，只入文字。见 [[concepts/voice-asset-binding]]、[[raw/changes/2026-11-03-indextts-enqueue-media]]。

## 副作用与风险

读写 [[tables/queue-batches]]、[[tables/queue-outbox]] 及辅助流记录，网络发生在适配器；无 UI 操作。完整回复必须与已流出前缀一致。异常交 fail_batch，retry_safe 默认 False，未知结果不自动重放。定时维护恢复安全失败/过期投递，细节见 [[concepts/delivery-state]]。

## 测试

本地 tests/unit/queue/test_queue_worker.py、test_queue_concurrency.py、tests/unit/model_stream/test_model_stream_pipeline.py。

## 代码依据

- `src/wxbot/queue_worker.py:46` — `def process_once(`
- `src/wxbot/queue_worker.py:152` — `reply = self.router.handle_reply(`
- `src/wxbot/queue_worker.py:102` — `self.store.finish_batch_parts(`
- `src/wxbot/queue_worker.py:120` — `voice_media = resolve_queued_media_path(policy)`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


## 群聊采集与自动语音复核（2026-11-05）

自动回复的 webui 默认推导、实时语音策略、流式缓冲、daemon 合成及录音前准确预设复核见 [[concepts/automatic-voice-reply]]；旧媒体包/离线提供者合同保留。自动 webui 的录音前失败终结并仅回退一次文字，不让 blocked 重试重复投递，无数据库迁移。来源 [[raw/changes/2026-11-05-group-auto-voice]]。
