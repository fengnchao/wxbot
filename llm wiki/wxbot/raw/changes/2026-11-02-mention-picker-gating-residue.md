---
type: change
title: 群聊提及先等候选面板，失败残留登记为可清理草稿
pages: [concepts/delivery-state, modules/wiki, modules/wxbot, symbols/mention-selection,
  symbols/queue-store, tables/queue-outbox]
---
# 群聊提及先等候选面板，失败残留登记为可清理草稿

## 目标与背景

线上症状：群聊模拟 @ 成员失败后，输入框里留下字面 `@昵称`（不是真正的提及对象），随后该会话的消息一直粘贴不进去。

运行队列的 `delivery_events`（只读核对，不记录正文）与症状对应：

- 近期已确认的群回复多为 `mention_verified=false`，说明 @ 在验证阶段被静默降级为纯正文。
- 2026-10-28 两次 `blocked` 的 `phase=mention_verify`、`manual_required=true`、`characters_entered=0`：候选被选中后草稿校验未通过，`@昵称` 留在输入框，正文没有粘贴。
- 2026-10-29 一次 `blocked` 的 `phase=draft_cleanup`、`manual_required=true`：回退清理没有把草稿清空，下一次发送在准备阶段被挡。

代码原因是三件事叠加：

1. `mention_filter` 在输入 `@` 后不等候选面板出现就直接键入成员名。面板没打开时，昵称变成普通文字，形成字面 `@昵称`。
2. `mention_choose`/`_wait`/`mention_verify` 对草稿做逐字节比较。UIA 读回多一个尾随空格、换行，或清理时只删掉部分字符，都会判为「草稿变化」并 `blocked`。
3. `blocked` 的投递不会清 `outbox.draft_text`，但提及留下的字面草稿从来没有写进 `owned_draft`；下一次 `DeliveryPump._start` 无法认领，`start_send` 见到非空输入一律 `draft_conflict`，后续消息就永久粘贴失败。

## 文件与代码位置

- `src/wxbot/wechat/mentions.py:59` — 新增 `DRAFT_SPACE` 与 `_plain`：只剥离微信可能追加的分隔空白（空格、换行、U+2005、NBSP）。
- `src/wxbot/wechat/mentions.py:96` — 新增 `_open_timeout`：读取可选配置 `wechat.mention.open_timeout`，默认 1 秒，夹在 0.1–5 秒。
- `src/wxbot/wechat/mentions.py:101` — 新增 `_owned`：只接受本次会话输入过的字面 `@...` 前缀（含尾随空白、丢字、部分退格），`\ufffc` 对象和用户追加文字都不算。
- `src/wxbot/wechat/mentions.py:112` — 新增 `owned_residue()`：读回输入框，返回可证明属于我们的字面残留，否则空串。
- `src/wxbot/wechat/mentions.py:166` — `mention_trigger` 在发送 `@` 前置 `typed=true`；即使 `SendKeys` 抛异常，残留仍可认领。
- `src/wxbot/wechat/mentions.py:171` — `mention_filter` 先等 `_panel()` 出现；`open_timeout` 到期仍没有面板时，只清理自己输入的 `@` 并回退纯正文，绝不键入昵称。
- `src/wxbot/wechat/mentions.py:194` — `mention_choose` 用 `_owned` 而不是精确字符串比较。
- `src/wxbot/wechat/mentions.py:239` — `mention_verify` 用 `_plain` 容忍尾随空白，但仍只接受 `\ufffc` 或 `@昵称` 两种完整对象。
- `src/wxbot/wechat/mentions.py:255` — `_cleanup` 以 `_owned` 判定清理范围；删除阶段若只删掉部分字符，在 3 次上限内重新 `Ctrl+A` + `Back`，不再把半截 `@...` 留在输入框。
- `src/wxbot/wechat/typing.py:104` — 新增 `_save_mention_residue`：把 `owned_residue()` 通过 `on_verified_draft` 写成 `outbox.draft_text`，并记 `mention_residue=true`。
- `src/wxbot/wechat/typing.py:124` — 输入焦点/目标守卫失败时也登记提及残留。
- `src/wxbot/wechat/typing.py:244` — 异常路径同样登记残留，避免异常打断清理后草稿无人认领。
- `src/wxbot/wechat/chat_window.py:392` — 新增 `_draft_equal`：`clear_owned_draft` 的两次比较容忍尾随分隔空白，其余内容仍须完全一致。
- `src/wxbot/wechat/chat_window.py:401` — `clear_owned_draft` 在点击输入框后条件等待焦点（0.5 秒），因为残留可能来自上一次投递，窗口未必已在前台。
- `src/wxbot/queue_store.py:26` — `FAILURE_DETAIL_FIELDS` 增加 `mention_residue`。
- `src/wxbot/delivery_policy.py:37` — `save_draft` 的约定补充「验证过的字面提及前缀」这一种合法来源。
- `README.md:650` — 微信 UI 与队列一节补充面板 gating、默认超时与残留草稿规则。
- `llm wiki/wxbot/modules/wiki.md` — README 新增行把该页来源锚点从 699 推到 703，复核无行为变化。

## 接口与字段

无 HTTP 契约变化。新增可选配置 `wechat.mention.open_timeout`（秒，默认 1，非数值回退默认，超出范围夹到 0.1–5）。

`delivery_events.details` 新增标量键 `mention_residue`，只在 blocked 且读回的字面 `@...` 可证明属于本次操作时为 `true`；不写正文、不写昵称以外的新内容。原有 `mention_verified` / `mention_fallback` 语义不变。

## 数据库与迁移

无 schema 迁移。复用 `outbox.draft_text`：

- `blocked` 保留 `draft_text`（原行为），所以提取失败后仍可在下一次发送前认领并清理。
- `sent` 继续清空 `draft_text`（原行为）。
- `owned_draft(contact)` 只按联系人取最新非空值；`clear_owned_draft` 清掉后 `forget_draft` 删除该联系人的所有 `draft_text`。

历史遗留的字面 `@昵称` 若发生在这次改动之前，没有登记过 `draft_text`，仍需人工清一次输入框；修复只保证新失败不再产生无法认领的残留。

## 前端消费点

不涉及。管理台 `delivery_events` 的 details 只读投影；新键是标量，未知键的展示逻辑不需要改动。

## 测试与异步任务

本地 `tests/`（不入 Git）：

- `tests/unit/text/test_true_mentions.py` — 原「面板不可见也要键入筛选词」用例改为 `test_filter_is_not_typed_when_picker_never_opens`，断言只发送 `@`、不键入昵称、回退原因 `picker_not_opened`，最终以纯正文提交并删除自己输入的 `@`。
- `test_blocked_mention_registers_only_its_own_literal_residue_as_a_draft` — 焦点丢失 blocked 时只登记 `@甲`，并记 `mention_residue` / `manual_required`。
- `test_cleanup_removes_our_prefix_despite_trailing_space_and_partial_delete` — 尾随空格 + 每次只删一个字符时，清理链重试到空再粘贴正文。
- `test_owned_draft_clear_tolerates_ui_trailing_whitespace` — `clear_owned_draft('@甲')` 能清掉 UI 读回的 `'@甲 '`。
- 既有 41 条提及用例全部通过；`tests/unit/wxbot` 202 条通过；`compileall src/wxbot` 通过。

不涉及定时任务。清理与登记都在 UI 时间片的 `TypingSession.step` 内同步完成，不新增后台线程。

## 风险与回滚

- 面板 gating 会多等最多 `open_timeout` 秒。若某个微信版本确实在输入首字后才弹面板，会一直回退为纯正文；把 `open_timeout` 调到 5 秒可缓解，或按新面板重新校准 `[wechat.mention.panel]`。
- 残留登记只覆盖字面 `@...`；无法证明归属的 `\ufffc` 对象仍然 `blocked` 且不自动删除，避免误删用户的提及对象。这类失败仍需人工清理。
- `clear_owned_draft` 只放宽尾随分隔空白，不改变「必须完全匹配已登记草稿」的主体规则；用户改写草稿仍会 `draft_conflict`。
- 回滚：移除 `mention_filter` 的面板等待、`_owned`/`owned_residue` 与 `mention_residue` 即可恢复旧行为；`draft_text` 是既有列，无需迁移。
