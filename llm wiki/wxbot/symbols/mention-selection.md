---
type: symbol
module: wxbot
summary: UI 线程内的 @ 提及选择器，验证失败时退回纯正文并清理自己输入的前缀
coverage: core
last_verified: '2026-11-01'
sources:
- path: src/wxbot/wechat/mentions.py
  line: 59
  anchor: 'class MentionSelection:'
- path: src/wxbot/wechat/mentions.py
  line: 213
  anchor: 'def _cleanup(self):'
- path: src/wxbot/wechat/mentions.py
  line: 235
  anchor: "auto.SendKeys('{Back}',waitTime=0)"
- path: src/wxbot/wechat/typing.py
  line: 112
  anchor: result = self._mention.step()
- path: src/wxbot/wechat/chat_window.py
  line: 402
  anchor: "auto.SendKeys('{Back}', waitTime=0.05)"
changes:
- raw/changes/2026-11-01-mention-fallback-unread-retry
calls: []
called_by: []
---
# MentionSelection

## 签名与职责

`MentionSelection(chat, win, edit, name, *, clock=time.monotonic)`，所属 [[modules/wxbot]]。每次 `step()` 只做一小步 UI 操作、不 sleep、不用 Enter 选候选。阶段依次是 `mention_trigger` → `mention_filter` → `mention_choose` → `mention_verify`，失败后进入 `mention_fallback_cancel` → `mention_fallback_select` → `mention_fallback_delete` → `mention_fallback_verify`。

返回 `'typing' | 'selected' | 'plain' | 'blocked'`。`'plain'` 表示放弃提及、改发不带 @ 的正文。

## 调用方与反向引用

由 `TypingSession.step` 在 `src/wxbot/wechat/typing.py:112` 调用；`TypingSession` 只在 `ChatWindow.start_send(..., mention_name=...)` 里创建，调用链再往上是 `DeliveryPump._start`（`src/wxbot/delivery.py:174`）。`mention_name` 由服务签发的身份给出，不由模型正文推断。

## 调用了谁

`auto.SendKeys` 发 `@`、筛选字面量和清理键；`find_all` 在面板里找候选；`rich_draft` 用 TextPattern 的 `\ufffc` 子对象与 RuntimeId 验证，Qt 不暴露子控件时退化为 `PickerReceipt`。`chat._can_send`、`chat._input_text` 做目标与草稿守卫。

## 副作用（库/文件/事件/网络）

只操作微信窗口的键盘与鼠标，不写库、不联网。失败原因写进 `TypingSession.failure_details`（`mention_fallback`、`mention_verified`），最终落 `delivery_events.details`。

## 契约、测试与风险

- 输入框必须是空的；`@` 之后每一步都要求草稿仍是我们写下的字面量，否则 `blocked` 且不回车。
- 只有候选唯一且 `Name` 完全等于目标昵称才点击。昵称是一句卡片文案时必然 `member_missing`，走 `_wait` → 回退链。
- 回退链删除阶段只能用 uiautomation 认识的特殊键。`SpecialKeyNames` 里退格是 `BACK`，`{Backspace}` 会被当成 Unicode 字面量交给 `SendUnicodeChar` 并抛 `TypeError`；一旦抛出，清理链中断，`\ufffc` 提及对象留在输入框，而提及草稿从不写入 `owned_draft`，`clear_owned_draft` 无法认领，后续 `start_send` 全部 `draft_conflict`。2026-11-01 起改用 `{Back}`。
- 本地覆盖在 `tests/unit/text/test_true_mentions.py`，含「回退链走完落到纯正文」与「发送的特殊键都在 `auto.SpecialKeyNames` 里」两条断言。

## 代码依据

- `src/wxbot/wechat/mentions.py:59` — `class MentionSelection:`
- `src/wxbot/wechat/mentions.py:213` — `def _cleanup(self):`
- `src/wxbot/wechat/mentions.py:235` — `auto.SendKeys('{Back}',waitTime=0)`
- `src/wxbot/wechat/typing.py:112` — `result = self._mention.step()`
- `src/wxbot/wechat/chat_window.py:402` — `auto.SendKeys('{Back}', waitTime=0.05)`

## 入库来源

[[raw/changes/2026-11-01-mention-fallback-unread-retry]]
