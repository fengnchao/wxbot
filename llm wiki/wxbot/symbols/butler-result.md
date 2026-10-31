---
type: symbol
module: butler
summary: 生成 reply/actions/reply_parts/meta 的公开边界
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/butler/agent/core.py
  line: 64
  anchor: 'class Result:'
- path: src/butler/agent/core.py
  line: 69
  anchor: def as_dict(
- path: src/butler/server.py
  line: 361
  anchor: result=res.as_dict(reply_chunk_chars=cfg.reply_chunk_chars)
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch-core-emit
calls: []
called_by:
- symbols/butler-handle
---
# Result.as_dict

## 签名、职责与关系

`Result(reply: str | None, actions: list, meta: dict)`；`as_dict(*, reply_chunk_chars=500) -> dict`。结构由 [[symbols/butler-handle]] 返回，再由 HTTP handler 序列化为 [[apis/butler-handle]] 的响应/[[apis/butler-handle-stream]] 的最终 result。这里 calls 元信息的 handle → result 表示返回对象构造关系，不表示 handle 直接调用 as_dict。

## 字段与副作用

reply 原样；actions 调各项 as_dict；reply_parts 经 split_reply 切分；meta 使用默认 reply_complete=True 再被业务 meta 覆盖，因此可能显式 False。此方法本身无数据库或网络副作用。

## 消费与风险

消费者 [[symbols/butler-processor]] 会拒绝不完整结果、非法 reply/meta、请求 ID 不一致。改 DTO 要同时检查 wxbot Reply 的分句约束和 [[symbols/model-worker]]，不能仅看 HTTP 200。

2026-10-31 的接入方式改动只动了 core.py 里 `emit('backend')` 的模型来源上报（改用 `Config.model_identity`），Reply/actions/reply_parts/meta 的字段与语义未变。

## 代码依据

- `src/butler/agent/core.py:64` — `class Result:`
- `src/butler/agent/core.py:69` — `def as_dict(`
- `src/butler/server.py:361` — `result=res.as_dict(reply_chunk_chars=cfg.reply_chunk_chars)`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch-core-emit]]
