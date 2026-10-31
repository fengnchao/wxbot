---
type: api
module: butler
summary: 同步消息处理契约，从 wxbot 批次到完整 Butler 回复
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/butler/server.py
  line: 312
  anchor: 'if self.path in ("/v1/handle","/v1/handle-stream"):'
- path: src/butler/server.py
  line: 64
  anchor: def _authed(
- path: src/butler/agent/core.py
  line: 69
  anchor: def as_dict(
- path: src/wxbot/processor/butler.py
  line: 60
  anchor: def handle_reply(
- path: src/wxbot/processor/butler.py
  line: 129
  anchor: def _decode_reply(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch-core-emit
---
# POST /v1/handle

## 方法、鉴权与实现

POST `/v1/handle`；Bearer token 经 Handler._authed 校验，无服务 token 返回 500，错误凭据 401。实现由 server.make_handler → [[symbols/butler-handle]] → [[symbols/butler-result]]。所属 [[modules/butler]]。

## 请求字段

| 字段 | 类型/默认 | 必填及校验 |
|---|---|---|
| contact | 归一化字符串 | 必须非空；微信窗口标题 |
| text | 转字符串，默认空串 | 无非空校验；不能擅自改成必填非空 |
| msg_id | 可选，服务原样传入 | wxbot 用批次 ID，回写 meta.msg_id |
| channel_type | 字符串，默认 dm，转小写 | 仅 dm/group |
| member_key / member_name | 字符串，默认空 | 群身份观察/显示；不授予权限 |
| avatar | 字符串，默认空 | 长度不超过 750000 |
| group_context_seq | 整数，默认 0 | 要求 type 为 int 且非负，bool 不被接受 |

请求顶层必须为 JSON 对象；无 contact、非法 channel/avatar/boundary 返回 400。

## 响应字段

| 字段 | 类型/含义 |
|---|---|
| reply | string/null；最终合成文本，可静默 |
| reply_parts | string[]；按 reply_chunk_chars 切分 |
| actions | list；行动 as_dict 序列化结果 |
| meta | object；含 reply_complete，分支可有 msg_id/error/retry_safe/身份等 |

成功 HTTP 200 不等于业务完成：`meta.reply_complete == false` 被 wxbot 拒绝；msg_id 若存在须匹配请求。异常非流式返回 500。其它 meta 字段由业务分支决定，不能将所有字段标为必返。

## 消费、表与血缘

直接调用方 [[symbols/butler-processor]]；它的 request_id → 请求 msg_id → Butler trace / meta.msg_id；源头是 [[tables/queue-batches]] 的 id。群边界来自归档返回的序号。完成回复经过 [[symbols/model-worker]] → [[symbols/queue-finish]] → [[tables/queue-outbox]]。

浏览器不直接消费此端点；展示经 [[apis/dashboard-workflow]] / [[apis/dashboard-queue]]。Butler 业务库由身份/工具等分支触及，详细表待建档，不应误记为直接写 wxbot 队列表。

## 测试与风险

本地 tests/butler/test_transport.py、test_pipeline.py；tests/unit/model_stream/test_model_stream_transport.py。改字段同时查适配器 decoder、Result.as_dict、队列 worker；流式变体见 [[apis/butler-handle-stream]]，权限见 [[concepts/identity-authority]]。

2026-10-31 的接入方式改动只影响 `emit('backend')` 的模型来源上报，请求/响应字段与校验未变。

## 代码依据

- `src/butler/server.py:312` — `if self.path in ("/v1/handle","/v1/handle-stream"):`
- `src/butler/server.py:64` — `def _authed(`
- `src/butler/agent/core.py:69` — `def as_dict(`
- `src/wxbot/processor/butler.py:60` — `def handle_reply(`
- `src/wxbot/processor/butler.py:129` — `def _decode_reply(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch-core-emit]]
