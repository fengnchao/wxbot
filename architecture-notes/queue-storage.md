# 收发队列存储

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 收发队列存储

收件、消息批次和发件状态存放在 SQLite 中。图中的分类队列表示消息的处理分支。

当前发件共用一张 outbox，kind 为 text / voice / image / emoji。第一步没有数据库迁移。
QueueStore.claim_delivery 按会话和 seq 保证跨类型顺序，并保留失败、人工核对、包内顺序与会话轮转规则。
文件发件、reply_type 分流和持久化的 TTS 准备队列尚未实现。

## 技术资料

- [GET /api/queue](#doc-0b08697b4d4a4f) · `llm wiki/wxbot/apis/dashboard-queue.md`
- [QueueStore](#doc-37f6245b143a25) · `llm wiki/wxbot/symbols/queue-store.md`
- [SQLite outbox](#doc-6dd6d137f99cdf) · `llm wiki/wxbot/tables/queue-outbox.md`

<a id="doc-0b08697b4d4a4f"></a>

### GET /api/queue

来源：`llm wiki/wxbot/apis/dashboard-queue.md:1`。

```yaml
type: api
module: dashboard
summary: 队列分页诊断，展示状态和可用动作而不执行恢复
coverage: core
last_verified: '2026-11-06'
sources:
- path: src/dashboard/routes.py
  line: 47
  anchor: ("GET", "/api/queue", queue.read)
- path: src/dashboard/api/queue.py
  line: 10
  anchor: 'def read(ctx):'
- path: src/dashboard/queue_view.py
  line: 22
  anchor: def read(self, *, contact=
- path: src/dashboard/queue_view.py
  line: 170
  anchor: def _row(
- path: web/src/views/QueueView.vue
  line: 248
  anchor: apiGet('/api/queue?'
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-diary-web
```
### GET /api/queue

#### 请求

GET `/api/queue`；可选 contact（字符串过滤）、state（默认 all）、scope、order；limit 默认 50，视图截在 1..200；offset 默认 0 且非负；inbox_offset/batches_offset/outbox_offset/rounds_offset 单独分页，telegram_offset 默认 0。路由 → api.queue.read → QueueView.read；HTTP 访问控制属于 [modules/dashboard](dashboard.md#doc-bb47c9474691fe)。

#### 响应

`read_only: true`、database、at、status/error、contacts、counts、pages、inbox/batches/outbox、events、actions_enabled、failure_timeout_seconds；成功读取还含 rounds；处理器添加 telegram。pages 各表 total/offset/limit/has_more。missing/error 状态可能缺少正常读取的扩展字段，前端须容忍。

`_row` 投影状态、part_count/sent_parts/completed_parts、时限和允许动作。actions_enabled 仅在 schema 最新时开启，GET 本身不执行动作；写动作走独立 API 及确认头。

#### 消费与表

[modules/web](dashboard.md#doc-aeec90dfe23cd3) 的 QueueView.vue 使用 apiGet 消费；无 TypeScript DTO，实际字段消费者就在 Vue 和共用 JS 中。对应 [tables/queue-inbox](inbox.md#doc-6529d9966e604a)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)，batch_id 保持反向关联。展示与 [apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714) 是不同投影。

#### 测试与风险

本地 tests/dashboard/test_queue_actions.py、test_queue_cleanup_actions.py、test_flow_view.py 和 web/scripts/smoke.mjs。表变更需兼容旧库只读展示；不得为了 GET 成功而创建/迁移队列。生命周期见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。

2026-11-01 起陆续新增的 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6) 与队列无关：`/api/knowledge`、`/api/knowledge/facts`、`/api/knowledge/extract`、`/api/knowledge/template` 四条 GET 现在连排在 `:43`–`:46`，两条知识 POST 在 `:67`–`:68`。这些行都插在 `/api/queue` 之后，本接口仍在 `:42`；请求参数、响应字段与动作白名单一条未变。

#### 代码依据

- `src/dashboard/routes.py:42` — `("GET", "/api/queue", queue.read)`
- `src/dashboard/api/queue.py:10` — `def read(ctx):`
- `src/dashboard/queue_view.py:22` — `def read(self, *, contact=`
- `src/dashboard/queue_view.py:170` — `def _row(`
- `web/src/views/QueueView.vue:248` — `apiGet('/api/queue?'`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。

#### 本次核对

新增知识事实写端点，队列读接口沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 小潮日记接入核对

复核共享路由表，收发队列读接口与队列操作仍使用原处理器。 来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。
<!-- end-migrated-part: doc-0b08697b4d4a4f -->

<a id="doc-37f6245b143a25"></a>

### QueueStore

来源：`llm wiki/wxbot/symbols/queue-store.md:1`。

```yaml
type: symbol
module: wxbot
summary: 短事务管理收件、合批、模型状态与 UI 发件状态
coverage: core
last_verified: '2026-11-07'
sources:
- path: src/wxbot/queue_store.py
  line: 91
  anchor: class QueueStore(
- path: src/wxbot/queue_store.py
  line: 239
  anchor: def capture(
- path: src/wxbot/queue_store.py
  line: 277
  anchor: def prepare(
- path: src/wxbot/queue_store.py
  line: 585
  anchor: def claim_delivery(
- path: src/wxbot/queue_store.py
  line: 21
  anchor: FAILURE_DETAIL_FIELDS =
- path: src/wxbot/queue_store.py
  line: 605
  anchor: def record_submitted_text(self, delivery_id,
- path: src/wxbot/queue_store.py
  line: 717
  anchor: 'def recover(self, *, now=None):'
changes:
- raw/changes/2026-11-03-feat-voice-001-anchor-refresh
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-07-delivery-handlers
- raw/changes/2026-11-07-stale-regression-tests
called_by:
- symbols/delivery-pump
- symbols/delivery-handlers
```
### QueueStore

#### 职责、签名与入口

`QueueStore(path, *, access='runtime', ...)` 继承 StreamQueue / DeliveryPolicy，连接 SQLite，并按访问模式处理生命周期。运行期模式可能持锁和迁移，不能为了看板读取而直接构造运行模式实例。所属 [modules/wxbot](wxbot.md#doc-8508032cbe5131)。

#### 调用关系

MainInbox.capture 写 [tables/queue-inbox](inbox.md#doc-6529d9966e604a)；[symbols/model-worker](queue-worker.md#doc-0183b6974519f0) 的 prepare/claim_batch 处理 [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)；[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1) 写 [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)；UI delivery 使用 claim_delivery、save_baseline、confirming、finish_delivery 保存可核对结果。各方法持短事务，模型/窗口操作不在数据库事务内执行。

`forget_session` 是 `pending_sessions` 除 capture 之外唯一的删除路径，专供「未读始终读不到可采内容」的放弃场景，否则该联系人的 prepare 永远被跳过；重试与放弃规则见 [concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)。

`FAILURE_DETAIL_FIELDS` 是 `delivery_events.details` 的白名单：只接受标量键，字符串截断 256 字符。发件失败写 `error_code` / `retry`，发送确认写 `confirm_evidence` / `ref_available`，提及失败留下可认领字面草稿时写 `mention_residue`；管理台只读投影复用同一份常量。`save_baseline` 保存的是去掉快照引用的行（`ui_contract.persisted_rows`），所以引用不跨重启。见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。

#### 副作用与反向消费

SQLite 状态、队列事件和辅助流；只读消费使用 [apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f) / [apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)，不要让查询触发 QueueStore.recover。失败/过期/人工处置详见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。

#### 测试

本地 tests/unit/queue/test_queue_store.py、test_queue_migration.py、test_delivery_queue.py。

#### 代码依据

- `src/wxbot/queue_store.py:91` — `class QueueStore(`
- `src/wxbot/queue_store.py:239` — `def capture(`
- `src/wxbot/queue_store.py:277` — `def prepare(`
- `src/wxbot/queue_store.py:585` — `def claim_delivery(`
- `src/wxbot/queue_store.py:21` — `FAILURE_DETAIL_FIELDS =`
- `src/wxbot/queue_store.py:229` — `def forget_session(self, contact):`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[raw/changes/2026-10-31-group-identity-nickname](identity-tools.md#doc-f39c15a6fe0885)

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-mention-picker-gating-residue](wechat-ui.md#doc-980ea358badbe6)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 发件处理器拆分

[symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca) 保留统一 outbox 认领与 UI 所有权，按 kind 调用 [symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c)。同会话顺序仍由 claim_delivery 的 seq/未终结前项约束保证，数据字段和 HTTP 不变。

来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。


#### 实际正文登记与队列状态

record_submitted_text 只写 submitted_text 和必要的说明，不会更改任务/批次状态。常规登记仅用于 sending/confirming；user_confirmed=True 仅用于 uncertain。重启后的 uncertain/detached 允许新轮继续；活跃任务登记正文后仍阻塞。对应本地测试覆盖这两个相反状态及非法登记拒绝。

来源 [raw/changes/2026-11-07-stale-regression-tests](wxbot.md#doc-df3c99eaa835f8)。
<!-- end-migrated-part: doc-37f6245b143a25 -->

<a id="doc-6dd6d137f99cdf"></a>

### SQLite outbox

来源：`llm wiki/wxbot/tables/queue-outbox.md:1`。

```yaml
type: table
module: wxbot
summary: 逐分句发件与不确定结果审计，包含迁移新增字段
coverage: core
last_verified: '2026-11-07'
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
- path: src/wxbot/queue_schema.py
  line: 22
  anchor: OUTBOX_SQL =
- path: src/wxbot/queue_store.py
  line: 639
  anchor: def finish_delivery(
- path: src/wxbot/queue_store.py
  line: 21
  anchor: FAILURE_DETAIL_FIELDS =
- path: src/wxbot/delivery_handlers/bubble.py
  line: 111
  anchor: details.update(confirm_evidence=evidence
changes:
- raw/changes/2026-11-03-indextts-enqueue-media
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-03-feat-voice-001-virtual-mic
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-07-delivery-handlers
```
### SQLite outbox

#### 字段清单（VERSION=10 最终结构）

| 字段 | SQLite 类型/约束/默认 |
|---|---|
| seq | INTEGER PRIMARY KEY AUTOINCREMENT |
| id | TEXT NOT NULL UNIQUE |
| contact / text / state | TEXT NOT NULL |
| batch_id | TEXT REFERENCES batches(id)，可 NULL（主动推送） |
| created_at / not_before | REAL NOT NULL |
| baseline | TEXT，可 NULL |
| submitted_at / finished_at / failed_at | REAL，可 NULL |
| error | TEXT NOT NULL DEFAULT '' |
| submitted_text / draft_text | TEXT，可 NULL |
| part_seq | INTEGER NOT NULL DEFAULT 1 |
| resolution | TEXT NOT NULL DEFAULT '' |
| kind | TEXT NOT NULL DEFAULT 'text' |
| retries / detached / manual_required | INTEGER NOT NULL DEFAULT 0 |
| mention_name | TEXT NOT NULL DEFAULT '' |
| package_id | TEXT REFERENCES delivery_packages(id)，可 NULL |
| media_id / media_path | TEXT NOT NULL DEFAULT '' |

#### 索引与关系

UNIQUE(batch_id,part_seq)，outbox_state(state,seq)。batch_id 指向 [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)；SQLite 中 NULL 的批次不构成这个唯一键下的去重保障。package_id 关联 delivery_packages（尚未独立建页）；媒体相关字段不能拿模型任意文件路径填充。

#### 字段血缘

[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1) 将完整 reply parts 逐项写 text/part_seq，群 mention_name 仅第一条；UI 发件器写 baseline/submitted_text/submitted_at 并核对新增自身气泡后记 state。`kind=voice` 的 `media_path` 仅当 `tts_provider=fixture` 时由模型线程或 `DeliveryPump.enqueue` 写成 `fixture_wav`；`indextts` 等投递时合成的提供者保持默认空字符串，发件前走 TTS `prepare`。无可用绑定不入语音条。见 [concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0)、[raw/changes/2026-11-03-indextts-enqueue-media](index-tts.md#doc-29fc2d893f2889)。`baseline` 保存的是去掉快照引用的行（引用只属于一次读取，不跨重启）；发送确认把 `confirm_evidence`（`ref`/`text`）与 `ref_available` 写进该行的 `delivery_events.details`，失败写 `error_code` / `retry`，提及失败且能证明字面残留时另写 `mention_residue`，白名单见 `FAILURE_DETAIL_FIELDS`。实际投递规则见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。

`draft_text` 只在 UI 读回能证明是机器人输入时写入：已核验的正文前缀，或提及失败后读回的字面 `@...` 前缀。`blocked`/`uncertain` 保留该值，下一次发件前由 `owned_draft(contact)` 取回并清理；只有 `sent` 才清空。

[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f) 的 outbox、rounds、events 和 [apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714) 读取状态/时间/分句进度；前端不得从“存在 outbox”推断已发送。所属 [modules/wxbot](wxbot.md#doc-8508032cbe5131)，执行器 [symbols/queue-store](queue-storage.md#doc-37f6245b143a25)。

#### 风险与测试

[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) 复用 kind=voice、package_id、media_id、media_path、part_seq，不新增列；路径只能来自鉴权音频缓存，部分顺序由原 outbox.seq 约束。该包不要求管理台参考音绑定，失败停止后续部分；已录音异常为 uncertain，不自动重放。该路径与原自动语音字段血缘分开。

uncertain/confirming 记录需要保守保留及人工核对，不能任意自动重放；detached 标记与超时/关闭轮次有关。本地 test_delivery_queue.py、test_delivery_failure_policy.py、test_queue_migration.py。

#### 代码依据

- `src/wxbot/queue_schema.py:34` — `_TABLES = (`
- `src/wxbot/queue_schema.py:84` — `def initialize(`
- `src/wxbot/queue_schema.py:149` — `for sql in ('CREATE INDEX`
- `src/wxbot/queue_schema.py:7` — `VERSION = 10`
- `src/wxbot/queue_schema.py:22` — `OUTBOX_SQL =`
- `src/wxbot/queue_store.py:639` — `def finish_delivery(`
- `src/wxbot/queue_store.py:21` — `FAILURE_DETAIL_FIELDS =`
- `src/wxbot/delivery_handlers/bubble.py:111` — `details.update(confirm_evidence=evidence, ref_available=by_ref)`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-mention-picker-gating-residue](wechat-ui.md#doc-980ea358badbe6)

#### 变更

- 2026-11-03: FEAT-VOICE-001 P1 outbox kind=voice（虚拟麦+RALT）；见 [raw/changes/2026-11-03-feat-voice-001-virtual-mic](delivery-voice.md#doc-3b7c8dcbc01ec2)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 群聊采集与自动语音复核（2026-11-05）

自动回复的 webui 默认推导、实时语音策略、流式缓冲、daemon 合成及录音前准确预设复核见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)；旧媒体包/离线提供者合同保留。自动 webui 的录音前失败终结并仅回退一次文字，不让 blocked 重试重复投递，无数据库迁移。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。


#### 发件职责拆分（2026-11-07）

统一调度见 [symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca)，文字、图片、语音、表情的准备和确认见 [symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c)。outbox 字段、语音授权、重试及流式契约保持原状，无迁移。

来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。
<!-- end-migrated-part: doc-6dd6d137f99cdf -->
