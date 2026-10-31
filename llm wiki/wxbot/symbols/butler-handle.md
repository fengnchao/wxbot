---
type: symbol
module: butler
summary: 单轮身份解析、会话互斥、补发优先与最终合成
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/butler/agent/core.py
  line: 207
  anchor: 'def handle(self, contact_name:'
- path: src/butler/agent/core.py
  line: 263
  anchor: def _handle_request(
- path: src/butler/agent/core.py
  line: 297
  anchor: 'def _handle(self, c:'
- path: src/butler/server.py
  line: 345
  anchor: res = butler.handle(contact, text,
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch-core-emit
calls:
- symbols/butler-result
called_by: []
---
# Butler.handle

## 签名与职责

`handle(contact_name, text, msg_id=None, channel_type='dm', member_key='', member_name='', avatar='', group_context_seq=0, on_event=None)`。所属 [[modules/butler]]；返回 [[symbols/butler-result]]。

## 调用关系

由 server.make_handler 中 [[apis/butler-handle]] / [[apis/butler-handle-stream]] 调用（其它调用方不在本批穷举）。内部 `_handle_request` 解析联系人并绑定 request trace，在 session 锁下进入 `_handle` 或指定转发路由；`_handle` 先 take_and_claim 补发，再做规则路由、调用后端、行动执行和最终合成。

## 副作用与风险

写 flow/trace；可能读取记忆、归档群上下文、执行经授权工具并认领补发；具体业务表待建档。msg_id 回填 meta。流式 sendable 前缀受最终合成约束，群身份/补发时不可随意提早发送。关联 [[concepts/message-pipeline]]、[[concepts/identity-authority]] 和 [[symbols/butler-processor]]。

## 测试

本地 tests/butler/test_pipeline.py、test_butler_concurrency.py、tests/unit/model_stream/test_model_stream_pipeline.py。

## 代码依据

- `src/butler/agent/core.py:207` — `def handle(self, contact_name:`
- `src/butler/agent/core.py:263` — `def _handle_request(`
- `src/butler/agent/core.py:297` — `def _handle(self, c:`
- `src/butler/server.py:345` — `res = butler.handle(contact, text,`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

## 请求级模型一致性

handle 在 [[symbols/reloadable-backend]] 的 request 上下文中固定后端，直到最终结果/流式包和群游标处理结束。配置错误在未发送前明确失败，不自动落回另一个模型。

`emit('backend')` 的 provider 改用 `Config.model_identity`，按接入方式（`[model].provider`）上报真实模型来源；未填时仍回退协议名。


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch-core-emit]]
