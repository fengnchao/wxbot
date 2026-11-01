---
type: concept
module: butler
summary: 模型失败的分类、脱敏、自动重试与超时放行契约
coverage: core
last_verified: '2026-11-01'
sources:
- path: src/butler/agent/hermes.py
  line: 36
  anchor: 'class HermesError(Exception):'
- path: src/butler/backends/compatible.py
  line: 112
  anchor: 'def _error_detail(exc):'
- path: src/butler/backends/models.py
  line: 72
  anchor: 'except HermesError as exc:'
- path: src/butler/backends/codex.py
  line: 349
  anchor: failure.retry_safe=not submitted
- path: src/butler/runtime/model_switch.py
  line: 21
  anchor: 'class ModelConfigurationError(HermesError):'
- path: src/butler/agent/core.py
  line: 255
  anchor: emit('error',code='incomplete_result'
- path: src/butler/server.py
  line: 391
  anchor: stream_event({'type':'error','code':type(e).__name__,
- path: src/wxbot/processor/butler.py
  line: 99
  anchor: raise ValueError('Butler stream failed'
- path: src/wxbot/processor/butler.py
  line: 137
  anchor: error.retry_safe=meta.get('retry_safe') is True
- path: src/wxbot/processor/openai_compat.py
  line: 141
  anchor: if on_event is not None:exc.retry_safe=False
- path: src/wxbot/queue_worker.py
  line: 174
  anchor: safe=getattr(exc,'retry_safe',False) is True
- path: src/wxbot/queue_store.py
  line: 395
  anchor: '''model_retryable'' if retry_safe else ''model_uncertain'''
- path: src/wxbot/model_recovery.py
  line: 2
  anchor: MODEL_MAX_ATTEMPTS=3
- path: src/wxbot/queue_store.py
  line: 414
  anchor: 结束失败批次并放行后续消息
changes:
- raw/changes/2026-11-01-model-request-error-visibility
- raw/changes/2026-11-01-model-error-contract
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-01-knowledge-vault-graph
---
# 模型失败契约

## 术语与状态含义

`retry_safe` 只有一问：这次失败能不能在不重复副作用的前提下重放。默认是 **False**——`HermesError` 本身不带这个属性（`src/butler/agent/hermes.py:36` 只有 `status`/`detail`），下游一律用 `getattr(exc,'retry_safe',False)` 取值，所以"没显式标记"就等于"不许重试"。

两个互斥事件动作：`model_retryable`（模型尚未提交，可自动重试）和 `model_uncertain`（结果未知，禁止重放）。写在 `delivery_events.action`，不是 `batches.state` 的枚举值（`src/wxbot/queue_store.py:395`）。

`reply_complete=False` 是 Butler 内部的"没有完整终态"标记，与 `retry_safe` 相互独立：可以完整失败但可重试，也可以不完整且不可重试。

## 业务规则与边界

**什么算可重试**（唯一的 True 来源只有两类）：

1. 配置在碰到任何后端之前就被拒绝——`ModelConfigurationError.retry_safe = True`（`src/butler/runtime/model_switch.py:21`）。这是类属性，不进 `__init__`。
2. Codex 已判定"未提交"——`retry_safe = not submitted`（`src/butler/backends/codex.py:349`）。提交给远端之后哪怕超时也算不可重试，因为远端可能已产生副作用。

**什么算不可重试**：

- 全部 HTTP 类后端（`openai`/`responses`/`hermes`/`openclaw`/`ollama`/`cursor`/`echo`，接入方式为 `deepseek`/`custom` 时同为该路径）显式置 False（`src/butler/backends/models.py:75`、`:80`）。`create_backend` 的协议分支共 8 种，见 `src/butler/backends/__init__.py:12`。
- wxbot 直连模型的旧路径恒为 False（`src/wxbot/processor/openai_compat.py:141`）。
- Butler SSE 处理器的兜底异常恒为 False（`src/butler/server.py:392`）。

**放行规则**：同一批次最多试 3 次，间隔 5 秒、15 秒（`src/wxbot/model_recovery.py:2`）。整轮失败时限取 `queue.failure_discard_seconds`（默认 180 秒，范围 1–86400，`src/wxbot/config.py:53`），从**首次失败**起算（`src/wxbot/model_recovery.py:17`），到期即结束该失败批次并放行后续消息，原因串保留原始失败正文（`src/wxbot/queue_store.py:414`）。这两个终止条件任一先到就放弃，不必都满足。

**永远不会发生的事**：失败不会产生已投递回复，也不会进入发件箱。`CompatibleBackend.chat` 在返回前抛错（`src/butler/backends/compatible.py:147`），`OpenAICompatProcessor._handle_reply` 的注释明确"失败的回合绝不能变成已投递回复"（`src/wxbot/processor/openai_compat.py:150`）。

失败轮仍会在 L1 原文库里留一条 `outcome='error'` 的记录（[[tables/kb-episodes]]，`reply_text` 为空）。那不是"已投递回复"，而是排障用的旁路存证：与 `queue-outbox` 和 `batches.reply_text` 无关，也不参与重试判定。

拆库（同日的 knowledge-sharding）只改了这条记录的落盘位置：`data/knowledge.sqlite3` 变成 `data/knowledge/` 下按 owner 分库的 `p-<slug>/episodes.sqlite3`，`outcome` 取值、`reply_text` 为空的做法，以及「不进 `queue-outbox`、不参与重试判定」的结论均未变。

## 跨层映射

失败原因在四层里换形但不换语义，逐层对照：

| 层 | 位置 | 表达形式 |
|---|---|---|
| 后端 | `src/butler/backends/compatible.py:112` | `HermesError("{provider} model request failed ({type} {status}：{本地提示})")` |
| Butler core | `src/butler/agent/core.py:387` | `Result(meta={'error','status','reply_complete':False,'retry_safe'})` |
| SSE | `src/butler/agent/core.py:252` | `error` 事件，`code='incomplete_result'` |
| wxbot 适配 | `src/wxbot/processor/butler.py:99` | `ValueError('Butler stream failed: {code}: {message}')`，属性 `retry_safe` 在 `:115` 补挂 |
| 队列 worker | `src/wxbot/queue_worker.py:174` | `fail_batch(..., retry_safe=safe)` |
| 队列存储 | `src/wxbot/queue_store.py:389` | `batches.state='uncertain'` + 事件动作二选一 |
| 维护线程 | `src/wxbot/model_recovery.py:18` | `model_retry` / `model_abandoned` |

`retry_safe` 有**两个**来源，wxbot 两处都读且不能混：流中 `error` 事件（`:115`，只对 `code='model_configuration'` 且有 `retry_safe=True` 才放行），以及 `result.meta`（`:137`）。前者用于"刚开跑就配置错"，后者用于"跑完发现不完整"。

不过 HTTP 路径时（`/v1/handle`，无 `on_event`），Butler 在 `uses_local_runtime` 下返回 `reply_complete=False` 的对象，wxbot 由 `_decode_reply` 转成带 `retry_safe` 的 `ValueError`（`src/wxbot/processor/butler.py:135`），语义与流式一致。

## 历史坑与冲突

**二次包装吞掉真实原因**。`LocalModelBackend.chat` 调用 `super().chat()`，父类抛的 `HermesError` 落进自己的 `except Exception` 又被包一层，错误文本变成 `openai model request failed (HermesError)`——类型名指向包装者而非根因，状态码全丢。现在 `src/butler/backends/models.py:72` 用 `except HermesError` 直通并保留 `retry_safe=False`，禁止再包装。

**错误消息曾经不可定位**。原实现只输出异常类型名，401/404/400 无法区分，地址填错和模型名写错长得一模一样。`src/butler/backends/compatible.py:112` 现在补状态码与一句本地提示（401 查密钥、403 权限、404 路径、400 模型名、429 限流），但仍不回显 URL、密钥和远端响应正文。

**"报错但看不出为什么"不是脱敏问题**。脱敏是必要的（异常里可能含 key），正确做法是保留**可判定**的部分（状态码）而不是把整个原因抹平。

**配置改了不立刻生效的错觉**。`ReloadableBackend` 每次请求前重读 TOML（`src/butler/runtime/model_switch.py:109`），旧的失败批次仍按旧配置的记录走恢复流程；判定新配置是否生效要看下一个请求的 `retry_status`，不是看队列里的历史报错。

## 相关模块、接口、测试

- 后端与热切换：[[modules/models]]、[[symbols/local-model-backend]]、[[symbols/reloadable-backend]]
- SSE 契约：[[apis/butler-handle-stream]]、[[apis/butler-handle]]、[[symbols/butler-processor]]
- 队列与投递：[[tables/queue-batches]]、[[concepts/delivery-state]]、[[symbols/model-worker]]、[[symbols/queue-store]]
- 只读投影：[[apis/dashboard-queue]] 展示剩余时限与建议动作，不能触发恢复

本地用例（`tests/` 不入 Git）：`test_backend_adapters.py` 覆盖状态码可见性与密钥不外泄；`test_model_switch_runtime.py` 覆盖代际切换；`test_model_recovery.py` 覆盖 3 次上限与超时放弃；`test_transport.py`、`test_pipeline.py` 覆盖错误传播与不投递。

## 代码依据与修改来源

- `src/butler/agent/hermes.py:36` — `class HermesError(Exception):`
- `src/butler/backends/compatible.py:112` — `def _error_detail(exc):`
- `src/butler/backends/models.py:72` — `except HermesError as exc:`
- `src/butler/backends/codex.py:349` — `failure.retry_safe=not submitted`
- `src/butler/runtime/model_switch.py:21` — `class ModelConfigurationError(HermesError):`
- `src/butler/agent/core.py:252` — `emit('error',code='incomplete_result'`
- `src/butler/server.py:392` — `stream_event({'type':'error','code':type(e).__name__,`
- `src/wxbot/processor/butler.py:99` — `raise ValueError('Butler stream failed'`
- `src/wxbot/processor/butler.py:137` — `error.retry_safe=meta.get('retry_safe') is True`
- `src/wxbot/processor/openai_compat.py:141` — `if on_event is not None:exc.retry_safe=False`
- `src/wxbot/queue_worker.py:174` — `safe=getattr(exc,'retry_safe',False) is True`
- `src/wxbot/queue_store.py:395` — `'model_retryable' if retry_safe else 'model_uncertain'`
- `src/wxbot/model_recovery.py:2` — `MODEL_MAX_ATTEMPTS=3`
- `src/wxbot/queue_store.py:414` — `结束失败批次并放行后续消息`

## 入库来源

[[raw/changes/2026-11-01-model-request-error-visibility]]、[[raw/changes/2026-11-01-model-error-contract]]

[[raw/changes/2026-11-01-knowledge-episodes]]

[[raw/changes/2026-11-01-knowledge-sharding]]

[[raw/changes/2026-11-01-knowledge-auto]]

[[raw/changes/2026-11-01-mention-fallback-unread-retry]]
