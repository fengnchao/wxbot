---
type: change
title: UI 快照引用、发送确认证据与稳定失败码
pages: [concepts/delivery-state, concepts/group-identity-evidence, concepts/message-pipeline,
  concepts/unread-capture-retry, modules/wiki, modules/wxbot, symbols/mention-selection,
  symbols/queue-store, tables/queue-outbox]
---
# UI 快照引用、发送确认证据与稳定失败码

## 目标与背景

借鉴 agent-desktop 的 snapshot/ref 契约，只改「怎么判断动作成功」，不改 wxbot 的驱动方式
（微信发送仍需真实焦点、剪贴板和真回车）。

原来的发送确认只比「对方最后一句之后有没有出现同文的自己气泡」，存在三类误判：

1. 同一句话别人刚说过（或自己上一轮说过同样的句子），回读时被当成新气泡，幽灵回复记成 `sent`。
2. 发送方判定（截图左右像素）抖动时，同一条行的方向可能翻转，正文相同也被算作证据。
3. 失败原因散落在多个细节字段里，前端只能看 `error` 文本，无法区分「重读一次界面就能重试」和「重放会重复副作用」。

改成：一次读取产生一个快照，每行带只属于本次读取的引用（控件运行期标识）；确认只认
「baseline 里不存在、且方向为自己、正文一致」的行。引用拿不到或不唯一时**显式降级**为正文对齐，
并把降级事实写进事件细节，而不是假装两种证据等价。

## 文件与代码位置

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

## 接口与字段

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

## 数据库与迁移

无 schema 迁移，VERSION 不变。仅扩展 `delivery_events.details` 的白名单字段；
`outbox.baseline` 与 `observations.snapshot` 的 JSON 里不再写入 `ref`。
历史行里的 JSON 没有 `ref` 键，`Snapshot` 判定其为「引用不完整」，自动按正文对齐，无需回填。

## 前端消费点

`src/dashboard/queue_view.py:8` 直接复用 `FAILURE_DETAIL_FIELDS` 过滤事件细节，
新增键会自动出现在只读投影里，网页端不需要改动。管理台没有按失败码分支的展示逻辑，
新字段只用于排障与后续统计。

## 测试与异步任务

本地 `tests/`（不入 Git）：

- `tests/unit/wxbot/test_ui_contract.py` — 9 条：同文旧行不算新证据、别人的同文回显不算、
  引用缺失时显式降级为 `text`、引用重复视为不可信、快照错位不猜测、落库剥离引用、
  失败信封的码与重试语义、`wait_until` 的满足/超时、发件泵记录 `ref` 证据且 baseline 无引用、
  `blocked` 事件带 `target_unavailable` + `after_snapshot`。
- 既有 `test_delivery_queue.py` / `test_delivery_failure_policy.py` / `test_clipped_history_capture.py`
  与 `test_typing.py` 未改断言，仍通过。

不涉及定时任务；`wait_until` 在 UI 时间片内同步等待，超时上限沿用原固定等待的 0.5 秒与 `switch_timeout`。

## 风险与回滚

- 引用依赖 UIA `GetRuntimeId()`。拿不到、行数为空或引用重复时 `ref_complete=False`，
  整体降级为正文对齐，并记 `ref_available=false` —— 这是旧行为，不会更差。
- 引用只在一次读取内有效，不落库、不跨进程；不存在「重启后旧引用被当成新行」的误确认路径。
- `wait_until` 有超时上限，不会把固定等待换成潜在死循环；超时后的判定与原逻辑一致。
- 失败码只增字段，不改状态机与重试 SQL；回滚只需还原 `reply_evidence` 的实现与 import，
  已写入的事件细节保持可读，无需清库。
- `Message.ref` 有默认值，旧 JSON 反序列化、其他构造点不需同步修改。
