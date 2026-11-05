---
type: concept
module: wxbot
summary: 未读任务只有采集成才清除，读不到文字时必须退避并最终放弃，否则阻塞发送队列
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/wxbot/inbox.py
  line: 449
  anchor: 'def _receive_one(self):'
- path: src/wxbot/inbox.py
  line: 479
  anchor: 'def _abandon_unread(self, session, attempts):'
- path: src/wxbot/inbox.py
  line: 376
  anchor: 'if self._receive_abandoned.get(session.contact) == (session.unread_count, session.mentioned):'
- path: src/wxbot/inbox.py
  line: 269
  anchor: if (fresh is None and session and session.unread_count
- path: src/wxbot/inbox.py
  line: 554
  anchor: receive_ready = bool(self._connected and any(
- path: src/wxbot/wechat/chat_window.py
  line: 364
  anchor: raise ReadDeferred('unread_messages_not_visible'
- path: src/wxbot/queue_store.py
  line: 229
  anchor: 'def forget_session(self, contact):'
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-03-feat-voice-001-anchor-refresh
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-residue-reverify
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-group-auto-voice
---
# 未读采集的重试与放弃

## 术语与状态含义

未读任务记在 `MainInbox.pending` 与 `pending_sessions` 两处，键都是会话名。`_receive_retry[name]` 是下次允许尝试的时刻，`_receive_failures[name]` 是连续失败次数，`_receive_abandoned[name]` 是放弃时的 `(unread_count, mentioned)` 快照。

「默认状态」是：未读任务只在 `_capture` 成功末尾 `self.pending.pop(name, None)` 时消失，`capture()` 同时 `DELETE FROM pending_sessions`。没有第三条清除路径。

## 业务规则与边界

- 采集失败按指数退避：第 n 次失败后等待 `poll_interval * 2 ** (n-1)`，默认从 1.5 秒起。
- 连续失败达到 `[bot].unread_give_up_attempts`（默认 5）后放弃：清 `pending`、`forget_session` 删 `pending_sessions`、记下放弃快照。
- `_discover` 遇到与放弃快照完全相同的未读会跳过；未读数或「有人@我」变化后重新纳入，重新从第 1 次失败计数。
- `_capture` 成功时同时清失败计数与放弃快照，避免旧快照压住正常采集。
- 不可读的判定有两处：`chat_window.read_bundle` 在 `count > 0` 且没有任何 `other`/`system` 条目时抛 `unread_messages_not_visible`；`inbox._capture` 在被动/发送前后的读取里，`pending` 有未读但 `messages` 里没有 `other`/`system` 行时抛同一 `read_code`。

## 跨层映射

未读任务同时是 `QueueStore.prepare` 的闸门：`prepare` 看到该联系人还有 `pending_sessions` 就跳过，不把已入库的收件合成批次。所以「采集卡住」等价于「这个联系人的回复也停摆」，不只是少一条消息。

`tick` 用 `receive_ready`（`pending` 里有人到期）决定本轮的 UI 时间片给收还是给发；退避期间 `receive_ready` 为假，时间片自然让给发送。

## 历史坑与冲突

2026-11-01 之前失败只把 `_receive_retry` 推后一个轮询周期，没有放弃出口。收到只有小程序卡片、红包或消息区尚未加载的未读时，`pending` 永远不清，采集按 1.5 秒一轮持续失败并反复切换会话窗口，同一会话的新文字消息也被 `_capture_current` 的 `current.title in self.pending` 跳过。

同一时期 `mentions._cleanup` 用了 uiautomation 不认识的 `{Backspace}`，见 [[symbols/mention-selection]]；两件事独立，但同时发生在同一轮回复上：昵称是卡片文案 → 选不中候选 → 走回退链 → `TypeError` → 草稿卡死。

## 相关模块、接口、测试

[[modules/wxbot]]、[[concepts/message-pipeline]]、[[tables/queue-outbox]]。本地 `tests/unit/wxbot/test_inbox_unread_backoff.py` 覆盖退避时点、放弃后 `pending_sessions` 清空、放弃后 `prepare` 能成批、放弃快照未变时不重新采集、未读变化后重新纳入；`tests/unit/queue/test_read_deferred_delivery.py` 覆盖发送侧遇到 `ReadDeferred` 时的独立核验。

## 代码依据与修改来源

- `src/wxbot/inbox.py:449` — `def _receive_one(self):`
- `src/wxbot/inbox.py:479` — `def _abandon_unread(self, session, attempts):`
- `src/wxbot/inbox.py:367` — 放弃快照比较
- `src/wxbot/inbox.py:264` — `_capture` 的不可读守卫
- `src/wxbot/inbox.py:554` — `receive_ready`
- `src/wxbot/wechat/chat_window.py:350` — `read_bundle` 抛 `unread_messages_not_visible`
- `src/wxbot/queue_store.py:229` — `forget_session`

[[raw/changes/2026-11-01-mention-fallback-unread-retry]]

[[raw/changes/2026-11-02-ui-snapshot-ref-contract]]

[[raw/changes/2026-11-02-mention-residue-reverify]]


## 本次核对

[[raw/changes/2026-11-04-index-tts-skill]]：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [[apis/index-tts]]，其余已述契约未改。


## 群聊采集与自动语音复核（2026-11-05）

采集前的越屏恢复和 row_offscreen 显式拒绝见 [[concepts/capture-viewport]]；不放宽 gutter 阈值，不推进未知发送方快照。语音准备期间继续采集，恢复录音任务后本轮不再切换收件会话，见 [[concepts/automatic-voice-reply]]。来源 [[raw/changes/2026-11-05-group-auto-voice]]。
