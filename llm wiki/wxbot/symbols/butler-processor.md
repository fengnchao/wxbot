---
type: symbol
module: wxbot
summary: wxbot 的 Butler HTTP 适配及完整结果校验
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/wxbot/processor/butler.py
  line: 60
  anchor: def handle_reply(
- path: src/wxbot/processor/butler.py
  line: 129
  anchor: def _decode_reply(
- path: src/wxbot/processor/router.py
  line: 27
  anchor: def handle_reply(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
calls: []
called_by:
- symbols/model-worker
---
# ButlerProcessor.handle_reply

## 签名与职责

`handle_reply(contact, text, *, request_id=None, member_key='', member_name='', avatar='', group_context_seq=None, channel_type='dm', on_event=None) -> Reply`。所属 [[modules/wxbot]]。

## 调用链

[[symbols/model-worker]] → processor.router.Router.handle_reply → 本方法 → [[apis/butler-handle]] 或 [[apis/butler-handle-stream]]。`request_id` 映射 JSON msg_id；member_key 会使 channel_type 变为 group；on_event 存在时选择 SSE。

## 校验和副作用

HTTP 网络请求、公开流事件与 trace；decoder 校验 dict/meta、reply_complete、msg_id、mention_name、reply 及分句。流式断连或前缀不符抛错，未知提交结果不能重放；非流式是否抛出取决于 raise_errors。输出进入 [[symbols/queue-finish]] 前必须完整。

## 反向关系与测试

元信息只列通过 Router 的已核对调用链，Router 本身未单独建页。底层 [[symbols/butler-handle]] 的变化会影响此消费者。测试 tests/unit/queue/test_processor_queue_errors.py 和 tests/unit/model_stream/test_model_stream_transport.py（本地）。

## 代码依据

- `src/wxbot/processor/butler.py:60` — `def handle_reply(`
- `src/wxbot/processor/butler.py:129` — `def _decode_reply(`
- `src/wxbot/processor/router.py:27` — `def handle_reply(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


[[raw/changes/2026-10-31-switchable-models]]
