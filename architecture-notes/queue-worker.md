# 队列工作器

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 队列工作器

领取收件批次，调用 Butler 并将回复写入发件队列。

## 使用说明

- [wxbot / Butler / 模块与文件职责 / src/wxbot —— 微信 UI 收发层 / processor/ —— 消息处理器](#doc-271abea1efa9ae) · `README.md`

<a id="doc-271abea1efa9ae"></a>

### wxbot / Butler / 模块与文件职责 / src/wxbot —— 微信 UI 收发层 / processor/ —— 消息处理器

来源：`README.md:395`。

###### processor/ —— 消息处理器

| 文件 | 职责 |
|---|---|
| `processor/base.py` | 处理器接口：收到一条消息返回要回复的文字（`None` 表示不回） |
| `processor/router.py` | 命令路由：`/` 开头的走命令，其余交给模型；新命令在 `COMMANDS` 里加一项 |
| `processor/butler.py` | Butler 处理器：把消息转给本地 Butler（`POST /v1/handle`） |
| `processor/openai_compat.py` | 非流式、只接受完整结果的 OpenAI 兼容对话传输 |
| `processor/responses.py` | OpenAI Responses JSON 协议，严格校验终止状态 |
| `processor/cursor.py` | Cursor 无头适配器；聊天输入始终是数据，不当命令行选项 |
| `processor/ollama.py` | 本机 Ollama 处理器，按联系人保存在内存里的上下文 |
<!-- end-migrated-part: doc-271abea1efa9ae -->

## 技术资料

- [ButlerProcessor.handle_reply](#doc-0b0a168dc38d24) · `llm wiki/wxbot/symbols/butler-processor.md`
- [ModelWorker.process_once](#doc-0183b6974519f0) · `llm wiki/wxbot/symbols/model-worker.md`
- [SQLite batches](#doc-8e6cc338038d9a) · `llm wiki/wxbot/tables/queue-batches.md`

<a id="doc-0b0a168dc38d24"></a>

### ButlerProcessor.handle_reply

来源：`llm wiki/wxbot/symbols/butler-processor.md:1`。

```yaml
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
```
### ButlerProcessor.handle_reply

#### 签名与职责

`handle_reply(contact, text, *, request_id=None, member_key='', member_name='', avatar='', group_context_seq=None, channel_type='dm', on_event=None) -> Reply`。所属 [modules/wxbot](wxbot.md#doc-8508032cbe5131)。

#### 调用链

[symbols/model-worker](queue-worker.md#doc-0183b6974519f0) → processor.router.Router.handle_reply → 本方法 → [apis/butler-handle](butler.md#doc-4f70359e7ae440) 或 [apis/butler-handle-stream](butler.md#doc-5135f5350303bc)。`request_id` 映射 JSON msg_id；member_key 会使 channel_type 变为 group；on_event 存在时选择 SSE。

#### 校验和副作用

HTTP 网络请求、公开流事件与 trace；decoder 校验 dict/meta、reply_complete、msg_id、mention_name、reply 及分句。流式断连或前缀不符抛错，未知提交结果不能重放；非流式是否抛出取决于 raise_errors。输出进入 [symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1) 前必须完整。

#### 反向关系与测试

元信息只列通过 Router 的已核对调用链，Router 本身未单独建页。底层 [symbols/butler-handle](butler.md#doc-eba67ca6f97d80) 的变化会影响此消费者。测试 tests/unit/queue/test_processor_queue_errors.py 和 tests/unit/model_stream/test_model_stream_transport.py（本地）。

#### 代码依据

- `src/wxbot/processor/butler.py:60` — `def handle_reply(`
- `src/wxbot/processor/butler.py:129` — `def _decode_reply(`
- `src/wxbot/processor/router.py:27` — `def handle_reply(`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)
<!-- end-migrated-part: doc-0b0a168dc38d24 -->

<a id="doc-0183b6974519f0"></a>

### ModelWorker.process_once

来源：`llm wiki/wxbot/symbols/model-worker.md:1`。

```yaml
type: symbol
module: wxbot
summary: 领取批次、调用模型并保存回复，绝不访问 UI
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/wxbot/queue_worker.py
  line: 46
  anchor: def process_once(
- path: src/wxbot/queue_worker.py
  line: 152
  anchor: reply = self.router.handle_reply(
- path: src/wxbot/queue_worker.py
  line: 102
  anchor: self.store.finish_batch_parts(
- path: src/wxbot/queue_worker.py
  line: 120
  anchor: voice_media = resolve_queued_media_path(policy)
changes:
- raw/changes/2026-11-03-indextts-enqueue-media
- raw/changes/2026-11-03-feat-voice-003-model-worker-drift
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-03-feat-voice-001-anchor-refresh
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-11-05-group-auto-voice
calls:
- symbols/butler-processor
- symbols/queue-finish
called_by: []
```
### ModelWorker.process_once

#### 签名与调用方

`ModelWorker.process_once(self)` 返回是否处理一个批次；由 worker._run 循环调用。所属 [modules/wxbot](wxbot.md#doc-8508032cbe5131)。依赖 [symbols/queue-store](queue-storage.md#doc-37f6245b143a25)。

#### 调用与输出

prepare/claim_batch → Router → [symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24)（使用 Butler 模型时）→ [symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)。根据回复模式选择表情、静默或文本；事件模式可以持久化增量，只有 sendable 文本进入流式队列。

非流式完整回复在联系人投递模式不是 off 时入语音条。`outbox.media_path` 只在 `tts_provider=fixture` 时写 `fixture_wav`；`indextts` 等投递时合成的提供者留空，以便发件调用 `prepare`。无可用音色绑定则模式视为 off，只入文字。见 [concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0)、[raw/changes/2026-11-03-indextts-enqueue-media](index-tts.md#doc-29fc2d893f2889)。

#### 副作用与风险

读写 [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf) 及辅助流记录，网络发生在适配器；无 UI 操作。完整回复必须与已流出前缀一致。异常交 fail_batch，retry_safe 默认 False，未知结果不自动重放。定时维护恢复安全失败/过期投递，细节见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。

#### 测试

本地 tests/unit/queue/test_queue_worker.py、test_queue_concurrency.py、tests/unit/model_stream/test_model_stream_pipeline.py。

#### 代码依据

- `src/wxbot/queue_worker.py:46` — `def process_once(`
- `src/wxbot/queue_worker.py:152` — `reply = self.router.handle_reply(`
- `src/wxbot/queue_worker.py:102` — `self.store.finish_batch_parts(`
- `src/wxbot/queue_worker.py:120` — `voice_media = resolve_queued_media_path(policy)`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)


#### 群聊采集与自动语音复核（2026-11-05）

自动回复的 webui 默认推导、实时语音策略、流式缓冲、daemon 合成及录音前准确预设复核见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)；旧媒体包/离线提供者合同保留。自动 webui 的录音前失败终结并仅回退一次文字，不让 blocked 重试重复投递，无数据库迁移。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。
<!-- end-migrated-part: doc-0183b6974519f0 -->

<a id="doc-8e6cc338038d9a"></a>

### SQLite batches

来源：`llm wiki/wxbot/tables/queue-batches.md:1`。

```yaml
type: table
module: wxbot
summary: 模型请求批次与最终回复完整性，非发送回执
coverage: core
last_verified: '2026-11-04'
sources:
- path: src/wxbot/queue_schema.py
  line: 34
  anchor: _TABLES = (
- path: src/wxbot/queue_schema.py
  line: 84
  anchor: def initialize(
- path: src/wxbot/queue_schema.py
  line: 149
  anchor: for sql in ('CREATE INDEX
- path: src/wxbot/queue_schema.py
  line: 7
  anchor: VERSION = 10
- path: src/wxbot/queue_store.py
  line: 309
  anchor: def claim_batch(
- path: src/wxbot/queue_store.py
  line: 339
  anchor: def finish_batch_parts(
changes:
- raw/changes/2026-11-03-feat-voice-001-anchor-refresh
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-queue-batches-format
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-details-whitelist-reverify
- raw/changes/2026-11-02-mention-residue-reverify
- raw/changes/2026-11-04-index-tts-skill
```
### SQLite batches

#### 字段清单（VERSION=10 最终结构）

| 字段                          | SQLite 类型/约束/默认                   |
| --------------------------- | --------------------------------- |
| seq                         | INTEGER PRIMARY KEY AUTOINCREMENT |
| id                          | TEXT NOT NULL UNIQUE              |
| contact / text / context    | TEXT NOT NULL                     |
| member_key / member_name    | TEXT NOT NULL DEFAULT ''          |
| reply_mode                  | TEXT NOT NULL DEFAULT 'text'      |
| state                       | TEXT NOT NULL                     |
| created_at                  | REAL NOT NULL                     |
| started_at / finished_at    | REAL，可 NULL                       |
| attempts                    | INTEGER NOT NULL DEFAULT 0        |
| error                       | TEXT NOT NULL DEFAULT ''          |
| reply_text                  | TEXT，可 NULL                       |
| reply_complete / part_count | INTEGER NOT NULL DEFAULT 0        |
| avatar / reply_reason       | TEXT NOT NULL DEFAULT ''（补列）      |
| first_delivery_failure      | REAL，可 NULL（补列）                   |
| delivery_resolution         | TEXT NOT NULL DEFAULT ''（补列）      |
|                             |                                   |

#### 关系与索引

所属 [modules/wxbot](wxbot.md#doc-8508032cbe5131)；batches_state(state,seq)。[tables/queue-inbox](inbox.md#doc-6529d9966e604a).batch_id 与 [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf).batch_id 引用 id，inbox 一批多条，outbox 一批多分句。所有读写核心见 [symbols/queue-store](queue-storage.md#doc-37f6245b143a25)。

#### 血缘

prepare 合并 inbox 得 text/context/member/回复模式；claim_batch 标记 processing。[symbols/model-worker](queue-worker.md#doc-0183b6974519f0) 把 id 作为 request_id，[symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24) 映射 msg_id，Butler 回 meta.msg_id；[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714) 将其作为 request_id 关联 trace。

[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1) 保存 reply_text / reply_complete=1 / part_count，并插入 outbox；只有聚合投递状态可表示整轮结束。字段 reply_complete 属模型完整性，不能替代 outbox sent。展示也见 [apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)。

2026-11-02 复核：`queue_store.py` 的变更是扩展 `delivery_events.details` 白名单（`error_code` / `retry` / `confirm_evidence` / `ref_available`），批次字段、状态机与 `_recompute_batch` 聚合规则未变。

#### 风险与测试

失败模型请求仅 retry_safe 为真才重试；未知结果不重放，超时放行后续消息。first_delivery_failure 以整轮首次失败计算时限，见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。本地 test_queue_worker.py、test_model_recovery.py、test_reply_delivery_lifecycle.py。

#### 代码依据

- `src/wxbot/queue_schema.py:34` — `_TABLES = (`
- `src/wxbot/queue_schema.py:84` — `def initialize(`
- `src/wxbot/queue_schema.py:149` — `for sql in ('CREATE INDEX`
- `src/wxbot/queue_schema.py:7` — `VERSION = 10`
- `src/wxbot/queue_store.py:309` — `def claim_batch(`
- `src/wxbot/queue_store.py:339` — `def finish_batch_parts(`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[raw/changes/2026-10-31-queue-batches-format](queue-worker.md#doc-33b232c2a9cf1f)

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-details-whitelist-reverify](delivery-pump.md#doc-ae7b71a2b37518)

[raw/changes/2026-11-02-mention-residue-reverify](wechat-ui.md#doc-989f2003dec3a1)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。
<!-- end-migrated-part: doc-8e6cc338038d9a -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [保留 batches 词条后续表格排版](#doc-33b232c2a9cf1f) · `llm wiki/wxbot/raw/changes/2026-10-31-queue-batches-format.md`

<a id="doc-33b232c2a9cf1f"></a>

### 保留 batches 词条后续表格排版

来源：`llm wiki/wxbot/raw/changes/2026-10-31-queue-batches-format.md:1`。

```yaml
type: change
title: 保留 batches 词条后续表格排版
pages:
- tables/queue-batches
```
### 保留 batches 词条后续表格排版

#### 目标与背景

首批入库后，交付前的再次巡检发现 queue-batches.md 摘要变化。检查发现字段表格列对齐和空白行变化，事实内容未变；保留当前排版，不用初始生成内容覆盖它。此记录接续 [raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)。

#### 文件与代码位置

`llm wiki/wxbot/tables/queue-batches.md:36` 的最终结构字段表发生排版变化。核对 `src/wxbot/queue_schema.py:34`、`:84`、`:149` 及 `src/wxbot/queue_store.py:300`、`:330`，字段和来源仍一致。更新 [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a) 修改来源并重新登记快照。

#### 接口与字段

不涉及接口/DTO 变更；表格中的字段名、类型、约束和默认值未改变。

#### 数据库与迁移

不涉及数据库或迁移，只核对源码中的 schema，未读取实际数据库。

#### 前端消费点

不涉及业务前端，只保留 Obsidian Markdown 排版；不修改原有 Obsidian 设置。

#### 测试与异步任务

无新增任务或业务代码。脚本专项回归仍为 20 passed / 1 skipped；重新执行 ingest / lint / status 核对图谱闭环。验证限制见 [verification](wxbot.md#doc-951820f4d5f621)。

#### 风险与回滚

没有业务语义影响。后续对已入库词条的编辑仍会触发 page-drift，必须复核后以新记录入库，不改历史 raw 或直接改证据摘要。保留本次排版，无需业务服务重启。
<!-- end-migrated-part: doc-33b232c2a9cf1f -->
