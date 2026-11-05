---
type: symbol
module: butler
summary: 生成 reply/actions/reply_parts/meta 的公开边界
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/agent/core.py
  line: 68
  anchor: 'class Result:'
- path: src/butler/agent/core.py
  line: 73
  anchor: def as_dict(
- path: src/butler/server.py
  line: 412
  anchor: result=res.as_dict(reply_chunk_chars=cfg.reply_chunk_chars)
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch-core-emit
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
calls: []
called_by:
- symbols/butler-handle
---
# Result.as_dict

## 签名、职责与关系

`Result(reply: str | None, actions: list, meta: dict)`；`as_dict(*, reply_chunk_chars=500) -> dict`。结构由 [[symbols/butler-handle]] 返回，再由 HTTP handler 序列化为 [[apis/butler-handle]] 的响应/[[apis/butler-handle-stream]] 的最终 result。这里 calls 元信息的 handle → result 表示返回对象构造关系，不表示 handle 直接调用 as_dict。

## 字段与副作用

reply 原样；actions 调各项 as_dict；reply_parts 经 split_reply 切分；meta 使用默认 reply_complete=True 再被业务 meta 覆盖，因此可能显式 False。此方法本身无数据库或网络副作用。L1 原文沉淀由 [[symbols/butler-handle]] 旁路写入 [[tables/kb-episodes]]，不经过 Result，所以本 DTO 字段与语义不受影响。

## 消费与风险

消费者 [[symbols/butler-processor]] 会拒绝不完整结果、非法 reply/meta、请求 ID 不一致。改 DTO 要同时检查 wxbot Reply 的分句约束和 [[symbols/model-worker]]，不能仅看 HTTP 200。

2026-10-31 的接入方式改动只动了 core.py 里 `emit('backend')` 的模型来源上报（改用 `Config.model_identity`），Reply/actions/reply_parts/meta 的字段与语义未变。

同日的拆库（knowledge-sharding）同样不经过本 DTO：它只改了 [[tables/kb-episodes]] 的落盘位置与目录结构，`Result` 的字段与 `as_dict` 的序列化未变。

## 代码依据

- `src/butler/agent/core.py:68` — `class Result:`
- `src/butler/agent/core.py:73` — `def as_dict(`
- `src/butler/server.py:412` — `result=res.as_dict(reply_chunk_chars=cfg.reply_chunk_chars)`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch-core-emit]]

[[raw/changes/2026-11-01-knowledge-episodes]]

[[raw/changes/2026-11-01-knowledge-sharding]]

[[raw/changes/2026-11-01-knowledge-auto]]


## 本次核对

[[raw/changes/2026-11-04-index-tts-skill]]：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [[apis/index-tts]]，其余已述契约未改。

## 本次核对

补建窗口属于入站业务库副作用，公开 Result 字段沿用。 来源 [[raw/changes/2026-11-05-contact-enrollment-and-tts-ui]]。
