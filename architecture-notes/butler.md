# Butler

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### Butler

负责身份、权限、会话和角色编排。接收队列工作器的请求，调用配置的模型后端并返回回复。

## 使用说明

- [wxbot / Butler / 模块与文件职责 / src/butler —— 编排层](#doc-1802b32aa1f822) · `README.md`
- [wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / 根目录（高频导入，留在根）](#doc-59e3b3420d609f) · `README.md`
- [wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / agent/ —— 决策与执行](#doc-ec452653482b80) · `README.md`
- [wxbot / Butler / 接口与协议](#doc-f0447a1ef5f389) · `README.md`
- [wxbot / Butler / 接口与协议 / Butler HTTP](#doc-28e203f082f6ba) · `README.md`

<a id="doc-1802b32aa1f822"></a>

### wxbot / Butler / 模块与文件职责 / src/butler —— 编排层

来源：`README.md:163`。

##### src/butler —— 编排层
<!-- end-migrated-part: doc-1802b32aa1f822 -->

<a id="doc-59e3b3420d609f"></a>

### wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / 根目录（高频导入，留在根）

来源：`README.md:165`。

###### 根目录（高频导入，留在根）

| 文件 | 职责 |
|---|---|
| `butler/__main__.py` | `python -m butler` 命令行入口：init/setup/migrate/contacts-*/doctor/login/serve/start |
| `butler/config.py` | 配置：一个 TOML 读进来，其余模块只认 `Config` 对象；默认配置路径硬编码在这里 |
| `butler/defaults.py` | 不含凭据的安装默认值，每次调用返回独立对象 |
| `butler/runtime_config.py` | 把结构化覆盖编码成 TOML，不做 shell 插值 |
| `butler/business.py` | 与模型后端无关的业务状态；一个事务一条连接 |
| `butler/server.py` | Butler HTTP 接口（stdlib，无第三方依赖）：鉴权、路由、状态码 |
<!-- end-migrated-part: doc-59e3b3420d609f -->

<a id="doc-ec452653482b80"></a>

### wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / agent/ —— 决策与执行

来源：`README.md:176`。

###### agent/ —— 决策与执行

| 文件 | 职责 |
|---|---|
| `agent/core.py` | 主流程：认领补发 → 调模型 → 解析行动 → 组装回复 → 出站推送 |
| `agent/router.py` | 决策前半：进入模型之前的规则，和出来之后的行动标记解析 |
| `agent/skills.py` | 决策后半：模型能调哪些 skill 的白名单与执行器；`HERMES_HINT` 是行动协议提示 |
| `agent/hermes.py` | Hermes 客户端：管家与 Hermes（模型 + skill 运行时）之间唯一的一层 |
| `agent/hermes_stream.py` | 读 Hermes 进度事件，同时缓存一份完整回复交给 wxbot |
| `agent/reply.py` | 把最终回复切成句：不切断 URL、代码块和受保护的 token |
| `agent/skill_policy.py` | 可按联系人热加载的角色／skill／心跳策略 |
| `agent/catalogue.py` | 可移植、纯数据的 skill 目录；skill 不能自己选择权限 |
| `agent/tools.py` | 服务端签发的身份能力与唯一的业务工具边界 |
<!-- end-migrated-part: doc-ec452653482b80 -->

<a id="doc-f0447a1ef5f389"></a>

### wxbot / Butler / 接口与协议

来源：`README.md:546`。

#### 接口与协议
<!-- end-migrated-part: doc-f0447a1ef5f389 -->

<a id="doc-28e203f082f6ba"></a>

### wxbot / Butler / 接口与协议 / Butler HTTP

来源：`README.md:548`。

##### Butler HTTP

全部要求 `Authorization: Bearer <token>`，默认只绑 loopback。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 探活 |
| GET | `/v1/catalogue` | 行动 skill 目录 |
| POST | `/v1/handle` | 处理一条消息，返回完整回复与 `reply_parts` |
| POST | `/v1/handle-stream` | 同上，附带流式增量 |
| POST | `/v1/reset` | 轮换会话 id（`/new`、`/重置`） |
| POST | `/v1/push` | 主动推送（不调模型、不改会话） |
| POST | `/v1/push/bundle` | 图文组合投递 |
| POST/GET | `/v1/media`、`/v1/media/<id>` | 媒体登记与取回（只认服务端签发的不透明 ID） |
| GET | `/v1/runtime` | 运行时状态 |
| GET/POST | `/v1/knowledge/extract` | 自动提炼的开关与进度；POST 立即跑一轮（202，正在跑时 409） |
| POST | `/v1/knowledge/facts/delete` | 确认并删除单条事实，保留原文与提炼游标 |
| GET/POST | `/v1/users`、`/v1/users/observe`、`/v1/users/audit` | 用户目录、身份观测与审计 |
| GET | `/v1/skills` | 技能目录（服务端读 Hermes） |
| POST | `/v1/jobs/delete` | 删除提醒任务 |
| POST | `/v1/group/archive` | 群归档 |
| POST | `/v1/heartbeat/trigger` | 立即触发心跳 |
| POST | `/v1/telegram/inbox` | Telegram 入库 |
| POST | `/v1/telegram-relay/authorize`、`/v1/telegram-relay/resolve` | 中继授权快照与核对 |
| POST | `/mcp` | 插件用 MCP 网关（无状态 Streamable HTTP） |

- 调用 Hermes 时同时传 `X-Hermes-Session-Key`（长期身份与知识库归属）与
  `X-Hermes-Session-Id`（同一段对话连续性）；只传前者会每轮派生新会话。
- 模型行动标记 `<<butler:action {"skill":"...","args":{...}}>>` 由 `agent/router.py`
  去掉并交 `agent/skills.py` 白名单执行；未知 skill 失败留痕。`<<butler:silent>>` 表示不回复。
- 每条消息开始先认领补发队列再调模型；模型失败或静默时仍要送出已认领的内容。
- 主动推送不改会话：`type=1` 指定联系人；`type=2` 按 `messageType` 从分组 JSON 逐人发送，
  每次推送重新读取。
<!-- end-migrated-part: doc-28e203f082f6ba -->

## 技术资料

- [POST /v1/handle-stream](#doc-5135f5350303bc) · `llm wiki/wxbot/apis/butler-handle-stream.md`
- [POST /v1/handle](#doc-4f70359e7ae440) · `llm wiki/wxbot/apis/butler-handle.md`
- [Butler 编排层](#doc-38393df7a7b4da) · `llm wiki/wxbot/modules/butler.md`
- [Butler.handle](#doc-eba67ca6f97d80) · `llm wiki/wxbot/symbols/butler-handle.md`
- [Result.as_dict](#doc-a9181bbf2979fd) · `llm wiki/wxbot/symbols/butler-result.md`

<a id="doc-5135f5350303bc"></a>

### POST /v1/handle-stream

来源：`llm wiki/wxbot/apis/butler-handle-stream.md:1`。

```yaml
type: api
module: butler
summary: SSE 增量观察与最终 result，断流不能当完整结果
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/server.py
  line: 413
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
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
```
### POST /v1/handle-stream

#### 请求和实现

所属 [modules/butler](butler.md#doc-38393df7a7b4da)。鉴权、请求字段、输入校验同 [apis/butler-handle](butler.md#doc-4f70359e7ae440)；实现仍进入 [symbols/butler-handle](butler.md#doc-eba67ca6f97d80)。返回 `text/event-stream; charset=utf-8`，`Cache-Control: no-store`，连接关闭。

#### 响应契约

每个 SSE 帧是 `data: <JSON>` 加空行；公开事件按 type 分派。`answer_delta` 的 text 只有 `sendable is true` 时进入可发送前缀。`error` 带 code/message/retry_safe，HTTP 已开始后错误也可能是 200 下的 error 帧。

最终 `type: result` 的 result 字段与 [symbols/butler-result](butler.md#doc-a9181bbf2979fd) 的 JSON 相同，必须经过 decoder 校验，而且最终 reply 必须以已发出前缀开头。观察到 complete 不能替代最终 result；在 result 前断流为失败。

#### 消费与影响

[symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24) 在 on_event 存在时选择此路径；[symbols/model-worker](queue-worker.md#doc-0183b6974519f0) 根据模式持久化事件/可发送增量。涉及 [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a) / [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf) 和 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)；浏览器另读管理台的 workflow-stream，不直接连接这个 Butler SSE。

#### 测试与风险

本地 tests/unit/model_stream/test_model_stream_transport.py / test_model_stream_pipeline.py。修改最终事件、错误或前缀校验时，必须验证断流、重复/不完整结果及禁止未知结果重放。

#### 代码依据

- `src/butler/server.py:413` — `streaming=self.path=='/v1/handle-stream'`
- `src/wxbot/processor/butler.py:89` — `if kind=='result':`
- `src/wxbot/processor/butler.py:106` — `if data is None:raise ValueError('Butler stream disconnected before result')`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

#### 模型配置错误

在模型提交前的配置错误使用 code=model_configuration、retry_safe=True；wxbot 仅在尚无 backend/tool/answer_delta/summary_delta/complete 事件时保留安全重试标记。已提交或部分输出错误仍禁止自动重放。模型切换见 [modules/models](model-backends.md#doc-69928b2a06b8f9)。


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。

#### 本次核对

新增独立知识事实删除端点，流式消息处理契约沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

同步与流式聊天共用前台活动计数。流式模型处理期间，[symbols/resident-role](resident.md#doc-81303bd5af31f1) 暂停下一次浏览操作。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。
<!-- end-migrated-part: doc-5135f5350303bc -->

<a id="doc-4f70359e7ae440"></a>

### POST /v1/handle

来源：`llm wiki/wxbot/apis/butler-handle.md:1`。

```yaml
type: api
module: butler
summary: 同步消息处理契约，从 wxbot 批次到完整 Butler 回复
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/server.py
  line: 392
  anchor: 'if self.path in ("/v1/handle","/v1/handle-stream"):'
- path: src/butler/server.py
  line: 70
  anchor: def _authed(
- path: src/butler/agent/core.py
  line: 73
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
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
```
### POST /v1/handle

#### 方法、鉴权与实现

POST `/v1/handle`；Bearer token 经 Handler._authed 校验，无服务 token 返回 500，错误凭据 401。实现由 server.make_handler → [symbols/butler-handle](butler.md#doc-eba67ca6f97d80) → [symbols/butler-result](butler.md#doc-a9181bbf2979fd)。所属 [modules/butler](butler.md#doc-38393df7a7b4da)。

#### 请求字段

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

#### 响应字段

| 字段 | 类型/含义 |
|---|---|
| reply | string/null；最终合成文本，可静默 |
| reply_parts | string[]；按 reply_chunk_chars 切分 |
| actions | list；行动 as_dict 序列化结果 |
| meta | object；含 reply_complete，分支可有 msg_id/error/retry_safe/身份等 |

成功 HTTP 200 不等于业务完成：`meta.reply_complete == false` 被 wxbot 拒绝；msg_id 若存在须匹配请求。异常非流式返回 500。其它 meta 字段由业务分支决定，不能将所有字段标为必返。

#### 消费、表与血缘

直接调用方 [symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24)；它的 request_id → 请求 msg_id → Butler trace / meta.msg_id；源头是 [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a) 的 id。群边界来自归档返回的序号。完成回复经过 [symbols/model-worker](queue-worker.md#doc-0183b6974519f0) → [symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1) → [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)。

浏览器不直接消费此端点；展示经 [apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714) / [apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)。Butler 业务库由身份/工具等分支触及，详细表待建档，不应误记为直接写 wxbot 队列表。

#### 测试与风险

本地 tests/butler/test_transport.py、test_pipeline.py；tests/unit/model_stream/test_model_stream_transport.py。改字段同时查适配器 decoder、Result.as_dict、队列 worker；流式变体见 [apis/butler-handle-stream](butler.md#doc-5135f5350303bc)，权限见 [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。

2026-10-31 的接入方式改动只影响 `emit('backend')` 的模型来源上报，请求/响应字段与校验未变。

2026-11-01 的 L1 原文沉淀只在 `_handle_request` 内部旁路写 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)，失败只记日志：请求体、响应字段与 `meta.reply_complete` 契约均未变，handle 的调用方无需改动。

同日的拆库把 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20) 的库根从单文件 `data/knowledge.sqlite3` 改成 `data/knowledge/` 目录（一人一库 + 目录库，见 [tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)，另加 [tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)）：`_record_episode` 的入参、三态 `outcome` 与全包异常的约定未变，`Result.as_dict` 的字段也没动，所以本端点的请求/响应契约同样不变。

2026-11-01 的自动提炼批次（[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)）在 server 里新增的是 `/v1/knowledge/extract` 两条旁路路由，只把 `make_handler` 往下推了几行：`/v1/handle` 的入参校验、响应字段与 `meta.reply_complete` 约定一条未动。

#### 代码依据

- `src/butler/server.py:392` — `if self.path in ("/v1/handle","/v1/handle-stream"):`
- `src/butler/server.py:70` — `def _authed(`
- `src/butler/agent/core.py:73` — `def as_dict(`
- `src/wxbot/processor/butler.py:60` — `def handle_reply(`
- `src/wxbot/processor/butler.py:129` — `def _decode_reply(`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-10-31-model-access-switch-core-emit](model-backends.md#doc-6510cadeadeb37)

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。

#### 本次核对

入站处理补建窗口是 Butler 内部副作用，请求字段、结果和群成员元数据契约继续沿用。 来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 本次核对

新增独立知识事实删除端点，同步消息处理契约沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

启用常驻角色时，有效聊天处理期间增加前台活动计数。该信号供 [symbols/resident-role](resident.md#doc-81303bd5af31f1) 让路，原有鉴权、请求和响应字段保持原契约。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。
<!-- end-migrated-part: doc-4f70359e7ae440 -->

<a id="doc-38393df7a7b4da"></a>

### Butler 编排层

来源：`llm wiki/wxbot/modules/butler.md:1`。

```yaml
type: module
module: butler
summary: 身份、权限、模型编排和业务工具的服务边界
coverage: overview
last_verified: '2026-11-05'
sources:
- path: src/butler/server.py
  line: 52
  anchor: def make_handler(
- path: src/butler/agent/core.py
  line: 79
  anchor: 'class Butler:'
- path: src/butler/agent/tools.py
  line: 30
  anchor: 'class ToolService:'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
depends_on:
- modules/common
```
### Butler 编排层

#### 职责与范围

`src/butler/` 持有业务编排；HTTP 从 server.make_handler 进入 agent.core.Butler，工具执行以 ToolService 验证的服务身份为边界。入口 `python -m butler.server`；操作细节见根 README。

#### 关键入口与依赖

消息 API：[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc) → [symbols/butler-handle](butler.md#doc-eba67ca6f97d80) → [symbols/butler-result](butler.md#doc-a9181bbf2979fd)。模型后端位于 `backends/`，调用共享接口；业务不能塞进 wxbot UI 层。

知识库管理接口：`GET /v1/knowledge/extract`（`src/butler/server.py:142`）只回 [symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) 的 `status()`；`POST /v1/knowledge/extract`（`:322`）校验 `owner`/`batch`/`dry_run` 后交给 `trigger()` 后台跑，鉴权后只回 202。调度器本身在 `serve()` 里构造与启停（`:477`、`:488`、`:496`），不占 HTTP 线程。

子模块：[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/delivery](butler-functions.md#doc-f61f55fe09c5e9)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[modules/telegram](butler-functions.md#doc-8b0e2206d40805)；共享基础能力 [modules/common](wxbot.md#doc-dd2bd595b3d8f8)。运行时角色/工具定义见 [modules/plugin](resident-skills.md#doc-709338d3e083eb)，不是开发知识图谱的权限来源。

#### 数据和消费方

业务 SQLite 由 BusinessStore 持有；本轮未完整建档其表。HTTP 消费方是 [modules/wxbot](wxbot.md#doc-8508032cbe5131)，管理接口经 [modules/dashboard](dashboard.md#doc-bb47c9474691fe) 代理。微信队列属于 wxbot，不属于 Butler 业务库。主链路见 [concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)，权限边界见 [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。

另有一套旁路库：[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)（`data/knowledge/p-<slug>/episodes.sqlite3`）只存每轮对话的用户原文与回复，[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)（同目录 `facts.sqlite3`）存从原文提炼的长期事实，两者由 [tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)（`data/knowledge/index.sqlite3`）当目录。**一人一库**：任何一个联系人的数据损坏或整体清空都不牵连别人；原文按保留期过期，事实不跟着消失。它们和 BusinessStore 分库，因为 business 库每次启动整库备份，塞入聊天原文会让备份体积失控。原文写入点只在 `_handle_request`，失败只记日志。

保留期清理与事实提炼现在由 `serve()` 里的常驻调度器 [symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) 驱动（`knowledge.auto_extract` 与 `knowledge.auto_prune` 两个开关，默认关），提炼仍只经 [symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774) 这一条写路径；`python -m butler knowledge-extract|knowledge-prune|knowledge-migrate` 保留为人工补跑与旧库拆分入口，其中提炼要先拿同一把跨进程锁。

#### 代码依据

- `src/butler/server.py:52` — `def make_handler(`
- `src/butler/agent/core.py:79` — `class Butler:`
- `src/butler/agent/tools.py:30` — `class ToolService:`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

#### 可切换后端

统一后端见 [modules/models](model-backends.md#doc-69928b2a06b8f9)；本地业务按 uses_local_runtime 初始化，适用于 Codex 和通用模型。旧 Hermes 空 model 配置保留历史远端业务兼容路径。

模型来源上报用 `Config.model_identity`：Codex 固定报 codex，其它按 `[model].provider` 产品名、回退协议名。因此流转日志和模型面板显示 deepseek 而不再是 openai。


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-10-31-model-access-switch](model-backends.md#doc-954a7ea1e7487b)

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。

#### 本次核对

统一联系人窗口补建由 Butler 管理，wxbot 和管理台分别沿用收件与查询接口。 来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 本次核对

Butler 通过鉴权端点独占写入单条事实删除，见 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

启用时，`serve()` 构造并启动 [symbols/resident-role](resident.md#doc-81303bd5af31f1)，服务退出时先停止常驻活动。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。
<!-- end-migrated-part: doc-38393df7a7b4da -->

<a id="doc-eba67ca6f97d80"></a>

### Butler.handle

来源：`llm wiki/wxbot/symbols/butler-handle.md:1`。

```yaml
type: symbol
module: butler
summary: 单轮身份解析、会话互斥、补发优先与最终合成
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/agent/core.py
  line: 219
  anchor: 'def handle(self, contact_name:'
- path: src/butler/agent/core.py
  line: 275
  anchor: def _handle_request(
- path: src/butler/agent/core.py
  line: 339
  anchor: 'def _handle(self, c:'
- path: src/butler/server.py
  line: 426
  anchor: res = butler.handle(contact, text,
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
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
calls:
- symbols/butler-result
called_by: []
```
### Butler.handle

#### 签名与职责

`handle(contact_name, text, msg_id=None, channel_type='dm', member_key='', member_name='', avatar='', group_context_seq=0, on_event=None)`。所属 [modules/butler](butler.md#doc-38393df7a7b4da)；返回 [symbols/butler-result](butler.md#doc-a9181bbf2979fd)。

#### 调用关系

由 server.make_handler 中 [apis/butler-handle](butler.md#doc-4f70359e7ae440) / [apis/butler-handle-stream](butler.md#doc-5135f5350303bc) 调用（其它调用方不在本批穷举）。内部 `_handle_request` 解析联系人并绑定 request trace，在 session 锁下进入 `_handle` 或指定转发路由；`_handle` 先 take_and_claim 补发，再做规则路由、调用后端、行动执行和最终合成。

#### 副作用与风险

写 flow/trace；可能读取记忆、归档群上下文、执行经授权工具并认领补发；具体业务表待建档。msg_id 回填 meta。流式 sendable 前缀受最终合成约束，群身份/补发时不可随意提早发送。关联 [concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37) 和 [symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24)。

`_handle_request` 还旁路写一条 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20) 原文：成功、无回复和异常各对应一个 outcome。写入在 `_record_episode` 内部全包异常，失败只落流水日志，不影响返回值和异常上抛。

拆库（同日的 knowledge-sharding）只把落盘位置从 `data/knowledge.sqlite3` 换成 `data/knowledge/` 下按 owner 分库（目录见 [tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)），三态 outcome 与全包异常的约定未变。

#### 测试

本地 tests/butler/test_pipeline.py、test_butler_concurrency.py、tests/unit/model_stream/test_model_stream_pipeline.py。

正常入站处理完成身份解析后，调用 [modules/identity](identity-tools.md#doc-5e308350a1ba25) 补建待补充窗口；专用 HTTP 转发继续绕过身份流程。来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 代码依据

- `src/butler/agent/core.py:219` — `def handle(self, contact_name:`
- `src/butler/agent/core.py:275` — `def _handle_request(`
- `src/butler/agent/core.py:339` — `def _handle(self, c:`
- `src/butler/server.py:426` — `res = butler.handle(contact, text,`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

#### 请求级模型一致性

handle 在 [symbols/reloadable-backend](model-backends.md#doc-85aba8d0cc88bd) 的 request 上下文中固定后端，直到最终结果/流式包和群游标处理结束。配置错误在未发送前明确失败，不自动落回另一个模型。

`emit('backend')` 的 provider 改用 `Config.model_identity`，按接入方式（`[model].provider`）上报真实模型来源；未填时仍回退协议名。


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-10-31-model-access-switch-core-emit](model-backends.md#doc-6510cadeadeb37)

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。

#### 本次核对

事实删除由独立服务端点处理，入站主流程沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

同步与 SSE 入口均在调用处理器期间标记前台忙碌，供 [symbols/resident-role](resident.md#doc-81303bd5af31f1) 调度使用。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。
<!-- end-migrated-part: doc-eba67ca6f97d80 -->

<a id="doc-a9181bbf2979fd"></a>

### Result.as_dict

来源：`llm wiki/wxbot/symbols/butler-result.md:1`。

```yaml
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
  line: 442
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
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
calls: []
called_by:
- symbols/butler-handle
```
### Result.as_dict

#### 签名、职责与关系

`Result(reply: str | None, actions: list, meta: dict)`；`as_dict(*, reply_chunk_chars=500) -> dict`。结构由 [symbols/butler-handle](butler.md#doc-eba67ca6f97d80) 返回，再由 HTTP handler 序列化为 [apis/butler-handle](butler.md#doc-4f70359e7ae440) 的响应/[apis/butler-handle-stream](butler.md#doc-5135f5350303bc) 的最终 result。这里 calls 元信息的 handle → result 表示返回对象构造关系，不表示 handle 直接调用 as_dict。

#### 字段与副作用

reply 原样；actions 调各项 as_dict；reply_parts 经 split_reply 切分；meta 使用默认 reply_complete=True 再被业务 meta 覆盖，因此可能显式 False。此方法本身无数据库或网络副作用。L1 原文沉淀由 [symbols/butler-handle](butler.md#doc-eba67ca6f97d80) 旁路写入 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)，不经过 Result，所以本 DTO 字段与语义不受影响。

#### 消费与风险

消费者 [symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24) 会拒绝不完整结果、非法 reply/meta、请求 ID 不一致。改 DTO 要同时检查 wxbot Reply 的分句约束和 [symbols/model-worker](queue-worker.md#doc-0183b6974519f0)，不能仅看 HTTP 200。

2026-10-31 的接入方式改动只动了 core.py 里 `emit('backend')` 的模型来源上报（改用 `Config.model_identity`），Reply/actions/reply_parts/meta 的字段与语义未变。

同日的拆库（knowledge-sharding）同样不经过本 DTO：它只改了 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20) 的落盘位置与目录结构，`Result` 的字段与 `as_dict` 的序列化未变。

#### 代码依据

- `src/butler/agent/core.py:68` — `class Result:`
- `src/butler/agent/core.py:73` — `def as_dict(`
- `src/butler/server.py:442` — `result=res.as_dict(reply_chunk_chars=cfg.reply_chunk_chars)`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-10-31-model-access-switch-core-emit](model-backends.md#doc-6510cadeadeb37)

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。

#### 本次核对

补建窗口属于入站业务库副作用，公开 Result 字段沿用。 来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 本次核对

独立事实删除端点不使用模型 Result；Result 契约沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

已对照当前共享源码复核本词条的接口或调用位置。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。
<!-- end-migrated-part: doc-a9181bbf2979fd -->
