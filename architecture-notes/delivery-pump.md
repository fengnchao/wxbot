# 统一发件调度

一张 outbox 按 kind 分派文字、语音、图片、表情处理器，由 DeliveryPump 统一调度并保持同会话顺序。不要把旧图中的 reply_type 或独立文件发件队列当成当前实现。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 统一发件调度

实现：`src/wxbot/delivery.py` 的 DeliveryPump。

统一认领 SQLite outbox，按 kind 选择处理器；一个时刻只有一个 UI 发送任务。
负责回执、状态落库、失败维护、包授权和重启核对；不在不同处理器之间启动竞争窗口的线程。
同会话先后顺序由 QueueStore.claim_delivery 保证。HTTP、数据表和外部调用接口未改变。

批次 `done` 表示本轮调度已结束，不等同于每一段都已确认送达。发送结果不确定时，
该段保留 `uncertain` 待核对，后续未发段停止；人工重试只恢复选中段。
重启恢复后可放行新消息；仍在 `sending/confirming` 的活跃任务继续阻塞同会话下一轮。

## 技术资料

- [模型完成与投递状态](#doc-1e3fe9ed2e96f6) · `llm wiki/wxbot/concepts/delivery-state.md`
- [发件类型处理器](#doc-9ba04de08ae10c) · `llm wiki/wxbot/symbols/delivery-handlers.md`
- [统一发件调度 DeliveryPump](#doc-7ca25975c49fca) · `llm wiki/wxbot/symbols/delivery-pump.md`

<a id="doc-1e3fe9ed2e96f6"></a>

### 模型完成与投递状态

来源：`llm wiki/wxbot/concepts/delivery-state.md:1`。

```yaml
type: concept
module: wxbot
summary: 完整回复、排队、已发送和结果不确定分别处理
coverage: core
last_verified: '2026-11-07'
sources:
- path: src/wxbot/queue_store.py
  line: 339
  anchor: def finish_batch_parts(
- path: src/wxbot/queue_store.py
  line: 639
  anchor: def finish_delivery(
- path: src/wxbot/queue_store.py
  line: 680
  anchor: def retry_failed_deliveries(
- path: src/wxbot/delivery_policy.py
  line: 5
  anchor: def _end_reply(
- path: src/wxbot/queue_worker.py
  line: 186
  anchor: safe=getattr(exc,'retry_safe',False) is True
- path: src/wxbot/ui_contract.py
  line: 65
  anchor: 'class Snapshot:'
- path: src/wxbot/delivery_handlers/text.py
  line: 7
  anchor: def reply_evidence(
- path: src/wxbot/queue_store.py
  line: 21
  anchor: FAILURE_DETAIL_FIELDS =
- path: src/wxbot/queue_store.py
  line: 717
  anchor: 'def recover(self, *, now=None):'
- path: src/wxbot/queue_store.py
  line: 845
  anchor: def resolve(self, record_id,
changes:
- raw/changes/2026-11-03-indextts-enqueue-media
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-03-feat-voice-001-virtual-mic
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-model-error-contract
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-07-delivery-handlers
- raw/changes/2026-11-07-stale-regression-tests
```
### 模型完成与投递状态

#### 状态含义

[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a).reply_complete 标记模型完整结果；[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf) 的 pending/sending/confirming/sent/blocked/uncertain/skipped 是分句投递阶段。具体允许转换以 QueueStore 实现为准，本页不将状态名当通用可任意流转的枚举。

[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1) 只能保存 processing 批次，写完整分句后重算整轮，不会立即宣称微信已发。UI 输入/提交后仍需要观察确认，见 [modules/wxbot](wxbot.md#doc-8508032cbe5131) 和 [symbols/queue-store](queue-storage.md#doc-37f6245b143a25)。

#### 重试、时限与人工核对

模型失败时 retry_safe 默认 False；已提交结果未知不能自动重放。这套判定与重试上限的完整契约见 [concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)。投递重试和整轮失败时限是另一套规则：首次失败起计时，过期可结束剩余未发送块并推进后续轮次；_end_reply 对 uncertain/confirming 保留 uncertain + detached/review，不能抹掉不确定证据。

[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f) 展示剩余时限/动作，[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714) 展示当前阶段；它们不能恢复队列。超时默认值从配置及实现读，不在图谱额外写死第二份。

#### 发送确认证据与失败码

UI 发件器不因「界面里出现了这段文字」就认定已发送。一次读取产生一个内存快照，每行带只属于本次读取的引用；确认只认 `outbox.baseline` 里不存在、方向为自己、正文一致的行，同一句话别人刚说过或上一轮自己说过都不算新证据。引用缺失、行数为空或被行控件复用（引用不唯一）时整批降级为正文对齐，并把 `confirm_evidence`（`ref`/`text`）与 `ref_available` 写进 `delivery_events.details`。引用不落库：`outbox.baseline` 与 `observations.snapshot` 只保存去掉引用的行，所以重启后自然走正文对齐，不存在旧引用被当成新行的路径。

失败细节另带稳定 `error_code` 与重试语义 `retry`：`after_snapshot` 表示必须重新读界面再试，`never` 表示重放会重复副作用或必然再失败。它们只作诊断，不改 `manual_required`，也不进入 `retry_failed_deliveries` 的筛选 SQL，自动重试次数与时限仍按上一节。失败码表与判定在 `src/wxbot/ui_contract.py`，发件侧入口是 `delivery.reply_evidence`。

#### 草稿所有权与提及残留

`outbox.draft_text` 只记录 UI 读回能证明是机器人输入的内容：已核验的正文前缀，或提及失败后读回的字面 `@...` 前缀（对应的 `delivery_events.details` 带 `mention_residue=true`）。`blocked`/`uncertain` 保留该列，`sent` 才清空；下一次投递先 `owned_draft(contact)` 取回，再由 `clear_owned_draft` 在目标窗口清掉。清理只接受与登记值完全相同（可忽略尾随分隔空白）的草稿，用户改写的输入仍 `draft_conflict`，不会误删。无法证明归属的 `\ufffc` 提及对象不登记，继续走人工核对。

#### 测试与风险

[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) 的 queued 是持久化回执而非发送确认。语音包通过原包顺序/停止机制推进；PTT 的设备准备发生在按键前，按键后探测或播放失败必须释放按键并记 uncertain，防止自动重录。正常松键仍沿用 ptt_release 的现有契约，不等同对方已收听。

本地 test_delivery_failure_policy.py / test_reply_delivery_lifecycle.py / test_model_recovery.py，以及快照确认的 test_ui_contract.py。改时限需同步队列维护、只读倒计时和用户配置，不能只改界面；改确认证据要同时看 baseline 的落库形态与 `ref_available` 降级。

#### 代码依据

- `src/wxbot/queue_store.py:339` — `def finish_batch_parts(`
- `src/wxbot/queue_store.py:639` — `def finish_delivery(`
- `src/wxbot/queue_store.py:680` — `def retry_failed_deliveries(`
- `src/wxbot/delivery_policy.py:5` — `def _end_reply(`
- `src/wxbot/queue_worker.py:186` — `safe=getattr(exc,'retry_safe',False) is True`
- `src/wxbot/ui_contract.py:65` — `class Snapshot:`
- `src/wxbot/delivery_handlers/text.py:7` — `def reply_evidence(`
- `src/wxbot/queue_store.py:21` — `FAILURE_DETAIL_FIELDS =`

`queue_worker.py` 与 `delivery.py` 因导入 `resolve_queued_media_path` 各下移一行，上列锚点已对齐。语音条 `media_path` 见 [concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0)、[raw/changes/2026-11-03-indextts-enqueue-media](index-tts.md#doc-29fc2d893f2889)。

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


#### 过期测试预期核对

批次 done 表示本轮调度已终结，不代表全部分段已送达。uncertain 分段保留审计并 detached，剩余未发段停止；人工确认或重试仅作用于选中段，不能复活停止的余段。重启后的旧回复终结并放行新消息；sending/confirming 中的活跃任务仍阻塞同会话新轮。原实现未变，CLI 和登记实际正文的本地测试现按这些规则断言。

来源 [raw/changes/2026-11-07-stale-regression-tests](wxbot.md#doc-df3c99eaa835f8)。
<!-- end-migrated-part: doc-1e3fe9ed2e96f6 -->

<a id="doc-9ba04de08ae10c"></a>

### 发件类型处理器

来源：`llm wiki/wxbot/symbols/delivery-handlers.md:1`。

```yaml
type: symbol
module: wxbot
summary: 文字、语音、图片、表情独立发送处理器及共用气泡保护
coverage: core
last_verified: '2026-11-07'
sources:
- path: src/wxbot/delivery_handlers/__init__.py
  line: 8
  anchor: 'def create_handlers(pump):'
- path: src/wxbot/delivery_handlers/base.py
  line: 19
  anchor: 'class DeliveryHandler:'
- path: src/wxbot/delivery_handlers/bubble.py
  line: 7
  anchor: 'class BubbleDeliveryHandler(DeliveryHandler):'
- path: src/wxbot/delivery_handlers/text.py
  line: 22
  anchor: 'class TextDeliveryHandler(BubbleDeliveryHandler):'
- path: src/wxbot/delivery_handlers/image.py
  line: 5
  anchor: 'class ImageDeliveryHandler(BubbleDeliveryHandler):'
- path: src/wxbot/delivery_handlers/voice.py
  line: 6
  anchor: 'class VoiceDeliveryHandler(DeliveryHandler):'
- path: src/wxbot/delivery_handlers/emoji.py
  line: 5
  anchor: 'class EmojiDeliveryHandler(DeliveryHandler):'
changes:
- raw/changes/2026-11-07-delivery-handlers
called_by:
- symbols/delivery-pump
calls:
- symbols/queue-store
```
### 发件类型处理器

所属 [modules/wxbot](wxbot.md#doc-8508032cbe5131)，由 [symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca) 的固定 registry 创建，不是模型可注册的插件。
每个处理器持有 Pump 上下文；队列操作继续使用 [symbols/queue-store](queue-storage.md#doc-37f6245b143a25)，不从模型响应接受任意媒体路径或身份权限。

#### 职责

| kind | 处理器 | 责任 |
|---|---|---|
| text | TextDeliveryHandler | 群提及、正文输入、流式封口、取消后草稿保护、自身气泡证据 |
| image | ImageDeliveryHandler | 原 ImageSession、可信路径、图片气泡确认、粘贴后失败人工核对 |
| voice | VoiceDeliveryHandler | WAV/TTS 准备、Future、模式/绑定复核、PTT 回执、一次文字回退 |
| emoji | EmojiDeliveryHandler | 原 send_sticker 及 sent/blocked/uncertain 映射 |

文字与图片继承 BubbleDeliveryHandler：共用目标准备、草稿归属、提交前捕获最新快照和包授权、确认时限。
文字的流式部分在 configure_input/sync_input 中处理；语音不走气泡核验，仍以 ptt_release 和 human_confirm_required 记录现有约定。

#### 生命周期

start 创建 UI Session 或语音准备任务；sync_input 在下一步前同步文字增量；complete 在 Session 离开 typing 后处理回执。
failure_details 在 Session 诊断之前提供默认值，prepare_finish 在关闭 Session 后决定持久状态，after_finish 在状态保存后做原语音回退。
VoiceDeliveryHandler.poll 只在 UI 线程恢复任务，核对 outbox 行仍为 sending；close 后不再接收结果。
语音失败规则和准确音色复核见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)、[concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0)，显式音频包见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。

#### 兼容与来源

`wxbot.delivery` 继续导出 ActiveDelivery、reply_evidence、reply_is_visible；仅本地测试访问的旧私有语音方法迁到 voice_handler。
未改变 DB/HTTP/配置。来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。
<!-- end-migrated-part: doc-9ba04de08ae10c -->

<a id="doc-7ca25975c49fca"></a>

### 统一发件调度 DeliveryPump

来源：`llm wiki/wxbot/symbols/delivery-pump.md:1`。

```yaml
type: symbol
module: wxbot
summary: 一张 outbox 的统一 UI 调度、类型分派、状态与回执
coverage: core
last_verified: '2026-11-07'
sources:
- path: src/wxbot/delivery.py
  line: 15
  anchor: 'class DeliveryPump:'
- path: src/wxbot/delivery.py
  line: 97
  anchor: 'def _finish(self, delivery, state,'
- path: src/wxbot/delivery.py
  line: 201
  anchor: 'def start_next(self):'
- path: src/wxbot/delivery.py
  line: 211
  anchor: 'def tick(self, *, allow_start=True):'
- path: src/wxbot/delivery.py
  line: 262
  anchor: 'def reconcile(self):'
changes:
- raw/changes/2026-11-07-delivery-handlers
calls:
- symbols/delivery-handlers
- symbols/queue-store
```
### 统一发件调度 DeliveryPump

所属 [modules/wxbot](wxbot.md#doc-8508032cbe5131)。MainInbox 创建一个 Pump 并在 UI 主线程调用它；构造、enqueue/start_next/tick/close/reconcile/busy 接口保留。

#### 调用与顺序

`start_next` 先检查活动 UI 任务、处理器准备状态和关闭状态，再通过 [symbols/queue-store](queue-storage.md#doc-37f6245b143a25) 的 claim_delivery 统一认领。
`handler_for(kind)` 选择 [symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c) 中的 text/voice/image/emoji。未知旧 kind 仍按既有文字兼容路径处理，不扩展 file 发送。
同会话跨类型 FIFO、失败阻塞/人工核对、不同会话轮转仍来自原 SQL，处理器没有私有数据库队列或并行 UI 消费线程。

#### 状态与边界

`_finish` 合并处理器默认诊断、UI Session 诊断及提交状态，关闭 Session，然后按类型调整失败策略，持久化结果，再执行类型后处理和 HTTP 等待者/媒体包回执。
语音合成仍在认领之后：准备时 busy=false 允许收件，但 preparing 阻止第二次发件认领；poll 恢复录音后本 tick 结束。
close 取消未开始的 Future、丢弃晚到结果并关闭活动 Session。重启 reconcile 只核对已有文字证据，图片/语音不凭文字快照重发。

不改 [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)、HTTP、配置或管理台 DTO。reply_type 分流、持久 TTS 作业与文件发送尚未实现。

#### 验证与来源

本地 `tests/unit/queue/test_delivery_handlers.py` 覆盖独立处理器、混合发送顺序、未确认图片不越序及重启不重发；原 queue/media/voice 回归保持断言。
参见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。
<!-- end-migrated-part: doc-7ca25975c49fca -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [发件重构第一步验证记录](#doc-a85671cf7b8516) · `docs/superpowers/plans/2026-11-07-delivery-handlers-verification.md`
- [Delivery Handlers Implementation Plan](#doc-7281dbe7fcbbd1) · `docs/superpowers/plans/2026-11-07-delivery-handlers.md`
- [发件处理器拆分（第一步）](#doc-4382681f9a2f3e) · `docs/superpowers/specs/2026-11-07-delivery-handlers-design.md`
- [发件处理器拆分影响分析](#doc-26369af37d5fda) · `llm wiki/wxbot/impacts/2026-11-07-delivery-handlers.md`
- [投递细节白名单扩展的词条复核](#doc-ae7b71a2b37518) · `llm wiki/wxbot/raw/changes/2026-11-02-details-whitelist-reverify.md`
- [UI 快照引用、发送确认证据与稳定失败码](#doc-5688ce5c14b7b6) · `llm wiki/wxbot/raw/changes/2026-11-02-ui-snapshot-ref-contract.md`
- [发件处理器按类型拆分](#doc-83d2ae6b4c4ac1) · `llm wiki/wxbot/raw/changes/2026-11-07-delivery-handlers.md`

<a id="doc-a85671cf7b8516"></a>

### 发件重构第一步验证记录

来源：`docs/superpowers/plans/2026-11-07-delivery-handlers-verification.md:1`。

### 发件重构第一步验证记录

后续更新：下文四项历史失败已完成核对及测试修正，全项目现为 1584 项通过、0 失败。
详见 [四项历史回归失败修复记录](wxbot.md#doc-b664511b293d11)。下文保留第一步重构时的原始验证结果。

当前工作树：`D:/work/code/wxbot`；分支 `codex/index-tts-skill`；起点 HEAD `20fc624bcf09e221079edd498fac85a5f2c1404f`。
保留所有原有未提交修改，不自动提交、迁移数据库或重启服务。

#### 结果

- 重构前相关回归：229 通过、2 个已有失败。
- 新增测试先运行：4 个处理器入口因模块不存在失败，3 个行为保持测试通过；实现后 7 项全部通过。
- 核心文字/流式/图片/自动语音回归：92 通过。
- 完整相关回归：236 通过、2 个相同的已有失败。
- 全项目 `python -m pytest`：1576 通过、4 失败、3 个 Pillow 弃用警告。
- 将拆分前 delivery.py 只在测试进程内载入，再单独运行上述 4 项：全部复现，不覆盖工作树。
- 只使用临时数据库、假窗口、假音频和随机本机端口替身；没有发送真实微信。
- 架构 HTML 渲染检查及 29 个节点 Markdown 映射检查；编辑器脚本保持原状。

#### 已有失败

1. `tests/integration/test_portable_install.py::test_plugin_references_and_protocol_are_self_contained`：测试预期 6 个 Skill，当前项目有 7 个。
2. `tests/unit/queue/test_queue_admin.py::test_multipart_cli_sent_and_retry_preserve_other_parts`：预期 waiting_delivery，实际 done。
3. `tests/unit/queue/test_queue_store.py::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker`：预期 uncertain，实际 done。
4. `tests/unit/text/test_typing.py::test_typing_steps_keep_half_second_between_batches_and_one_final_enter`：预期一次粘贴，当前时序已发生两次。

本次不改变这些模块的行为或测试预期，避免结构重构夹带队列状态及输入间隔改动。

#### 审查

独立审查已逐段对照拆分前源码与全部新处理器，未发现引入的正确性回归。
复核范围包括混合顺序、关闭与晚到结果、流式提交门控、图片人工核对、撤权、准确预设和单次回退。

非阻塞测试缺口暂留：后台合成中删除/跳过队列行的专门回归；源码中的失效行检查已原样保留，现有测试覆盖关闭时丢弃结果。

#### 环境与图谱

首次在沙箱默认临时目录运行遇到访问权限错误；改用独立 `tests/.tmp-delivery-*` 后解决。
带 HTTP 替身的测试在允许本机回环连接的测试进程执行，避免 WinError 10013。
图谱保留两条原有 pending-change：2026-11-03-feat-voice-002-indextts、2026-11-03-indextts-enqueue-media；本次记录单独入库，不代替旧记录完成审核。
<!-- end-migrated-part: doc-a85671cf7b8516 -->

<a id="doc-7281dbe7fcbbd1"></a>

### Delivery Handlers Implementation Plan

来源：`docs/superpowers/plans/2026-11-07-delivery-handlers.md:1`。

### Delivery Handlers Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans in this session. 用户已授权实施第一步。

**Goal:** 拆分四类发件处理器，保留现有投递契约。
**Architecture:** DeliveryPump 统一调度，一张 outbox 按 kind 选择处理器。文字和图片共用气泡发送流程；语音持有后台准备状态，表情独立发送。
**Tech Stack:** Python 3.14、SQLite、pytest、原生 SVG/HTML。
**Spec:** `docs/superpowers/specs/2026-11-07-delivery-handlers-design.md`

#### Global Constraints

- 不改数据库、HTTP、配置和管理台字段。
- 不重启服务、不发送真实微信；保留当前工作树已有修改。
- 本次在用户指定目录的 `codex/index-tts-skill` 分支工作，不提交或搬移已有未提交工作。

#### Review Focus

- 混合类型保持同会话 FIFO，确认前不领取同会话后项。
- WebUI 晚到结果在关闭/删除后不能录音；语音授权变化仍需复核。
- 流式文字只有封口才允许提交，草稿归属保护不变。
- 图文包撤权/图片已粘贴的失败保留人工核对。
- 重启仅核对已有气泡，不重新发送图片、语音或文字。

#### Task 1: 拆分处理器

**Files:** 修改 `src/wxbot/delivery.py`；新增 `src/wxbot/delivery_handlers/{__init__,base,bubble,text,image,voice,emoji}.py`；测试 `tests/unit/queue/test_delivery_handlers.py` 及现有 queue/media/voice 用例。
**Interfaces:** 保留 DeliveryPump 构造、enqueue/start_next/tick/close/reconcile/busy；处理器使用 start、sync_input、complete、prepare_finish、after_finish、poll、close 钩子；ActiveDelivery 和 reply_evidence 继续由旧入口导出。

- [x] 基线运行现有队列、媒体和自动语音回归。
- [x] 新增处理器可独立启动及真实 SQLite 混合类型顺序回归；运行并确认拆分入口缺失的失败。
- [x] 提取处理器与公共气泡流程；只调整既有测试调用的私有语音入口，保留断言。
- [x] 运行所有相关离线回归，核对结果。

#### Task 2: 架构与知识图谱同步

**Files:** `ARCHITECTURE.html`、`architecture-notes/`、`README.md`、`llm wiki/wxbot/` 相关条目。
**Interfaces:** kind、数据库表与 HTTP 保持原状；HTML 新节点绑定对应 Markdown。

- [x] 图中补充四类处理器及统一调度说明，保留规划节点并明确状态。
- [x] 补充源码职责、图谱调用与字段血缘，追加 raw 记录后 ingest/lint。
- [x] 渲染检查 HTML、运行适当测试与 diff 检查；独立审查本次差异。

#### 执行记录

- 基线：`D:/work/code/wxbot`，HEAD `20fc624bcf09e221079edd498fac85a5f2c1404f`；解释器与 REPO_ROOT 一致。
- Ruling: 就地保留已有未提交架构图和代码——用户要求接续当前项目第一步，隔离到 HEAD 会丢失当前工作基线；不自动提交其他修改。
- Pre-flight: Task 2 描述 Task 1 的最终处理器接口，依赖实现和源码核对完成后再入库。

- Task 1: complete — 核心 92 通过，相关套件 236 通过/2 个基线已有失败。
- Task 2: complete — 29 个节点映射与源码锚点通过，13 页 ingest 成功，lint 仅两条原有 pending-change。
- Final review: 独立审查已完成，无引入的正确性问题。
- Final: minor (deferred): 合成过程中删除/跳过行的专门回归用例；源码保护原样保留，现有关闭用例已通过。
- Final: Ruling: 既有状态/技能数量/输入间隔失败不进入本次结构重构 — 四项均用原始发件源码复现，保持本步行为范围；风险与详情见 verification 文档。
- 完整验证：1576 通过/4 个原有失败；未提交、未重启、未向真实微信发消息。
<!-- end-migrated-part: doc-7281dbe7fcbbd1 -->

<a id="doc-4382681f9a2f3e"></a>

### 发件处理器拆分（第一步）

来源：`docs/superpowers/specs/2026-11-07-delivery-handlers-design.md:1`。

### 发件处理器拆分（第一步）

用户已确认按架构重构的第一步：拆分文字、语音、图片、表情发送逻辑，保持现有消息行为。

#### 目标与约束

- 保留 `wxbot.delivery.DeliveryPump` 的构造与调用接口，由它统一认领 outbox、协调 UI、持久化状态、回执与失败维护。
- 在 `src/wxbot/delivery_handlers/` 分别实现 text、voice、image、emoji 处理器。文字和图片共用目标选择、草稿保护和气泡确认流程。
- 继续使用一张 SQLite outbox，按 kind 分派；同会话跨类型顺序仍由 QueueStore.claim_delivery 保证。
- 不改数据库、HTTP、配置与管理台字段。reply_type、持久 TTS 准备队列、文件发件和收件分类属于后续步骤。
- 保留现有语音授权复核、后台合成、单次文字回退、流式提交门控及重启核对语义。
- 离线测试仅使用临时库、假窗口和假音频；不重启已有服务、不发送微信测试消息。

#### 方案

已选择统一调度加类型处理器：保留一个 UI 所有者与跨类型顺序，避免为四个物理队列新增排序/迁移机制。
仅抽取辅助函数虽改动较少，但不能形成独立的发送责任；每种类型独立线程则会竞争同一个微信窗口，因此本步不采用。

#### 实现边界

处理器持有本次 Pump 上下文；共享生命周期钩子覆盖开始、输入同步、结果确认、结束和关闭。
语音处理器独立持有 Future 和本轮 WebUI 标记；只在 UI 线程恢复录音，后台线程仅准备音频。
未知 kind 继续沿用现有文字兼容路径，不由本步开放文件发送。
架构图保留目标布局，补充已实现的处理器节点，明确 reply_type 与前置 TTS 仍为规划。
<!-- end-migrated-part: doc-4382681f9a2f3e -->

<a id="doc-26369af37d5fda"></a>

### 发件处理器拆分影响分析

来源：`llm wiki/wxbot/impacts/2026-11-07-delivery-handlers.md:1`。

### 发件处理器拆分影响分析

状态：实施前源码已核对；本次仅结构重构，用户已授权第一步。

#### 文件、入口和调用方

- `src/wxbot/delivery.py:42 DeliveryPump`：目前文字、图片、表情、语音及确认混在一个类内，拆到 `delivery_handlers/`。
- `src/wxbot/inbox.py:45 MainInbox`：继续持有同一个 Pump，UI 所有权和 busy 语义不变。
- `src/wxbot/queue_store.py:585 claim_delivery`：统一认领，SQL 按 contact/seq 阻止后项越过未终结前项；不拆表、不改 SQL。
- `src/wxbot/queue_worker.py:46 process_once`：仅生成/持久化回复，无本次改动。
- 原代码的私有语音测试调用调整到 voice 处理器；公开导入 DeliveryPump/ActiveDelivery/reply_evidence 保持兼容。

#### 契约与字段血缘

ModelWorker/外发接口 → outbox.kind/text/media_path/package_id → Pump 认领 → 对应处理器 → 原窗口 Session → Pump.finish_delivery。
仍只有 text/voice/image/emoji；reply_type 和 file 未实现。HTTP/DTO 不变，前端队列和工作流继续读原状态/字段，无 UI 源码适配。
语音合成仍发生在认领后的投递准备阶段；不提前到模型线程，不添加持久 TTS 作业。

#### DB、异步任务与风险

数据库迁移不涉及；outbox schema/version/claim/recover 均保持原实现。
WebUI 后台线程仅合成，Future/关闭/失效行检查由语音处理器持有，UI 动作仍在 Pump tick 所在线程。
主要风险：类型混发次序、回退重复、语音撤权、图片残留和流式未封口提交。

#### 验证与回滚

使用本地 queue/media/automatic_voice_reply/tts_ptt/tts_transport/reply_delivery_lifecycle 离线测试，并补混合消息跨重启回归。全部使用临时数据和假 UI，不访问真实剪贴板。
同步 ARCHITECTURE.html、节点 Markdown 与源码图谱。回滚本次 Python 提取和相关文档即可，不迁移数据、不更改服务配置。
覆盖缺口：现有图谱无独立 DeliveryPump/类型处理器条目，本次补建。
<!-- end-migrated-part: doc-26369af37d5fda -->

<a id="doc-ae7b71a2b37518"></a>

### 投递细节白名单扩展的词条复核

来源：`llm wiki/wxbot/raw/changes/2026-11-02-details-whitelist-reverify.md:1`。

```yaml
type: change
title: 投递细节白名单扩展的词条复核
pages: [concepts/identity-authority, concepts/model-error-contract, symbols/queue-finish,
  tables/queue-batches, tables/queue-inbox]
```
### 投递细节白名单扩展的词条复核

#### 目标与背景

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6) 扩展了 `queue_store.py` 的
`FAILURE_DETAIL_FIELDS`（增加 `retry`、`confirm_evidence`、`ref_available`）。这 5 个词条都以该文件为来源，
虽然没有语义变化，但源码指纹变了，需要逐条对照复核并登记，否则巡检会一直报 `source-drift`。

#### 文件与代码位置

- `src/wxbot/queue_store.py:21` — `FAILURE_DETAIL_FIELDS` 的集合字面量行数未变，`claim_batch`（`:309`）、
  `finish_batch_parts`（`:339`）、`_insert_delivery`（`:321`）、`_recompute_batch`（`:359`）、
  `capture`（`:239`）、`finish_delivery`（`:591`）、`retry_failed_deliveries`（`:632`）的位置与实现均未变。
- `src/wxbot/queue_store.py:350` — `member_name = str(mention_name or '').strip()` 仍只取服务给出的 mention_name。

#### 接口与字段

这 5 个词条描述的字段、状态机、放行规则都没有变。唯一新增的是投递事件细节白名单里的键，
已在 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6) 与 [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf) 记录，不在本记录重复。

#### 数据库与迁移

不适用：无 schema 变化，`FAILURE_DETAIL_FIELDS` 只是读时过滤常量。

#### 前端消费点

不适用：管理台复用同一常量，新增键自动透出，本记录不引入网页改动。

#### 测试与异步任务

复核依据是既有离线用例（`tests/unit/queue/test_delivery_queue.py`、`test_delivery_failure_policy.py`、
`test_queue_store.py`）与本次新增的 `tests/unit/wxbot/test_ui_contract.py`；未新增定时任务。

#### 风险与回滚

复核结论是「无影响」：批次状态机、模型失败放行、身份 mention_name 解析都不经过细节白名单。
若后续把 `retry` 用于自动重试判定，必须同时更新 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6) 与
[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)，避免两套失败语义混用。
<!-- end-migrated-part: doc-ae7b71a2b37518 -->

<a id="doc-5688ce5c14b7b6"></a>

### UI 快照引用、发送确认证据与稳定失败码

来源：`llm wiki/wxbot/raw/changes/2026-11-02-ui-snapshot-ref-contract.md:1`。

```yaml
type: change
title: UI 快照引用、发送确认证据与稳定失败码
pages: [concepts/delivery-state, concepts/group-identity-evidence, concepts/message-pipeline,
  concepts/unread-capture-retry, modules/wiki, modules/wxbot, symbols/mention-selection,
  symbols/queue-store, tables/queue-outbox]
```
### UI 快照引用、发送确认证据与稳定失败码

#### 目标与背景

借鉴 agent-desktop 的 snapshot/ref 契约，只改「怎么判断动作成功」，不改 wxbot 的驱动方式
（微信发送仍需真实焦点、剪贴板和真回车）。

原来的发送确认只比「对方最后一句之后有没有出现同文的自己气泡」，存在三类误判：

1. 同一句话别人刚说过（或自己上一轮说过同样的句子），回读时被当成新气泡，幽灵回复记成 `sent`。
2. 发送方判定（截图左右像素）抖动时，同一条行的方向可能翻转，正文相同也被算作证据。
3. 失败原因散落在多个细节字段里，前端只能看 `error` 文本，无法区分「重读一次界面就能重试」和「重放会重复副作用」。

改成：一次读取产生一个快照，每行带只属于本次读取的引用（控件运行期标识）；确认只认
「baseline 里不存在、且方向为自己、正文一致」的行。引用拿不到或不唯一时**显式降级**为正文对齐，
并把降级事实写进事件细节，而不是假装两种证据等价。

#### 文件与代码位置

- `src/wxbot/ui_contract.py` — 新增。`DISPOSITIONS` / `failure()` / `disposition()` 定义 11 个稳定失败码与两种重试语义；
  `row_key()` 给出行的身份（优先引用）；`persisted_rows()` 在落库前剥离引用；`Snapshot` 提供
  `take` / `ref_complete` / `sent_after` / `evidence_available`。
- `src/wxbot/delivery.py:12` — `reply_evidence(before, current, text)` 返回 `(证据, 行, 引用是否可用)`；
  `reply_is_visible` 改为调用它，保持原签名兼容。
- `src/wxbot/delivery.py:85` — 新增 `_diagnostics(chat, phase, code)`：失败信封 + 阶段 + `send_diagnostics`。
- `src/wxbot/delivery.py:105` — `_finish` 对 `blocked`/`uncertain` 用 `setdefault` 补 `error_code`/`retry`，
  显式传入的码不被覆盖。
- `src/wxbot/delivery.py:171`、`:276` — baseline 落库改走 `persisted_rows`（不含引用）。
- `src/wxbot/delivery.py:389` — 确认事件追加 `confirm_evidence`（`ref`/`text`）与 `ref_available`。
- `src/wxbot/wechat/chat_window.py:36` — `Message` 增加可选 `ref: str = ''`，旧数据反序列化不受影响。
- `src/wxbot/wechat/chat_window.py:85` — `_row_ref(item)` 从控件 `GetRuntimeId()` 拼出行引用，异常返回空串。
- `src/wxbot/wechat/chat_window.py:428` — `start_send` 激活窗口后的固定 `sleep(0.2)` 换成
  `wait_until(target_is_current, timeout=0.5)`。
- `src/wxbot/wechat/locator.py:9` — 新增 `wait_until(predicate, *, timeout, interval, clock, sleep)`，
  时钟与休眠可注入，供离线测试。
- `src/wxbot/wechat/main_window.py:326` — 切换会话的尾部轮询改为 `wait_until`，超时仍按原逻辑判失败。
- `src/wxbot/wechat/typing.py:90`–`:221` — 各阻塞分支写入对应失败码：
  `target_changed` / `focus_lost` / `paste_mismatch` / `draft_conflict` / `clipboard_owner_changed`；
  except 兜底按是否已回车区分 `ui_error` / `paste_error`。
- `src/wxbot/inbox.py:316` — `observations.snapshot` 落库改用 `persisted_rows`。
- `src/wxbot/queue_store.py:21` — `FAILURE_DETAIL_FIELDS` 增加 `retry`、`confirm_evidence`、`ref_available`
  （`error_code` 已在白名单内）。
- 词条 `symbols/mention-selection`、`concepts/group-identity-evidence`、`concepts/unread-capture-retry`、
  `modules/wiki` 的源码行号随本次改动平移，已同步锚点（`typing.py:115`、`chat_window.py:246/356/413`、
  `README.md:699`、`delivery.py:149`）。

#### 接口与字段

无 HTTP 契约变化。

- `Message` 新增可选字段 `ref`，只存在于进程内的读取结果；`persisted_rows` 落库前剥离，
  所以 `observations.snapshot` 与 `outbox.baseline` 都不含引用，重启后 `reconcile` 自然走正文对齐。
- `delivery_events.details` 新增标量键：`error_code`、`retry`、`confirm_evidence`、`ref_available`。
  `retry` 只有 `after_snapshot`（必须重新读界面再试）与 `never`（重放会重复副作用或必然再失败）。
- 失败码集合：`target_unavailable`、`target_changed`、`focus_lost`、`clipboard_owner_changed`、
  `paste_error`、`draft_conflict`、`paste_mismatch`、`enter_unconfirmed`、`sticker_unconfirmed`、
  `sticker_unavailable`、`ui_error`；未知码统一落 `ui_error`。
- 失败信封**不**改 `manual_required`，也不参与 `retry_failed_deliveries` 的筛选 SQL，
  自动重试行为与改前完全一致。

#### 数据库与迁移

无 schema 迁移，VERSION 不变。仅扩展 `delivery_events.details` 的白名单字段；
`outbox.baseline` 与 `observations.snapshot` 的 JSON 里不再写入 `ref`。
历史行里的 JSON 没有 `ref` 键，`Snapshot` 判定其为「引用不完整」，自动按正文对齐，无需回填。

#### 前端消费点

`src/dashboard/queue_view.py:8` 直接复用 `FAILURE_DETAIL_FIELDS` 过滤事件细节，
新增键会自动出现在只读投影里，网页端不需要改动。管理台没有按失败码分支的展示逻辑，
新字段只用于排障与后续统计。

#### 测试与异步任务

本地 `tests/`（不入 Git）：

- `tests/unit/wxbot/test_ui_contract.py` — 9 条：同文旧行不算新证据、别人的同文回显不算、
  引用缺失时显式降级为 `text`、引用重复视为不可信、快照错位不猜测、落库剥离引用、
  失败信封的码与重试语义、`wait_until` 的满足/超时、发件泵记录 `ref` 证据且 baseline 无引用、
  `blocked` 事件带 `target_unavailable` + `after_snapshot`。
- 既有 `test_delivery_queue.py` / `test_delivery_failure_policy.py` / `test_clipped_history_capture.py`
  与 `test_typing.py` 未改断言，仍通过。

不涉及定时任务；`wait_until` 在 UI 时间片内同步等待，超时上限沿用原固定等待的 0.5 秒与 `switch_timeout`。

#### 风险与回滚

- 引用依赖 UIA `GetRuntimeId()`。拿不到、行数为空或引用重复时 `ref_complete=False`，
  整体降级为正文对齐，并记 `ref_available=false` —— 这是旧行为，不会更差。
- 引用只在一次读取内有效，不落库、不跨进程；不存在「重启后旧引用被当成新行」的误确认路径。
- `wait_until` 有超时上限，不会把固定等待换成潜在死循环；超时后的判定与原逻辑一致。
- 失败码只增字段，不改状态机与重试 SQL；回滚只需还原 `reply_evidence` 的实现与 import，
  已写入的事件细节保持可读，无需清库。
- `Message.ref` 有默认值，旧 JSON 反序列化、其他构造点不需同步修改。
<!-- end-migrated-part: doc-5688ce5c14b7b6 -->

<a id="doc-83d2ae6b4c4ac1"></a>

### 发件处理器按类型拆分

来源：`llm wiki/wxbot/raw/changes/2026-11-07-delivery-handlers.md:1`。

```yaml
type: change
title: 发件处理器按类型拆分，保留统一队列与投递契约
pages:
- apis/index-tts
- concepts/architecture-node-notes
- concepts/automatic-voice-reply
- concepts/delivery-state
- concepts/development-baseline
- concepts/voice-asset-binding
- modules/wiki
- tables/queue-outbox
- modules/wxbot
- concepts/message-pipeline
- symbols/queue-store
- symbols/delivery-pump
- symbols/delivery-handlers
```
### 发件处理器按类型拆分

#### 目标与背景

用户批准架构重构第一步。将现有文字、语音、图片、表情执行分开，保留一个队列调度器和现有投递行为。影响分析见 [impacts/2026-11-07-delivery-handlers](delivery-pump.md#doc-26369af37d5fda)。

#### 文件与代码位置

- src/wxbot/delivery.py:15 DeliveryPump；:97 _finish；:201 start_next；:211 tick；:262 reconcile。
- src/wxbot/delivery_handlers/base.py:19 生命周期；bubble.py:7 共用气泡保护；text.py:22 正文/流式；image.py:5 图片；voice.py:6 音频/PTT/回退；emoji.py:5 表情；__init__.py:8 固定 registry。
- README.md 文件职责和架构章节同步；ARCHITECTURE.html 添加调度器与四处理器、29 个节点和对应 architecture-notes 文档，明确未来分流与前置 TTS。
- 新建 symbols/delivery-pump 与 symbols/delivery-handlers；已更新相关来源锚点、反向调用、README 摘要与覆盖表。

#### 接口与字段

DeliveryPump 公开构造和方法、ActiveDelivery/reply_evidence/reply_is_visible 导入保持兼容。语音内部方法移入 voice_handler；本地测试只调整私有调用地址，保留断言。
无 HTTP/DTO/配置变更；按现有 kind 分派。不新增 reply_type 或 file，不前移 TTS。

#### 数据库与迁移

不涉及迁移。outbox/schema/version、claim_delivery/recover 未改。统一认领后按 kind 分派，跨类型顺序仍受原 contact/seq 约束。包回执、草稿、未确认结果和单次语音回退字段保持原血缘。

#### 前端消费点

web/ 源码、构建产物和管理台队列 API 不涉及；HTTP 和 DB 无变化，无需适配。
仅根 HTML 架构文档新增已实现处理器与路径，所有新增节点绑定真实 Markdown；其编辑器脚本未修改。

#### 测试与异步任务

基线相关回归 229 通过/2 失败；拆分后同范围加 7 项测试为 236 通过/2 个相同失败。核心回归 92 通过。
全项目回归 1576 通过/4 失败；四项均用拆分前发件源码在独立测试进程复现。详情与测试名见 docs/superpowers/plans/2026-11-07-delivery-handlers-verification.md。
未发送真实微信，未重启服务。语音处理器持有原单 daemon Future；后台只准备音频，UI 线程恢复前检查行、开关和音色。
独立代码审查未发现引入的正确性回归；保留“合成中删除/跳过行”的专门回归缺口，原失效行保护已保留。

#### 风险与回滚

主要风险为混合顺序、重复回退、预设撤权、图片残留和流式提前提交；现有离线回归加新混合/重启用例验证。
原有四条测试失败和两条旧 pending-change 不冒充本次已解决。新增图示仍保留部分目标架构，不能推断所有规划已实现。
回滚本次 delivery.py/新处理器和相应文档即可，无数据迁移或配置恢复。保留其他已有未提交工作。
<!-- end-migrated-part: doc-83d2ae6b4c4ac1 -->
