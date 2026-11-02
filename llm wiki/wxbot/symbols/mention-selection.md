---
type: symbol
module: wxbot
summary: UI 线程内的 @ 提及选择器，先等候选面板再输入昵称，失败时只清理并登记自己输入的字面前缀
coverage: core
last_verified: '2026-11-02'
sources:
- path: src/wxbot/wechat/mentions.py
  line: 67
  anchor: 'class MentionSelection:'
- path: src/wxbot/wechat/mentions.py
  line: 101
  anchor: 'def _owned(self, value):'
- path: src/wxbot/wechat/mentions.py
  line: 112
  anchor: 'def owned_residue(self):'
- path: src/wxbot/wechat/mentions.py
  line: 255
  anchor: 'def _cleanup(self):'
- path: src/wxbot/wechat/mentions.py
  line: 282
  anchor: "auto.SendKeys('{Back}',waitTime=0)"
- path: src/wxbot/wechat/typing.py
  line: 129
  anchor: result = self._mention.step()
- path: src/wxbot/wechat/chat_window.py
  line: 426
  anchor: "auto.SendKeys('{Back}', waitTime=0.05)"
changes:
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
calls: []
called_by: []
---
# MentionSelection

## 签名与职责

`MentionSelection(chat, win, edit, name, *, clock=time.monotonic)`，所属 [[modules/wxbot]]。每次 `step()` 只做一小步 UI 操作、不 sleep、不用 Enter 选候选。阶段依次是 `mention_trigger` → `mention_filter` → `mention_choose` → `mention_verify`，失败后进入 `mention_fallback_cancel` → `mention_fallback_select` → `mention_fallback_delete` → `mention_fallback_verify`。

`mention_filter` 在输入 `@` 后先等候选面板出现（`wechat.mention.open_timeout`，默认 1 秒），面板出现后才键入成员名；超时仍没有面板时只保留 `@` 并进入回退链，不会把昵称写成普通文字。

返回 `'typing' | 'selected' | 'plain' | 'blocked'`。`'plain'` 表示放弃提及、改发不带 @ 的正文。

## 调用方与反向引用

由 `TypingSession.step` 在 `src/wxbot/wechat/typing.py:115` 调用；`TypingSession` 只在 `ChatWindow.start_send(..., mention_name=...)` 里创建，调用链再往上是 `DeliveryPump._start`（`src/wxbot/delivery.py:149`）。`mention_name` 由服务签发的身份给出，不由模型正文推断。

## 调用了谁

`auto.SendKeys` 发 `@`、筛选字面量和清理键；`find_all` 在面板里找候选；`rich_draft` 用 TextPattern 的 `\ufffc` 子对象与 RuntimeId 验证，Qt 不暴露子控件时退化为 `PickerReceipt`。`chat._can_send`、`chat._input_text` 做目标与草稿守卫。

## 副作用（库/文件/事件/网络）

只操作微信窗口的键盘与鼠标，不写库、不联网。失败原因写进 `TypingSession.failure_details`（`mention_fallback`、`mention_verified`、`mention_residue`），最终落 `delivery_events.details`。`mention_residue` 出现时，`TypingSession` 还会把读回的字面 `@...` 通过 `on_verified_draft` 写成 `outbox.draft_text`，供下一次投递认领清理。

## 契约、测试与风险

- 输入框必须是空的；`@` 之后每一步都要求草稿仍是我们写下的字面量，否则 `blocked` 且不回车。`_owned` 只接受本次会话输入过的 `@...` 前缀：尾随分隔空白、丢字和部分退格都算我们的，`\ufffc` 对象与用户追加的文字都不算。
- 只有候选唯一且 `Name` 完全等于目标昵称才点击。昵称是一句卡片文案时必然 `member_missing`，走 `_wait` → 回退链。
- 回退链删除阶段只能用 uiautomation 认识的特殊键。`SpecialKeyNames` 里退格是 `BACK`，`{Backspace}` 会被当成 Unicode 字面量交给 `SendUnicodeChar` 并抛 `TypeError`；2026-11-01 起改用 `{Back}`。2026-11-02 起，清理阶段若只删掉部分字符，会在 3 次上限内重新 `Ctrl+A` + `Back`，不再把半截 `@...` 留在输入框。
- 仍不能证明归属的 `\ufffc` 对象（rich_draft 与 PickerReceipt 都失败）保持 `blocked`，不自动删除；这类失败仍可能让后续发送停在 `draft_conflict`，需要人工清理。
- 本地覆盖在 `tests/unit/text/test_true_mentions.py`，含「面板未出现不得键入昵称」「尾随空白/部分删除仍能清干净」「blocked 时只登记自己的字面残留」等断言。

## 代码依据

- `src/wxbot/wechat/mentions.py:67` — `class MentionSelection:`
- `src/wxbot/wechat/mentions.py:101` — `def _owned(self, value):`
- `src/wxbot/wechat/mentions.py:112` — `def owned_residue(self):`
- `src/wxbot/wechat/mentions.py:255` — `def _cleanup(self):`
- `src/wxbot/wechat/mentions.py:282` — `auto.SendKeys('{Back}',waitTime=0)`
- `src/wxbot/wechat/typing.py:129` — `result = self._mention.step()`
- `src/wxbot/wechat/chat_window.py:426` — `auto.SendKeys('{Back}', waitTime=0.05)`

## 入库来源

[[raw/changes/2026-11-01-mention-fallback-unread-retry]]

[[raw/changes/2026-11-02-ui-snapshot-ref-contract]]

[[raw/changes/2026-11-02-mention-picker-gating-residue]]
