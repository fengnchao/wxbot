# 文字发件队列

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 文字发件队列

保存待发送的文字回复，由界面线程发送至微信。

当前是 outbox.kind=text 的逻辑分支，由 TextDeliveryHandler 处理。
支持原有分批/整段/流式输入、群聊提及与草稿保护；新增自身气泡才确认发送。
未来由 Butler.reply_type 显式指定类型，本步不新增此字段。

## 技术资料

- [QueueStore.finish_batch_parts](#doc-b3c365f5c9fdf1) · `llm wiki/wxbot/symbols/queue-finish.md`

<a id="doc-b3c365f5c9fdf1"></a>

### QueueStore.finish_batch_parts

来源：`llm wiki/wxbot/symbols/queue-finish.md:1`。

```yaml
type: symbol
module: wxbot
summary: 完整分句入 outbox，模型完成和发送完成分开
coverage: core
last_verified: '2026-11-04'
sources:
- path: src/wxbot/queue_store.py
  line: 339
  anchor: def finish_batch_parts(
- path: src/wxbot/queue_store.py
  line: 321
  anchor: def _insert_delivery(
- path: src/wxbot/queue_store.py
  line: 388
  anchor: def _recompute_batch(
changes:
- raw/changes/2026-11-03-feat-voice-001-anchor-refresh
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-details-whitelist-reverify
- raw/changes/2026-11-02-mention-residue-reverify
- raw/changes/2026-11-04-index-tts-skill
calls: []
called_by:
- symbols/model-worker
```
### QueueStore.finish_batch_parts

#### 签名与关系

`finish_batch_parts(batch_id, parts, *, now, delay=0, reply_text=None, mention_name='')`；由 [symbols/model-worker](queue-worker.md#doc-0183b6974519f0) 和 QueueStore.finish_batch 调用，属于 [symbols/queue-store](queue-storage.md#doc-37f6245b143a25) / [modules/wxbot](wxbot.md#doc-8508032cbe5131)。

#### 输入及副作用

parts 必须是完整、非空字符串的 tuple（允许空 tuple 表示无需文本）；仅接受 processing 批次，拒绝重复保存模型结果。事务内逐句写 [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)，更新 [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a) 的 reply_text/reply_complete/part_count，再重算聚合状态。

群 @ 目标使用服务解析后的 mention_name，且仅第一分句携带；不使用观察昵称或模型文本来选收件人。入库完成不等于微信已发送，见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。`_insert_delivery` 签名与写入列未变，快照引用只存在于 UI 发件侧，不进入 outbox。

#### 测试

本地 tests/unit/queue/test_multipart_flow.py、test_queue_store.py、tests/butler/test_reply_delivery_lifecycle.py。

#### 代码依据

- `src/wxbot/queue_store.py:339` — `def finish_batch_parts(`
- `src/wxbot/queue_store.py:321` — `def _insert_delivery(`
- `src/wxbot/queue_store.py:388` — `def _recompute_batch(`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-details-whitelist-reverify](delivery-pump.md#doc-ae7b71a2b37518)

[raw/changes/2026-11-02-mention-residue-reverify](wechat-ui.md#doc-989f2003dec3a1)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。
<!-- end-migrated-part: doc-b3c365f5c9fdf1 -->
