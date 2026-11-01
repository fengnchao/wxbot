---
type: symbol
module: models
coverage: core
summary: 原生函数工具走服务签发身份，完整结果才进入历史
last_verified: '2026-11-01'
sources:
- path: src/butler/backends/models.py
  line: 16
  anchor: class LocalModelBackend
- path: src/butler/backends/models.py
  line: 83
  anchor: def _native_chat(
- path: src/butler/backends/models.py
  line: 72
  anchor: 'except HermesError as exc:'
- path: src/butler/backends/compatible.py
  line: 72
  anchor: def scope(
- path: src/butler/backends/compatible.py
  line: 112
  anchor: def _error_detail(
changes:
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch
- raw/changes/2026-11-01-model-request-error-visibility
---
# LocalModelBackend


所属 [[modules/models]]，实现 ModelBackend 的 chat/reset/session_id/alive/close。scope 包含后端地址/模型、联系人、记忆/绑定版本、策略与用途；不同成员和 heartbeat 历史隔离。角色由服务目录读取，额外上下文不会授予权限。

`self.identity` 是展示与分代用的模型来源：`[model].provider` 是产品名（如 deepseek）时用它，否则用协议名。它参与 scope 哈希（换产品即换会话）和 `emit('backend')` 上报，因此不会把 DeepSeek 请求记成 openai。

OpenAI/Responses 原生工具循环最多 8 轮、32 次调用且受总时间限制。服务端 issue/definitions/call 决定身份、工具白名单、只读和记忆许可；模型不能传入 owner/contact/uid 等身份字段，服务 token 不进入模型上下文。

只接受完整终态；错误、不完整回复、未解决调用不写成功历史或发送正文。工具可能已产生副作用后模型失败，此时标记 retry_safe=False，不能自动重放。其它协议使用 CompatibleBackend 的完整结果实现，见 [[concepts/delivery-state]]。

失败原因统一由 `CompatibleBackend._error_detail` 组装：只保留异常类型名与 HTTP 状态码，附一句本地排查提示（授权、地址路径、模型名），不回显请求地址、密钥或远端响应正文。`chat` 捕获到内层 `HermesError` 时直接透传，不再二次包装，否则状态码会被替换成 `HermesError`；此类失败同样标记 `retry_safe=False`。


## 代码依据

- `src/butler/backends/models.py:16` — `class LocalModelBackend`
- `src/butler/backends/models.py:83` — `def _native_chat(`
- `src/butler/backends/models.py:72` — `except HermesError as exc:`
- `src/butler/backends/compatible.py:72` — `def scope(`
- `src/butler/backends/compatible.py:112` — `def _error_detail(`

## 入库来源


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch]]

[[raw/changes/2026-11-01-model-request-error-visibility]]
