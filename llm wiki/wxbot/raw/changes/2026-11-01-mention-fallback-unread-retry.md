---
type: change
title: 群聊提及回退清理与不可读未读的退避放弃
pages: [concepts/delivery-state, concepts/group-identity-evidence, concepts/identity-authority,
  concepts/message-pipeline, concepts/model-error-contract, concepts/unread-capture-retry,
  modules/telegram, modules/wxbot, symbols/mention-selection, symbols/queue-finish,
  symbols/queue-store, tables/queue-batches, tables/queue-inbox, tables/queue-outbox]
---
# 群聊提及回退清理与不可读未读的退避放弃

## 目标与背景

线上两个症状：

1. 群聊回复带 @ 时，`@` 之后整条发送链路停摆，之后该会话的所有回复都卡在 `blocked`。
2. 收到无法采集的消息（当时是小程序分享卡片）后，采集以每个轮询周期一次的频率无限重试，每次都失败，日志持续刷「采集失败」，同一会话的新文字消息也采集不到。

第一件事的取证：`delivery_events.details` 记录 `exception_type=TypeError`、`phase=mention_fallback_delete`、`enter_attempted=false`、`characters_entered=0`，同批 `outbox.mention_name` 是一句卡片文案。回退清理链 `_cleanup` 在删除阶段发送 `auto.SendKeys('{Backspace}')`；uiautomation 的 `SpecialKeyNames` 只有 `BACK`/`DEL`/`DELETE`，未知 `{Xxx}` 会被当作 Unicode 字面量交给 `SendUnicodeChar`，对 9 个字符的字符串调用 `ord()` 抛 `TypeError`。异常打断清理链，`\ufffc` 提及对象留在输入框；由于提及草稿从不写入 `owned_draft`，`clear_owned_draft` 无法认领它，后续 `start_send` 一律 `draft_conflict`。

第二件事的取证：`pending` 只在 `_capture` 成功时 `pop`，`_receive_one` 失败只把 `_receive_retry[name]` 推到 `now + poll`，没有任何放弃出口。`read_bundle` 在 `count > 0` 且没有 `other`/`system` 条目时抛 `ReadDeferred('unread_messages_not_visible')`，只有卡片或消息区未加载时会一直命中。同一行 `pending_sessions` 还让 `QueueStore.prepare` 跳过该联系人，已有的收件永远不进入批次。

## 文件与代码位置

- `src/wxbot/wechat/mentions.py:235` — `_cleanup` 删除阶段改用 `auto.SendKeys('{Back}')`，与 `src/wxbot/wechat/chat_window.py:402` 的 `clear_owned_draft` 保持一致。
- `src/wxbot/telegram_desktop.py:195` — `_Scan.close` 里同一处非法键名一并改为 `{Back}`。
- `src/wxbot/wechat/main_window.py:28` — 新增 `plausible_nickname`：长度上限 16（微信昵称上限）、拒绝换行、拒绝 `[` 前缀、拒绝以「你/我」开头且含空白的整句、拒绝含句读。
- `src/wxbot/wechat/main_window.py:45` — `preview_sender` 的前缀判定改调 `plausible_nickname`。
- `src/wxbot/inbox.py:440` — `_receive_one` 记录连续失败次数，失败按 `poll * 2 ** (n-1)` 退避。
- `src/wxbot/inbox.py:470` — 新增 `_abandon_unread`：达到 `bot.unread_give_up_attempts`（默认 5）后清 `pending`、清 `pending_sessions`、记住放弃时的未读快照。
- `src/wxbot/inbox.py:367` — `_discover` 跳过与放弃快照完全相同的未读，未读数或 `mentioned` 变化后重新纳入。
- `src/wxbot/inbox.py:318` — `_capture` 成功时同时清失败计数与放弃快照。
- `src/wxbot/queue_store.py:229` — 新增 `forget_session(contact)`，删除一行 `pending_sessions`。

## 接口与字段

无 HTTP 契约变化。新增可选配置 `[bot].unread_give_up_attempts`（默认 5，最小 1），未配置时行为与旧代码的首次重试一致，只是不再无限重试。

`ReadDeferred.read_code` 的取值集合未变；`unread_messages_not_visible` 现在有消费出口。

## 数据库与迁移

无 schema 迁移。`pending_sessions` 新增一种删除路径（`QueueStore.forget_session`），与 `capture()` 成功后的 `DELETE` 语义相同。

历史脏数据不在本次自动清理范围：`data/business.sqlite3` 的 `user_bindings.nickname`、`user_profiles.display_name`、`user_name_history`，以及 `group_member_names` 里已被学成卡片文案的昵称仍需人工确认后处理。修复后的运行时行为是退化为不带 @ 的纯正文发送，不再阻塞整条链路。

## 前端消费点

不涉及。管理台的 workflow/queue 只读投影读取同名列，放弃未读不新增状态值。

## 测试与异步任务

本地 `tests/`（不入 Git）：

- `tests/unit/text/test_true_mentions.py` — 假 `SendKeys` 的退格键名从 `{Backspace}` 改为 `{Back}`（原用例把非法键名当成合法键，遮蔽了这个 bug）；新增 `test_fallback_cleanup_uses_the_declared_uiautomation_back_key`，断言回退链走完能落到纯正文提交，且发送的键在 `auto.SpecialKeyNames` 里。
- `tests/unit/wxbot/test_group_nickname_mapping.py` — `test_preview_requires_complete_matching_body` 增补卡片/系统通知文案必须拒绝、正常带空格昵称仍可学。
- `tests/unit/wxbot/test_inbox_unread_backoff.py` — 退避时点、放弃后清 `pending_sessions`、放弃后 `prepare` 能成批、放弃快照未变时不重新采集、未读变化后重新纳入。
- `tests/unit/wxbot/test_capture_diagnostics.py` — 补 `MainInbox.__new__` 白盒夹具所需的计数器与 `store` 桩。

不涉及定时任务；退避与放弃都在 `MainInbox.tick()` 的 UI 时间片内同步完成。

## 风险与回滚

- 退避只影响采集节奏，最长单次等待为 `poll * 2 ** 4`（默认 24 秒）。回滚只需把 `unread_give_up_attempts` 设为很大的值即可恢复旧的重试频率。
- 放弃会丢弃那一批未读，可读内容本来就取不到；代价是该批卡片消息不会被模型看到，收益是同会话的新文字消息恢复采集、已有收件恢复成批。
- 放弃快照以 `(unread_count, mentioned)` 为键，若微信角标不变化但内容变化，仍会等到下一次未读变化才重试；这是为了不再每个轮询周期抢一次会话窗口。
- 昵称护栏只影响自动学习，人工在管理台确认的昵称不受影响。
