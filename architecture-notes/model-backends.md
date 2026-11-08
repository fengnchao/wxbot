# 可切换模型后端

统一入口为 wxbot → Butler → ModelBackend。模型切换不迁移联系人、权限、提醒或知识；工具权限仍由业务服务签发与核验。具体协议、错误处理和会话代际见下方资料。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 使用说明

- [wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / news/ 与 backends/](#doc-3cc18faa25d1d5) · `README.md`

<a id="doc-3cc18faa25d1d5"></a>

### wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / news/ 与 backends/

来源：`README.md:267`。

###### news/ 与 backends/

| 文件 | 职责 |
|---|---|
| `news/__main__.py` | `python -m butler.news [--preview]`，不启动任何服务 |
| `news/collector.py` | 有界 RSS 抓取、确定性挑选、标注来源的摘要 |
| `news/delivery.py` | 日报持久化与逐收件人／分段回执 |
| `backends/codex.py` | 隔离的、有界的官方 SDK worker；绝不返回未完成的模型输出 |
| `backends/codex_runtime.py` | 给 SDK 的阻塞启动和模型流都加时限 |
| `backends/compatible.py` | 通用模型会话隔离、完整结果和 HTTP/CLI 传输适配 |
| `backends/models.py` | OpenAI/Responses 原生函数工具循环，权限由 Butler 服务签发 |
<!-- end-migrated-part: doc-3cc18faa25d1d5 -->

## 技术资料

- [模型失败契约](#doc-77e385a27b73a6) · `llm wiki/wxbot/concepts/model-error-contract.md`
- [model-switch-verification](#doc-c5a09700a83870) · `llm wiki/wxbot/model-switch-verification.md`
- [统一模型后端](#doc-69928b2a06b8f9) · `llm wiki/wxbot/modules/models.md`
- [LocalModelBackend](#doc-058aec74f1727e) · `llm wiki/wxbot/symbols/local-model-backend.md`
- [ReloadableBackend](#doc-85aba8d0cc88bd) · `llm wiki/wxbot/symbols/reloadable-backend.md`

<a id="doc-77e385a27b73a6"></a>

### 模型失败契约

来源：`llm wiki/wxbot/concepts/model-error-contract.md:1`。

```yaml
type: concept
module: butler
summary: 模型失败的分类、脱敏、自动重试与超时放行契约
coverage: core
last_verified: '2026-11-05'
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
  line: 350
  anchor: failure.retry_safe=not submitted
- path: src/butler/runtime/model_switch.py
  line: 21
  anchor: 'class ModelConfigurationError(HermesError):'
- path: src/butler/agent/core.py
  line: 261
  anchor: emit('error',code='incomplete_result'
- path: src/butler/server.py
  line: 435
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
  line: 186
  anchor: safe=getattr(exc,'retry_safe',False) is True
- path: src/wxbot/queue_store.py
  line: 424
  anchor: '''model_retryable'' if retry_safe else ''model_uncertain'''
- path: src/wxbot/model_recovery.py
  line: 2
  anchor: MODEL_MAX_ATTEMPTS=3
- path: src/wxbot/queue_store.py
  line: 443
  anchor: 结束失败批次并放行后续消息
changes:
- raw/changes/2026-11-03-indextts-enqueue-media
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-03-feat-voice-001-anchor-refresh
- raw/changes/2026-11-01-model-request-error-visibility
- raw/changes/2026-11-01-model-error-contract
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-details-whitelist-reverify
- raw/changes/2026-11-02-mention-residue-reverify
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
```
### 模型失败契约

#### 术语与状态含义

`retry_safe` 只有一问：这次失败能不能在不重复副作用的前提下重放。默认是 **False**——`HermesError` 本身不带这个属性（`src/butler/agent/hermes.py:36` 只有 `status`/`detail`），下游一律用 `getattr(exc,'retry_safe',False)` 取值，所以"没显式标记"就等于"不许重试"。

两个互斥事件动作：`model_retryable`（模型尚未提交，可自动重试）和 `model_uncertain`（结果未知，禁止重放）。写在 `delivery_events.action`，不是 `batches.state` 的枚举值（`src/wxbot/queue_store.py:395`）。

`reply_complete=False` 是 Butler 内部的"没有完整终态"标记，与 `retry_safe` 相互独立：可以完整失败但可重试，也可以不完整且不可重试。

#### 业务规则与边界

**什么算可重试**（唯一的 True 来源只有两类）：

1. 配置在碰到任何后端之前就被拒绝——`ModelConfigurationError.retry_safe = True`（`src/butler/runtime/model_switch.py:21`）。这是类属性，不进 `__init__`。
2. Codex 已判定"未提交"——`retry_safe = not submitted`（`src/butler/backends/codex.py:350`）。提交给远端之后哪怕超时也算不可重试，因为远端可能已产生副作用。

**什么算不可重试**：

- 全部 HTTP 类后端（`openai`/`responses`/`hermes`/`openclaw`/`ollama`/`cursor`/`echo`，接入方式为 `deepseek`/`custom` 时同为该路径）显式置 False（`src/butler/backends/models.py:75`、`:80`）。`create_backend` 的协议分支共 8 种，见 `src/butler/backends/__init__.py:12`。
- wxbot 直连模型的旧路径恒为 False（`src/wxbot/processor/openai_compat.py:141`）。
- Butler SSE 处理器的兜底异常恒为 False（`src/butler/server.py:392`）。

**放行规则**：同一批次最多试 3 次，间隔 5 秒、15 秒（`src/wxbot/model_recovery.py:2`）。整轮失败时限取 `queue.failure_discard_seconds`（默认 180 秒，范围 1–86400，`src/wxbot/config.py:53`），从**首次失败**起算（`src/wxbot/model_recovery.py:17`），到期即结束该失败批次并放行后续消息，原因串保留原始失败正文（`src/wxbot/queue_store.py:414`）。这两个终止条件任一先到就放弃，不必都满足。

**永远不会发生的事**：失败不会产生已投递回复，也不会进入发件箱。`CompatibleBackend.chat` 在返回前抛错（`src/butler/backends/compatible.py:147`），`OpenAICompatProcessor._handle_reply` 的注释明确"失败的回合绝不能变成已投递回复"（`src/wxbot/processor/openai_compat.py:150`）。

2026-11-02 复核：`queue_store.py` 的变更是扩展 `delivery_events.details` 白名单（投递侧 `error_code` / `retry` / `confirm_evidence` / `ref_available`），模型失败的 `retry_safe` / 三次上限 / 超时放行规则均未变；两套失败语义不要混用。

失败轮仍会在 L1 原文库里留一条 `outcome='error'` 的记录（[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)，`reply_text` 为空）。那不是"已投递回复"，而是排障用的旁路存证：与 `queue-outbox` 和 `batches.reply_text` 无关，也不参与重试判定。

拆库（同日的 knowledge-sharding）只改了这条记录的落盘位置：`data/knowledge.sqlite3` 变成 `data/knowledge/` 下按 owner 分库的 `p-<slug>/episodes.sqlite3`，`outcome` 取值、`reply_text` 为空的做法，以及「不进 `queue-outbox`、不参与重试判定」的结论均未变。

#### 跨层映射

失败原因在四层里换形但不换语义，逐层对照：

| 层 | 位置 | 表达形式 |
|---|---|---|
| 后端 | `src/butler/backends/compatible.py:112` | `HermesError("{provider} model request failed ({type} {status}：{本地提示})")` |
| Butler core | `src/butler/agent/core.py:406` | `Result(meta={'error','status','reply_complete':False,'retry_safe'})` |
| SSE | `src/butler/agent/core.py:261` | `error` 事件，`code='incomplete_result'` |
| wxbot 适配 | `src/wxbot/processor/butler.py:99` | `ValueError('Butler stream failed: {code}: {message}')`，属性 `retry_safe` 在 `:115` 补挂 |
| 队列 worker | `src/wxbot/queue_worker.py:186` | `fail_batch(..., retry_safe=safe)` |
| 队列存储 | `src/wxbot/queue_store.py:389` | `batches.state='uncertain'` + 事件动作二选一 |
| 维护线程 | `src/wxbot/model_recovery.py:18` | `model_retry` / `model_abandoned` |

`retry_safe` 有**两个**来源，wxbot 两处都读且不能混：流中 `error` 事件（`:115`，只对 `code='model_configuration'` 且有 `retry_safe=True` 才放行），以及 `result.meta`（`:137`）。前者用于"刚开跑就配置错"，后者用于"跑完发现不完整"。

不过 HTTP 路径时（`/v1/handle`，无 `on_event`），Butler 在 `uses_local_runtime` 下返回 `reply_complete=False` 的对象，wxbot 由 `_decode_reply` 转成带 `retry_safe` 的 `ValueError`（`src/wxbot/processor/butler.py:135`），语义与流式一致。

#### 历史坑与冲突

**二次包装吞掉真实原因**。`LocalModelBackend.chat` 调用 `super().chat()`，父类抛的 `HermesError` 落进自己的 `except Exception` 又被包一层，错误文本变成 `openai model request failed (HermesError)`——类型名指向包装者而非根因，状态码全丢。现在 `src/butler/backends/models.py:72` 用 `except HermesError` 直通并保留 `retry_safe=False`，禁止再包装。

**错误消息曾经不可定位**。原实现只输出异常类型名，401/404/400 无法区分，地址填错和模型名写错长得一模一样。`src/butler/backends/compatible.py:112` 现在补状态码与一句本地提示（401 查密钥、403 权限、404 路径、400 模型名、429 限流），但仍不回显 URL、密钥和远端响应正文。

**"报错但看不出为什么"不是脱敏问题**。脱敏是必要的（异常里可能含 key），正确做法是保留**可判定**的部分（状态码）而不是把整个原因抹平。

**配置改了不立刻生效的错觉**。`ReloadableBackend` 每次请求前重读 TOML（`src/butler/runtime/model_switch.py:109`），旧的失败批次仍按旧配置的记录走恢复流程；判定新配置是否生效要看下一个请求的 `retry_status`，不是看队列里的历史报错。

#### 相关模块、接口、测试

- 后端与热切换：[modules/models](model-backends.md#doc-69928b2a06b8f9)、[symbols/local-model-backend](model-backends.md#doc-058aec74f1727e)、[symbols/reloadable-backend](model-backends.md#doc-85aba8d0cc88bd)
- SSE 契约：[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)、[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24)
- 队列与投递：[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[symbols/model-worker](queue-worker.md#doc-0183b6974519f0)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)
- 只读投影：[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f) 展示剩余时限与建议动作，不能触发恢复

本地用例（`tests/` 不入 Git）：`test_backend_adapters.py` 覆盖状态码可见性与密钥不外泄；`test_model_switch_runtime.py` 覆盖代际切换；`test_model_recovery.py` 覆盖 3 次上限与超时放弃；`test_transport.py`、`test_pipeline.py` 覆盖错误传播与不投递。

#### 代码依据与修改来源

- `src/butler/agent/hermes.py:36` — `class HermesError(Exception):`
- `src/butler/backends/compatible.py:112` — `def _error_detail(exc):`
- `src/butler/backends/models.py:72` — `except HermesError as exc:`
- `src/butler/backends/codex.py:350` — `failure.retry_safe=not submitted`
- `src/butler/runtime/model_switch.py:21` — `class ModelConfigurationError(HermesError):`
- `src/butler/agent/core.py:261` — `emit('error',code='incomplete_result'`
- `src/butler/server.py:435` — `stream_event({'type':'error','code':type(e).__name__,`
- `src/wxbot/processor/butler.py:99` — `raise ValueError('Butler stream failed'`
- `src/wxbot/processor/butler.py:137` — `error.retry_safe=meta.get('retry_safe') is True`
- `src/wxbot/processor/openai_compat.py:141` — `if on_event is not None:exc.retry_safe=False`
- `src/wxbot/queue_worker.py:186` — `safe=getattr(exc,'retry_safe',False) is True`
- `src/wxbot/queue_store.py:424` — `'model_retryable' if retry_safe else 'model_uncertain'`
- `src/wxbot/model_recovery.py:2` — `MODEL_MAX_ATTEMPTS=3`
- `src/wxbot/queue_store.py:443` — `结束失败批次并放行后续消息`

`retry_safe` 读取点现位于 `queue_worker.py:190`（该文件增加语音 media 导入后下移一行）。失败分类未改。见 [raw/changes/2026-11-03-indextts-enqueue-media](index-tts.md#doc-29fc2d893f2889)。

#### 入库来源

[raw/changes/2026-11-01-model-request-error-visibility](model-backends.md#doc-507fd880895f6c)、[raw/changes/2026-11-01-model-error-contract](model-backends.md#doc-60c1969bb5f6f6)

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-details-whitelist-reverify](delivery-pump.md#doc-ae7b71a2b37518)

[raw/changes/2026-11-02-mention-residue-reverify](wechat-ui.md#doc-989f2003dec3a1)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 群聊采集与自动语音复核（2026-11-05）

[concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00) 补充自动语音的缓冲/后台准备与失败单次回退；[concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66) 补充越屏恢复，未修改模型后端请求/重试合同。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。

#### 本次核对

联系人补建先于模型处理，模型错误分类、流式契约与重试判断沿用。 来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 本次核对

知识事实删除错误属于独立 HTTP 契约，模型失败和重试分类沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

已对照当前共享源码复核本词条的接口或调用位置。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。
<!-- end-migrated-part: doc-77e385a27b73a6 -->

<a id="doc-c5a09700a83870"></a>

### model-switch-verification

来源：`llm wiki/wxbot/model-switch-verification.md:1`。


<!-- end-migrated-part: doc-c5a09700a83870 -->

<a id="doc-69928b2a06b8f9"></a>

### 统一模型后端

来源：`llm wiki/wxbot/modules/models.md:1`。

```yaml
type: module
module: models
coverage: core
summary: Butler 管理可切换模型与服务授权工具，wxbot 只调用 Butler
last_verified: '2026-11-01'
sources:
- path: src/butler/backends/__init__.py
  line: 12
  anchor: def create_backend(
- path: src/butler/backends/models.py
  line: 16
  anchor: class LocalModelBackend
- path: src/butler/backends/compatible.py
  line: 31
  anchor: PRODUCT_ENDPOINTS =
- path: src/butler/backends/compatible.py
  line: 36
  anchor: _STATUS_HINTS =
- path: src/butler/runtime/model_switch.py
  line: 50
  anchor: class ReloadableBackend
- path: src/dashboard/config_schema.py
  line: 166
  anchor: def row_metadata(
- path: src/dashboard/config_schema.py
  line: 136
  anchor: def access_provider(
- path: web/src/views/ConfigurationView.vue
  line: 37
  anchor: const backendName =
changes:
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch
- raw/changes/2026-11-01-model-request-error-visibility
- raw/changes/2026-11-01-model-error-contract
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
```
### 统一模型后端


所属 [modules/butler](butler.md#doc-38393df7a7b4da)；微信入口 [modules/wxbot](wxbot.md#doc-8508032cbe5131) → Butler → codex/hermes/openai/responses/openclaw/cursor/ollama/echo。

`[agent].provider` 选择后端，Codex 读取 `[codex]`；通用后端读取 `[model]` 的 url/model/api_key/timeout/max_history/system_prompt，以及 Cursor executable/work_dir 或 OpenClaw agent。`[hermes]` 兼容旧配置。页面 [modules/web](dashboard.md#doc-aeec90dfe23cd3) 使用草稿 provider 过滤适用字段，密钥使用既有保持/替换/清空语义。

分层语义：`[model].provider` 是接入方式（产品身份，可含 deepseek/custom），`[agent].provider` 与 `[model].backend` 是运行协议。页面只维护接入方式，由 `config_schema.ACCESS_PROTOCOLS` 推导协议并同时写入两处；`config_schema.access_fields()` 决定该接入方式真正要填的字段，未填的用 `ACCESS_HINTS` 占位而不是写入文件。CompatibleBackend 用 `PRODUCT_ENDPOINTS` 按产品身份选默认端点，空 url/model 也算未填，避免留空时落到另一家服务的官方地址。

模型通过 [symbols/reloadable-backend](model-backends.md#doc-85aba8d0cc88bd) 在后续请求切换；身份、业务库、认证、端口和监听目录仍是启动配置，不随模型重载。配置保存并非网络验证，真实服务可用性需另行授权验证。

配置保存只校验地址格式，不会补全路径也不会比对模型名：`[model].url` 必须是可以直接 POST 的完整端点（通常是 `.../v1/chat/completions` 或 `.../v1/responses`），`model` 必须是服务端实际提供的名称。填错时下一次请求即失败，失败原因由 `CompatibleBackend._error_detail` 保留状态码与本地提示（401 查密钥、404 查地址路径、400 查模型名）。失败后到底重试还是放弃、多久放行后续消息，统一见 [concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)。

[symbols/local-model-backend](model-backends.md#doc-058aec74f1727e) 对 OpenAI/Responses 支持经 ToolService 许可的原生函数工具；Codex 保留原工具实现。Hermes/OpenClaw/Cursor/Ollama 是完整结果路径，不宣称具有 Butler 原生工具桥；未处理的工具调用会失败。Cursor 始终 ask/sandbox 且独立目录，不执行来自聊天的 CLI 选项。

旧 direct 安装使用 `python -m butler migrate` 显式迁移；迁移仅将本机参数移到 Butler 并备份，禁止把备份提交 Git。业务表结构不变；远端模型对话会话不保证跨后端移植。模型 API Key 不是本地身份授权，见 [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。


#### 代码依据

- `src/butler/backends/__init__.py:12` — `def create_backend(`
- `src/butler/backends/models.py:16` — `class LocalModelBackend`
- `src/butler/backends/compatible.py:31` — `PRODUCT_ENDPOINTS =`
- `src/butler/backends/compatible.py:36` — `_STATUS_HINTS =`
- `src/butler/runtime/model_switch.py:50` — `class ReloadableBackend`
- `src/dashboard/config_schema.py:166` — `def row_metadata(`
- `src/dashboard/config_schema.py:136` — `def access_provider(`
- `web/src/views/ConfigurationView.vue:37` — `const backendName =`

#### 入库来源


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-10-31-model-access-switch](model-backends.md#doc-954a7ea1e7487b)

[raw/changes/2026-11-01-model-request-error-visibility](model-backends.md#doc-507fd880895f6c)

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)
<!-- end-migrated-part: doc-69928b2a06b8f9 -->

<a id="doc-058aec74f1727e"></a>

### LocalModelBackend

来源：`llm wiki/wxbot/symbols/local-model-backend.md:1`。

```yaml
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
- raw/changes/2026-11-01-knowledge-vault-graph
```
### LocalModelBackend


所属 [modules/models](model-backends.md#doc-69928b2a06b8f9)，实现 ModelBackend 的 chat/reset/session_id/alive/close。scope 包含后端地址/模型、联系人、记忆/绑定版本、策略与用途；不同成员和 heartbeat 历史隔离。角色由服务目录读取，额外上下文不会授予权限。

`self.identity` 是展示与分代用的模型来源：`[model].provider` 是产品名（如 deepseek）时用它，否则用协议名。它参与 scope 哈希（换产品即换会话）和 `emit('backend')` 上报，因此不会把 DeepSeek 请求记成 openai。

OpenAI/Responses 原生工具循环最多 8 轮、32 次调用且受总时间限制。服务端 issue/definitions/call 决定身份、工具白名单、只读和记忆许可；模型不能传入 owner/contact/uid 等身份字段，服务 token 不进入模型上下文。

只接受完整终态；错误、不完整回复、未解决调用不写成功历史或发送正文。工具可能已产生副作用后模型失败，此时标记 retry_safe=False，不能自动重放。其它协议使用 CompatibleBackend 的完整结果实现，见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。

失败原因统一由 `CompatibleBackend._error_detail` 组装：只保留异常类型名与 HTTP 状态码，附一句本地排查提示（授权、地址路径、模型名），不回显请求地址、密钥或远端响应正文。`chat` 捕获到内层 `HermesError` 时直接透传，不再二次包装，否则状态码会被替换成 `HermesError`；此类失败同样标记 `retry_safe=False`。


#### 代码依据

- `src/butler/backends/models.py:16` — `class LocalModelBackend`
- `src/butler/backends/models.py:83` — `def _native_chat(`
- `src/butler/backends/models.py:72` — `except HermesError as exc:`
- `src/butler/backends/compatible.py:72` — `def scope(`
- `src/butler/backends/compatible.py:112` — `def _error_detail(`

#### 入库来源


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-10-31-model-access-switch](model-backends.md#doc-954a7ea1e7487b)

[raw/changes/2026-11-01-model-request-error-visibility](model-backends.md#doc-507fd880895f6c)
<!-- end-migrated-part: doc-058aec74f1727e -->

<a id="doc-85aba8d0cc88bd"></a>

### ReloadableBackend

来源：`llm wiki/wxbot/symbols/reloadable-backend.md:1`。

```yaml
type: symbol
module: models
coverage: core
summary: 请求固定后端代际，在途完成后才关闭旧工作进程
last_verified: '2026-10-31'
sources:
- path: src/butler/runtime/model_switch.py
  line: 50
  anchor: class ReloadableBackend
- path: src/butler/runtime/model_switch.py
  line: 134
  anchor: def request(
- path: src/butler/runtime/model_switch.py
  line: 109
  anchor: def _refresh(
changes:
- raw/changes/2026-10-31-switchable-models
```
### ReloadableBackend


所属 [modules/models](model-backends.md#doc-69928b2a06b8f9)。`request()` 使用 ContextVar 固定本轮 generation；chat/reset/session_id 复用固定上下文。只复制模型字段，保留启动时服务身份、存储和路径；实际配置文件名由 Config.config_path 保存。

新请求读取配置并按差异构造后端，旧后端在用户计数归零后关闭；在途请求不迁移、不重放。Codex 代际工具凭据映射只在其生命周期内共同有效。解析/构造失败阻止新请求并暴露脱敏错误，保留旧代际供诊断与在途完成。

`runtime_status()` 报实际 backend/model、configured_backend、reload_error、active_requests 与 retiring_backends。数据库身份不随代际重建；消费方 [symbols/butler-handle](butler.md#doc-eba67ca6f97d80)，相关行为通过临时 fake 后端并发测试验证。


#### 代码依据

- `src/butler/runtime/model_switch.py:50` — `class ReloadableBackend`
- `src/butler/runtime/model_switch.py:134` — `def request(`
- `src/butler/runtime/model_switch.py:109` — `def _refresh(`

#### 入库来源


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)
<!-- end-migrated-part: doc-85aba8d0cc88bd -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [统一 Butler 模型接入与运行中切换](#doc-7e58558178e006) · `llm wiki/wxbot/impacts/2026-10-31-switchable-models.md`
- [模型来源上报改用接入方式（core.py 相关词条更正）](#doc-6510cadeadeb37) · `llm wiki/wxbot/raw/changes/2026-10-31-model-access-switch-core-emit.md`
- [配置页接入方式下拉与模型字段随选择变化](#doc-954a7ea1e7487b) · `llm wiki/wxbot/raw/changes/2026-10-31-model-access-switch.md`
- [统一 Butler 模型链路与随时切换](#doc-85f41883967373) · `llm wiki/wxbot/raw/changes/2026-10-31-switchable-models.md`
- [修改记录](#doc-60c1969bb5f6f6) · `llm wiki/wxbot/raw/changes/2026-11-01-model-error-contract.md`
- [模型请求失败保留脱敏状态码](#doc-507fd880895f6c) · `llm wiki/wxbot/raw/changes/2026-11-01-model-request-error-visibility.md`

<a id="doc-7e58558178e006"></a>

### 统一 Butler 模型接入与运行中切换

来源：`llm wiki/wxbot/impacts/2026-10-31-switchable-models.md:1`。

```yaml
type: impact
status: done
date: '2026-10-31'
```
### 统一 Butler 模型接入与运行中切换

目标：微信固定走 wxbot → Butler → Codex/Hermes/Cursor/兼容 API 或其他智能体。保存模型设置后新请求采用新后端，正在处理的请求保留原后端；不重启既有服务，不重放未知结果。

#### 查询与覆盖

已查询关键词“模型/backend/direct”，读取 [modules/butler](butler.md#doc-38393df7a7b4da)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80) 并核对源码。原图谱对非 Codex 后端和安装迁移仅概览；本次补建模型后端及切换词条。

#### 文件、调用与边界

- `src/butler/backends/__init__.py:12` 原先非 Codex 全部落入 Hermes，需要统一工厂与兼容适配。
- `src/butler/agent/core.py:84` / `server.py:122` 原先业务存储、工具与 runtime 接口只对 Codex 开启，需按 Butler 本地业务能力判断。
- `src/butler/config.py` 持有 provider/model 配置；保存后的模型相关字段按请求边界刷新，监听地址、服务 token、存储目录不热改。
- `src/dashboard/config_schema.py:111`、config_view/editor、`web/src/views/ConfigurationView.vue:27` 处理后端选项、字段和保存文案；页面按草稿选择显示字段，凭据原值只留服务端。
- 旧 direct 配置通过明确的 migrate 操作迁到本机 Butler；保留本机原配置备份，不自动修改正在使用的真实配置。

#### 接口与数据

保持 [apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc) 的完整回复契约，API/CLI 错误抛出并由既有错误路径处理。API Key、模型名、URL、协议、Cursor 工作目录等属于模型配置；不是身份权限凭证。

无需改业务表结构。联系人/记忆/提醒留在同一个 Butler 业务库；换模型不改变其归属。各后端对话历史按身份、策略和用途隔离，不能把其他人的历史带到新请求。

#### 页面与验证

保留 Vue 壳和主题，按 Hallmark app/polish 检查；新增后端选项/字段动态显示，既有 API secret keep/replace/clear 语义保留。前端 build、smoke 和实际应用 URL 渲染检查；失败或环境限制如实记录。

临时配置、假后端测试工厂、完整结果、会话隔离、运行请求固定代际、失败配置不污染现有后端、显式旧配置迁移。真实模型连接/微信发送不在离线验收范围。

#### 实施结果

运行时与后端已由 [raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373) 完成；页面侧的接入方式入口由 [raw/changes/2026-10-31-model-access-switch](model-backends.md#doc-954a7ea1e7487b) 补齐，`core.py` 上报改动另见 [raw/changes/2026-10-31-model-access-switch-core-emit](model-backends.md#doc-6510cadeadeb37)。验证结果见 [model-switch-verification](model-backends.md#doc-c5a09700a83870)。

页面只保留一个「接入方式」下拉（`[model].provider`），`[agent].provider` 与 `[model].backend` 由 `config_editor._access_changes()` 同时写入；字段适用性与说明随接口的 `model_access` 下发。空 url/model 按产品身份回退默认端点。遗留：只手工改 `[agent].provider` 仍会造成两处不一致，页面已把它移入「高级配置」并标注用途；新增产品需同时补 `PRODUCT_ENDPOINTS`。

#### 实施选择

沿用 ModelBackend 接口与现有纯 HTTP/CLI 协议实现，不引入新的常驻服务。通用 API 支持 Chat Completions/Responses，其他智能体需暴露支持的协议。热切换保留旧代际直到其在途请求结束，配置解析失败返回明确错误而非悄悄切回另一个模型。
<!-- end-migrated-part: doc-7e58558178e006 -->

<a id="doc-6510cadeadeb37"></a>

### 模型来源上报改用接入方式（core.py 相关词条更正）

来源：`llm wiki/wxbot/raw/changes/2026-10-31-model-access-switch-core-emit.md:1`。

```yaml
type: change
title: 模型来源上报改用接入方式（core.py 相关词条更正）
pages:
- apis/butler-handle
- concepts/message-pipeline
- symbols/butler-handle
- symbols/butler-result
```
### 模型来源上报改用接入方式（core.py 相关词条更正）

#### 目标与背景

补充 [raw/changes/2026-10-31-model-access-switch](model-backends.md#doc-954a7ea1e7487b) 漏登记的受影响词条。该记录改了 `src/butler/agent/core.py:255` 的 `emit('backend')`，但只把模型配置相关词条列进 pages；lint 的 source-drift 指出同一源文件的 handle/result/pipeline 词条也应有对应记录，因此单列此条，不改写已入库的历史记录。

#### 文件与代码位置

- `src/butler/agent/core.py:255`：`emit('backend', provider=model_cfg.model_identity, ...)`，去掉 `hermes_model` 兜底。
- `src/butler/config.py:86`：新增 `model_identity` property，Codex 固定 codex，其它按 `[model].provider` 产品名、回退协议名。

#### 接口与字段

不涉及。`/v1/handle` 与 `/v1/handle-stream` 的请求/响应字段、`Result.as_dict()` 的输出结构和 `meta` 语义均未变；变化只出现在流转 trace 的 `backend.provider` 展示值上（deepseek 不再显示为 openai）。队列表结构不变。

#### 数据库与迁移

不适用。无表结构、无迁移、无定时任务。

#### 前端消费点

[modules/web](dashboard.md#doc-aeec90dfe23cd3) 的实时工作流与模型面板读的是同一份 trace 字段，显示值随接入方式变化，不需要新增列或新接口。

#### 测试与异步任务

`pytest tests/dashboard tests/butler tests/unit/codex` 736 项通过，`tests/butler/test_model_switch_runtime.py` 覆盖 `butler_business_identity_survives_provider_change`。未发送真实微信消息、未调用真实模型、未重启服务。

#### 风险与回滚

若接入方式填了协议不认识的字符串，展示会退回协议名，不影响实际调用。回滚只需恢复 core.py 的 emit 参数与删除 `model_identity`；已写入的 `[model].provider` 在旧代码下作为未知值被忽略。
<!-- end-migrated-part: doc-6510cadeadeb37 -->

<a id="doc-954a7ea1e7487b"></a>

### 配置页接入方式下拉与模型字段随选择变化

来源：`llm wiki/wxbot/raw/changes/2026-10-31-model-access-switch.md:1`。

```yaml
type: change
title: 配置页接入方式下拉与模型字段随选择变化
pages:
- modules/models
- modules/dashboard
- modules/web
- modules/butler
- symbols/local-model-backend
```
### 配置页接入方式下拉与模型字段随选择变化

#### 目标与背景

上一轮 [raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373) 把运行时统一到 `wxbot → Butler → 所选模型`，但管理台页面没跟上：CLI 安装向导已支持 DeepSeek 和自定义 API，页面下拉里没有这两个值；`model_stream_view.LABELS` 与 `WorkflowView.vue` 的 deepseek/custom 标签永远走不到；切到 API 直调后 `[model].url` 和 `[model].model` 全空且没有任何提示。本次把「接入方式」收敛成页面上的一个入口，并让连接字段随选择变化。

约定沿用并写实：`[agent].provider` 是运行协议，`[model].provider` 是接入方式（产品身份），`[model].backend` 是自定义 API 的协议。页面只维护接入方式，另外两个由服务端推导，避免同一件事在两个下拉里各填一半。

#### 文件与代码位置

- `src/dashboard/config_schema.py`：`ACCESS_PROVIDERS`(10 种)、`ACCESS_LABELS`、`ACCESS_PROTOCOLS`、`ACCESS_NOTE`、`ACCESS_HINTS`、`access_provider()`、`access_fields()`；`row_metadata()` 为 `model.provider`/`model.backend`/`agent.provider` 补中文标签；`choices()` 增加两行；`validate_value()` 分开校验接入方式与协议。
- `src/dashboard/config_view.py`：`BT_DEFAULTS['model']` 补 `provider` 和 `backend` 两个键；行内按接入方式补 `placeholder`/`note`/`choice_labels`/`applicable`；响应增加 `model_access`。
- `src/dashboard/config_editor.py`：`_access_changes()` 把接入方式展开成 `[agent].provider` 与 `[model].backend`；Codex 用 `op:default` 删除多余协议字段。
- `src/butler/backends/compatible.py`：`PRODUCT_ENDPOINTS`、`self.identity`；空 url/model 也回退默认值；`scope()` 与 `emit('backend')` 使用接入方式。
- `src/butler/backends/models.py`、`src/butler/config.py`（`model_identity`）、`src/butler/agent/core.py`：模型来源上报用接入方式。
- `web/src/views/ConfigurationView.vue`：`draftRaw()`、`backendName`、`applicable()`、`categoryOf()`、`choicesOf()`、`fieldOf()`；`model.provider` 豁免兼容降级，避免选完 Codex 就切不回来。
- `web/src/components/ConfigField.vue`：显示 `field.note`，文本/数字输入带占位提示。
- `web/scripts/smoke.mjs`：配置页假数据补接入方式行与 `model_access`，下拉定位改为按 `deepseek` 选项识别。

#### 接口与字段

`GET /api/configuration` 的响应新增 `model_access`：

```
model_access = { current: <接入方式>, fields: {<接入方式>: [字段名…]}, notes: {<接入方式>: <说明>} }
```

`fields` 与 `notes` 覆盖全部 10 种接入方式，页面不维护第二份映射表。请求体仍是原有的 `source/version/changes/acknowledge`；`changes` 里出现 `model.provider` 或 `model.backend` 时由服务端展开，客户端不额外传协议。

#### 数据库与迁移

不涉及。无业务表结构变更、无数据迁移、无新增定时任务。旧配置只有 `[agent].provider` 时按协议名回退接入方式，不需要重写文件；用户下次保存时才落盘。

#### 前端消费点

`ConfigurationView.vue` 用 `draftRaw('butler.model.provider')` 优先、`model_access.current` 兜底决定当前接入方式，草稿一改字段就跟着变。`agent.provider` 收进「高级配置」避免两个下拉并存，`model.provider` 不参与兼容降级判断。字段占位提示只作展示，留空由运行时默认值兜底，不写入配置文件。

#### 测试与异步任务

`pytest tests/dashboard tests/butler tests/unit/codex` 共 736 项通过。`npm.cmd --prefix web run build` 与 `npm.cmd --prefix web run smoke` 通过。Hallmark `sloplint.mjs --scope app --render` 在隔离假数据预览上渲染，0 FAIL、2 REFLEX、1 WARN，均为既有壳层条目（详见 [model-switch-verification](model-backends.md#doc-c5a09700a83870)）。全程未发送真实微信消息、未调用真实模型、未重启任何服务。

#### 风险与回滚

接入方式与协议由服务端同时写入，手动只改一个字段仍会出现两者不一致，页面因此把它移入高级配置并标注用途。空地址按产品身份回退默认端点，若新增产品未登记 `PRODUCT_ENDPOINTS` 仍会落到协议默认地址，需同步补表。回滚需同时恢复 `config_schema`/`config_view`/`config_editor` 与前端源码，并重新构建 `web/dist`；已保存的 `[model].provider` 值在旧代码下会被当成未知协议忽略。
<!-- end-migrated-part: doc-954a7ea1e7487b -->

<a id="doc-85f41883967373"></a>

### 统一 Butler 模型链路与随时切换

来源：`llm wiki/wxbot/raw/changes/2026-10-31-switchable-models.md:1`。

```yaml
type: change
title: 统一 Butler 模型链路与随时切换
pages:
- apis/butler-handle
- apis/butler-handle-stream
- concepts/message-pipeline
- modules/butler
- modules/models
- modules/runtime
- modules/web
- modules/wiki
- modules/wxbot
- symbols/butler-handle
- symbols/butler-processor
- symbols/butler-result
- symbols/local-model-backend
- symbols/reloadable-backend
```
### 统一 Butler 模型链路与随时切换

#### 目标与背景

用户要求 wxbot→Butler→Codex/Hermes/Cursor/API+Key/其它智能体，页面随选择变化，模型运行中可切换。影响与设计见 [impacts/2026-10-31-switchable-models](model-backends.md#doc-7e58558178e006)。

#### 文件与代码位置

后端工厂、compatible.py/models.py、config.py；runtime/model_switch.py/model_migration.py/upgrade.py；agent/core.py/server.py/heartbeat.py；wxbot/main.py；dashboard 的 config_schema/view/editor、model_stream_view、api/support/jobs；ConfigurationView.vue、smoke 及 web/dist。准确位置见本记录 pages 所列词条的 sources。

#### 接口与字段

Butler 处理消息完整回复契约保持，模型选择移到 [agent].provider/[model]/[codex]，runtime 追加实际模型、配置模型、重载错误和在途代际状态。原生工具只通过服务签发身份授权，模型 Key 不授予本地权限。

#### 数据库与迁移

无业务表结构变更。通用远端会话仅保存不透明标识；联系人、记忆和提醒继续由 Butler 持有。旧 direct 配置显式迁移、私有备份并修改本机链路，不自动处理真实运行配置。已有工作树安装向导的统一链路改动予以保留并验证。

#### 前端消费点

配置页按草稿 provider 显示适用字段，保持/替换/清空密钥原值不回传；模型字段热生效、非模型字段提示手动重启。保留 Vue 壳、主题及用户已有联系人 UI 工作；重新构建 dist 并运行 smoke。

#### 测试与异步任务

临时 fake 后端覆盖协议、工具授权、完整结果、身份隔离、并发代际和显式迁移；配置和前端假数据验证见 [model-switch-verification](model-backends.md#doc-c5a09700a83870)。不发送真实微信，不调用真实模型，不重启业务进程。

#### 风险与回滚

这次代码首次加载需使用者手动重启相关进程，之后模型参数才由新代码热切换。失败配置不静默回旧模型；已执行工具而最终回答失败不可重放。未承诺跨模型远端会话连续。回滚代码需同时恢复兼容配置；模型迁移原配置备份只留本机，避免泄漏。旧 Hermes 远端业务模式仍是兼容入口，不自动转换既有业务身份。
<!-- end-migrated-part: doc-85f41883967373 -->

<a id="doc-60c1969bb5f6f6"></a>

### 修改记录

来源：`llm wiki/wxbot/raw/changes/2026-11-01-model-error-contract.md:1`。

```yaml
type: change
title: 模型失败契约补齐为概念词条
pages: [concepts/model-error-contract, concepts/delivery-state, modules/models]
```
### 修改记录

#### 目标与背景

`coverage.md` 的「待扩展」长期列着「全部模型后端的错误/重试契约」未建档。实际排查线上报错时，这条链路横跨 Butler 后端、SSE 事件、wxbot 处理适配和队列四层，只看单个模块词条拼不出来，只能反复读源码。本次把跨层契约收敛成 [concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)，并更新覆盖清单。

本次只补文档，不改代码。上一轮 `raw/changes/2026-11-01-model-request-error-visibility` 已把 HTTP 状态码加进错误消息，本词条按修改后的现状叙述。

#### 文件与代码位置

无源码改动。核对并作为事实来源的位置：

- `src/butler/agent/hermes.py:36` — `HermesError`，字段 `status`/`detail`，无 `retry_safe` 类属性。
- `src/butler/backends/compatible.py:112` — `_error_detail`，失败原因只保留类型名与状态码。
- `src/butler/backends/compatible.py:149` — 失败包装成 `HermesError` 的唯一点。
- `src/butler/backends/models.py:72` — 内层 `HermesError` 直通，不再二次包装。
- `src/butler/backends/codex.py:349` — `retry_safe=not submitted`，按是否已提交判定。
- `src/butler/runtime/model_switch.py:21` — `ModelConfigurationError.retry_safe = True`。
- `src/butler/agent/core.py:363` — `except HermesError` 转成 `reply_complete=False` 的 `Result`。
- `src/butler/agent/core.py:249` — SSE `error` 事件 `code='incomplete_result'`。
- `src/butler/server.py:354` — 未捕获异常兜底事件恒为 `retry_safe=False`。
- `src/wxbot/processor/butler.py:99` — SSE `error` 事件转成 `ValueError`；`:137` 从 `meta` 取 `retry_safe`。
- `src/wxbot/queue_worker.py:174` — 逐批次读取 `retry_safe` 后调 `fail_batch`。
- `src/wxbot/queue_store.py:384` — `fail_batch` 写 `model_retryable`/`model_uncertain`。
- `src/wxbot/model_recovery.py:2` — `MODEL_MAX_ATTEMPTS=3`，重试间隔 5/15 秒。
- `src/wxbot/queue_store.py:409` — 放弃时的用户可见原因文案。

#### 接口与字段

无新增或变更字段。词条只登记既有语义：

- SSE `error` 事件字段 `code`/`message`/`retry_safe`。
- `Result.meta` 字段 `error`/`status`/`reply_complete`/`retry_safe`。
- `batches` 表 `error`/`attempts` 与 `delivery_events.action` 的 `model_retryable`/`model_uncertain`/`model_retry`/`model_abandoned`。
- `queue.failure_discard_seconds` 配置项，默认 180 秒，范围 1–86400（`src/wxbot/config.py:53`）。

#### 数据库与迁移

不涉及。只读既有表结构与事件动作，不新增列、不写迁移。

#### 前端消费点

不涉及。管理台通过既有只读投影展示失败倒计时与动作，未改前端代码，也未新增接口。

#### 测试与异步任务

无新增测试。词条引用的本地用例（不入 Git）：`test_backend_adapters.py`、`test_model_switch_runtime.py`、`test_model_recovery.py`、`test_transport.py`、`test_pipeline.py`。队列侧异步任务为后台维护线程 `_maintain`，每 0.2 秒调用一次 `recover_model_failures`。

#### 风险与回滚

风险：词条把四层状态语义写在一起，若后续只改其中一层而未更新本页，会产生过期导航。缓解：词条每条事实都带 `path:line` 与锚点，`lint` 可检出漂移。

回滚：删除 `concepts/model-error-contract.md` 与 `raw/changes/2026-11-01-model-error-contract.md`，还原 `coverage.md` 的「待扩展」条目，重新 `ingest` + `lint`。本记录不影响运行时代码。
<!-- end-migrated-part: doc-60c1969bb5f6f6 -->

<a id="doc-507fd880895f6c"></a>

### 模型请求失败保留脱敏状态码

来源：`llm wiki/wxbot/raw/changes/2026-11-01-model-request-error-visibility.md:1`。

```yaml
type: change
title: 模型请求失败保留脱敏状态码
pages: [symbols/local-model-backend, modules/models]
```
### 模型请求失败保留脱敏状态码

#### 目标与背景

切换接入方式为 API + Key 后，用户只看到 `openai model request failed (HTTPError)`，无法判断是密钥、地址还是模型名的问题。原实现把任何异常压成类型名，故意丢弃状态码；同时存在两层包装：`LocalModelBackend.chat` 会再包一次内层 `HermesError`，把真实原因替换成 `HermesError`。本次让失败原因带上 HTTP 状态码与一句本地提示，仍不暴露地址、密钥和远端响应正文。

#### 文件与代码位置

- `src/butler/backends/compatible.py:36` — 新增 `_STATUS_HINTS`，状态码到本地排查提示的映射。
- `src/butler/backends/compatible.py:112` — 新增 `CompatibleBackend._error_detail`，只读取异常的 `response.status_code`。
- `src/butler/backends/compatible.py:153` — `chat` 的失败分支改用 `_error_detail` 组装 `HermesError`，并写入 `last_error`。
- `src/butler/backends/models.py:72` — 新增 `except HermesError` 直通分支：内层已带脱敏原因，不再二次包装，并显式设 `retry_safe=False`。
- `src/butler/backends/models.py:79` — 非 `HermesError` 分支同样使用 `_error_detail`。
- `tests/butler/test_backend_adapters.py` — 新增 HTTP 状态码可见性与不泄露地址/密钥的用例，以及原生工具路径的状态码用例。

#### 接口与字段

错误消息格式由 `{provider} model request failed ({类型名})` 变为 `{provider} model request failed ({类型名} {状态码}：{本地提示})`，非 HTTP 失败仍是纯类型名。`HermesError.status` 未改，仍是 `0`；状态码只出现在消息文本中。该文本经 `Result.meta['error']` 进入 SSE `error` 事件与 flow 日志，属既有字段，无新增字段。

#### 数据库与迁移

不涉及：没有表结构或字段变化，也没有迁移脚本。

#### 前端消费点

不涉及：管理台只展示既有 error 文本，未改组件、契约或 smoke 假数据。

#### 测试与异步任务

`tests/butler/test_backend_adapters.py` 覆盖 401/404/400 的提示文本、密钥与地址不出现在错误里、`last_error` 取值，以及 `LocalModelBackend` 不再返回 `(HermesError)`。同目录的 model switch、transport、pipeline 用例回归通过。无异步任务或定时任务变化。

#### 风险与回滚

提示文本会出现在日志与看板，长度略有增加，不含地址或凭据。若远端返回 5xx，仅显示状态码而不显示正文，排障仍需服务端日志。回滚方式是删除 `_error_detail` 与 `_STATUS_HINTS`，恢复为 `type(exc).__name__`，并移除 `models.py` 的 `except HermesError` 直通分支。
<!-- end-migrated-part: doc-507fd880895f6c -->
