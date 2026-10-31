---
type: api
module: butler
summary: SSE 增量观察与最终 result，断流不能当完整结果
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/butler/server.py
  line: 333
  anchor: streaming=self.path=='/v1/handle-stream'
- path: src/wxbot/processor/butler.py
  line: 89
  anchor: 'if kind==''result'':'
- path: src/wxbot/processor/butler.py
  line: 106
  anchor: if data is None:raise ValueError('Butler stream disconnected before result')
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
---
# POST /v1/handle-stream

## 请求和实现

所属 [[modules/butler]]。鉴权、请求字段、输入校验同 [[apis/butler-handle]]；实现仍进入 [[symbols/butler-handle]]。返回 `text/event-stream; charset=utf-8`，`Cache-Control: no-store`，连接关闭。

## 响应契约

每个 SSE 帧是 `data: <JSON>` 加空行；公开事件按 type 分派。`answer_delta` 的 text 只有 `sendable is true` 时进入可发送前缀。`error` 带 code/message/retry_safe，HTTP 已开始后错误也可能是 200 下的 error 帧。

最终 `type: result` 的 result 字段与 [[symbols/butler-result]] 的 JSON 相同，必须经过 decoder 校验，而且最终 reply 必须以已发出前缀开头。观察到 complete 不能替代最终 result；在 result 前断流为失败。

## 消费与影响

[[symbols/butler-processor]] 在 on_event 存在时选择此路径；[[symbols/model-worker]] 根据模式持久化事件/可发送增量。涉及 [[tables/queue-batches]] / [[tables/queue-outbox]] 和 [[concepts/delivery-state]]；浏览器另读管理台的 workflow-stream，不直接连接这个 Butler SSE。

## 测试与风险

本地 tests/unit/model_stream/test_model_stream_transport.py / test_model_stream_pipeline.py。修改最终事件、错误或前缀校验时，必须验证断流、重复/不完整结果及禁止未知结果重放。

## 代码依据

- `src/butler/server.py:333` — `streaming=self.path=='/v1/handle-stream'`
- `src/wxbot/processor/butler.py:89` — `if kind=='result':`
- `src/wxbot/processor/butler.py:106` — `if data is None:raise ValueError('Butler stream disconnected before result')`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

## 模型配置错误

在模型提交前的配置错误使用 code=model_configuration、retry_safe=True；wxbot 仅在尚无 backend/tool/answer_delta/summary_delta/complete 事件时保留安全重试标记。已提交或部分输出错误仍禁止自动重放。模型切换见 [[modules/models]]。


[[raw/changes/2026-10-31-switchable-models]]
