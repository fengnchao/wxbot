# 界面线程

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 界面线程

在微信窗口采集消息、发送出队内容，并核对发送结果。

发件由 `src/wxbot/delivery.py` 的 DeliveryPump 统一调度，按 outbox.kind 调用文字、语音、图片、表情处理器。
所有窗口操作仍在 UI 线程；语音后台线程仅准备音频，完成后回 UI 线程录音。

## 使用说明

- [wxbot / Butler / 模块与文件职责 / src/wxbot —— 微信 UI 收发层 / wechat/ —— 控件层](#doc-62c4af56a71362) · `README.md`
- [wxbot / Butler / 微信 UI 与队列](#doc-de96c7615265db) · `README.md`

<a id="doc-62c4af56a71362"></a>

### wxbot / Butler / 模块与文件职责 / src/wxbot —— 微信 UI 收发层 / wechat/ —— 控件层

来源：`README.md:382`。

###### wechat/ —— 控件层

| 文件 | 职责 |
|---|---|
| `wechat/main_window.py` | 微信主窗口：功能栏、会话列表、右侧当前聊天面板 |
| `wechat/chat_window.py` | 一个绑定联系人或群聊的独立聊天窗口：读消息、发消息（适配微信 4.x mmui） |
| `wechat/locator.py` | 按配置条件查找控件，条件来自 `config.wxbot.toml` 的 `[wechat.*]` |
| `wechat/typing.py` | UI 线程分批粘贴；`step` 每次最多输入一批，不 sleep 等下一批 |
| `wechat/clipboard.py` | 短时剪贴板租约，保证粘贴可校验；保留原剪贴板全部格式 |
| `wechat/mentions.py` | UI 线程的 @ 选择器，带校验过的纯文本回退 |
| `wechat/emoji.py` | 微信表情面板：打开面板，随机点一张表情／贴图发送 |
| `wechat/image.py` | 有界、仅 UI 线程的图片粘贴／预览／发送事务 |
<!-- end-migrated-part: doc-62c4af56a71362 -->

<a id="doc-de96c7615265db"></a>

### wxbot / Butler / 微信 UI 与队列

来源：`README.md:695`。

#### 微信 UI 与队列

- 默认 `[wechat].mode = "main"`：从 `mmui::MainWindow` 的 `session_list` 读会话行，
  行 `AutomationId` 形如 `session_item_<会话名>`；`[N条]` 是未读数，`[有人@我]` 是群提及提示。
- 群聊按右侧人数标签识别，`[bot].mention_names` 配机器人昵称；
  `[bot].group_reply_chance`（默认 0.1）与 `[bot].emoji_chance`（默认 0.2）决定非 @ 消息
  是否回复、发文字还是发表情。所有群消息都会进模型上下文。
- 群聊 @ 先等候选成员面板出现，再输入成员名。面板在 `wechat.mention.open_timeout`（默认 1 秒）内
  没出现时，只删除自己输入的字面 `@` 并按纯正文发送，不会把昵称当普通文字留在输入框。
  提及失败后读回仍是我们输入的字面 `@...` 时，会登记为可清理草稿，下一次发送前自动清除，
  避免后续消息一直因草稿冲突发不出去。
- 未读只有读到文字才算采集成功：同一条未读持续读不到内容（例如只有小程序卡片、红包）时按
  `poll_interval` 的倍数退避，满 `[bot].unread_give_up_attempts`（默认 5）次后放弃并清掉该会话的
  待读任务；未读数或「有人@我」变化后重新纳入。放弃前该会话的发送也会被待读任务挡住。
- 队列：`quiet_seconds` 默认 3、`max_wait_seconds` 10、`confirm_timeout` 5，模型并发由
  `[queue].max_model_requests` 控制（默认 2）。同会话同成员连续文本合并，命令与其他成员发言形成边界。
- 正文发送走剪贴板租约与 `Ctrl+V`，不是逐字符模拟键盘键入；回车等控制键仍由 UI 自动化执行。
  每批字符数 `wechat.typing.chunk_size`（默认 5）、间隔 `chunk_interval`（默认 0.25 秒）。
  `full` 整段粘贴，`chunked` 分批粘贴，`streaming` 随追加内容分批粘贴；缺省 `chunked`。
- 发件失败（`blocked`/`uncertain`）从首次失败起按 `retry_delay_seconds`（默认 20）自动重试，
  最多 `max_delivery_retries`（默认 2）次；满 `failure_discard_seconds`（默认 180）丢弃并留审计。
  同一个参数也是模型失败批次的放行时限：`retry_safe` 为否时不重试，到点后丢弃并继续后续消息。
- 回车后出现**新增**的「自己」气泡才算 `sent`；不确定不自动重放。输入框内容读不回来视为 blocked，不清草稿。
  「新增」按行的控件运行期标识（快照引用）判定：同一句话别人也发过、发送方判定抖动都不会被误认成自己的新气泡。
  引用拿不到或不唯一时显式降级为正文对齐（`confirm_evidence=text`），引用只在本次读取内有效，不落库，重启后只能按正文对齐。
- `delivery_events.details` 里每次发送都带稳定失败码 `error_code` 与重试语义 `retry`（`after_snapshot` 必须重新读界面，
  `never` 重放会重复副作用），发送确认另带 `confirm_evidence`（`ref`/`text`）与 `ref_available`。这些字段只放标量，不含正文与剪贴板内容。
- 剪贴板备份失败时降级为清空写入并在发送后不恢复，但「序号为 0 且已有内容」这类风险仍拒绝。
- `[wechat.emoji]` 未校准（button/item 为空）时自动改发文字，校准后自动恢复发图。
- UI 自动化要求窗口可见、不遮挡、机器不锁屏；控件随微信版本变化，用 `tools/probe.py` 重新校准。
<!-- end-migrated-part: doc-de96c7615265db -->

## 技术资料

- [截图采集与可见窗口](#doc-62362beb7f9b66) · `llm wiki/wxbot/concepts/capture-viewport.md`
- [未读采集的重试与放弃](#doc-8bf7e570157f43) · `llm wiki/wxbot/concepts/unread-capture-retry.md`
- [MentionSelection](#doc-c251b5ba0c9ae7) · `llm wiki/wxbot/symbols/mention-selection.md`

<a id="doc-62362beb7f9b66"></a>

### 截图采集与可见窗口

来源：`llm wiki/wxbot/concepts/capture-viewport.md:1`。

```yaml
type: concept
module: wxbot
summary: 采集前恢复越屏微信窗口，监视器联合区域外的像素不能证明发送方
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/wxbot/wechat/viewport.py
  line: 15
  anchor: 'def rect_is_visible(bounds, areas):'
- path: src/wxbot/wechat/viewport.py
  line: 38
  anchor: 'def fit_window_rect(bounds, areas):'
- path: src/wxbot/wechat/viewport.py
  line: 86
  anchor: 'def ensure_window_visible(window):'
- path: src/wxbot/wechat/chat_window.py
  line: 346
  anchor: def read_from_window(self, root,
- path: src/wxbot/wechat/main_window.py
  line: 287
  anchor: 'if not ensure_window_visible(win):'
changes:
- raw/changes/2026-11-05-group-auto-voice
depends_on:
- modules/wxbot
```
### 截图采集与可见窗口

#### 原因与边界

ImageGrab 在真实监视器范围以外可能得到纯黑补边。左右 gutter 背景不一致时，ChatWindow.side_scores 必须拒绝方向证据，不能把黑补边当头像或文字。历史出现此错误而窗口入屏后恢复，原因是越屏几何，不应提高色差阈值。详见 [concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)。

#### 监视器联合区域

viewport.rect_is_visible 逐区域扣除覆盖部分，支持负坐标、重叠监视器、跨屏窗口和屏间空隙，不能只用最大矩形冒充显示范围。fit_window_rect 对已经完整可见的窗口原样返回；否则选择重叠最大或最近的工作区，能放下时只平移，窗口大于工作区时才缩小。monitor_work_areas 使用明确 HANDLE 类型的 Win32 MonitorFromRect/GetMonitorInfoW，读取工作区而非固定主屏尺寸。

#### 恢复入口及失败语义

MainWindow.select 在已选中会话的早退分支之前恢复主窗口，并处理独立窗口。ChatWindow.read_from_window 在重新定位消息列表之前恢复现有 root，覆盖当前聊天无未读角标的采集路径；不切换会话或调用 SetActive。普通会话枚举、被动窗口 getter 仍不主动移动。

ensure_window_visible 通过控件 MoveWindow 后等待实际边界进入工作区，失败或不可确认则拒绝采集。side_scores 还在截图前验证头像高度带被真实监视器联合区域覆盖；越屏记 row_offscreen，不再用同文已发送缓存推断 self。原 gutter 一致性及裁剪拒绝规则保留，未知发送方仍不推进快照。

#### 测试与风险

本地 tests/unit/wxbot/test_viewport.py 覆盖联合几何、窗口放置、已可见不移动、恢复失败、无未读当前面板及越屏缓存拒绝；合成像素和 fake root 不访问真实消息。clipped-history 测试提供固定监视器和有效可见 fake root，意外移动直接失败，仍执行真实几何与采集逻辑。

窗口最小尺寸大于可用区域、系统拒绝移动或监视器信息不可用时仍会 ReadDeferred；不猜发送方。无 API/DTO/数据库迁移、无权限变更。加载代码需自行重启 wxbot。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。
<!-- end-migrated-part: doc-62362beb7f9b66 -->

<a id="doc-8bf7e570157f43"></a>

### 未读采集的重试与放弃

来源：`llm wiki/wxbot/concepts/unread-capture-retry.md:1`。

```yaml
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
```
### 未读采集的重试与放弃

#### 术语与状态含义

未读任务记在 `MainInbox.pending` 与 `pending_sessions` 两处，键都是会话名。`_receive_retry[name]` 是下次允许尝试的时刻，`_receive_failures[name]` 是连续失败次数，`_receive_abandoned[name]` 是放弃时的 `(unread_count, mentioned)` 快照。

「默认状态」是：未读任务只在 `_capture` 成功末尾 `self.pending.pop(name, None)` 时消失，`capture()` 同时 `DELETE FROM pending_sessions`。没有第三条清除路径。

#### 业务规则与边界

- 采集失败按指数退避：第 n 次失败后等待 `poll_interval * 2 ** (n-1)`，默认从 1.5 秒起。
- 连续失败达到 `[bot].unread_give_up_attempts`（默认 5）后放弃：清 `pending`、`forget_session` 删 `pending_sessions`、记下放弃快照。
- `_discover` 遇到与放弃快照完全相同的未读会跳过；未读数或「有人@我」变化后重新纳入，重新从第 1 次失败计数。
- `_capture` 成功时同时清失败计数与放弃快照，避免旧快照压住正常采集。
- 不可读的判定有两处：`chat_window.read_bundle` 在 `count > 0` 且没有任何 `other`/`system` 条目时抛 `unread_messages_not_visible`；`inbox._capture` 在被动/发送前后的读取里，`pending` 有未读但 `messages` 里没有 `other`/`system` 行时抛同一 `read_code`。

#### 跨层映射

未读任务同时是 `QueueStore.prepare` 的闸门：`prepare` 看到该联系人还有 `pending_sessions` 就跳过，不把已入库的收件合成批次。所以「采集卡住」等价于「这个联系人的回复也停摆」，不只是少一条消息。

`tick` 用 `receive_ready`（`pending` 里有人到期）决定本轮的 UI 时间片给收还是给发；退避期间 `receive_ready` 为假，时间片自然让给发送。

#### 历史坑与冲突

2026-11-01 之前失败只把 `_receive_retry` 推后一个轮询周期，没有放弃出口。收到只有小程序卡片、红包或消息区尚未加载的未读时，`pending` 永远不清，采集按 1.5 秒一轮持续失败并反复切换会话窗口，同一会话的新文字消息也被 `_capture_current` 的 `current.title in self.pending` 跳过。

同一时期 `mentions._cleanup` 用了 uiautomation 不认识的 `{Backspace}`，见 [symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7)；两件事独立，但同时发生在同一轮回复上：昵称是卡片文案 → 选不中候选 → 走回退链 → `TypeError` → 草稿卡死。

#### 相关模块、接口、测试

[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)。本地 `tests/unit/wxbot/test_inbox_unread_backoff.py` 覆盖退避时点、放弃后 `pending_sessions` 清空、放弃后 `prepare` 能成批、放弃快照未变时不重新采集、未读变化后重新纳入；`tests/unit/queue/test_read_deferred_delivery.py` 覆盖发送侧遇到 `ReadDeferred` 时的独立核验。

#### 代码依据与修改来源

- `src/wxbot/inbox.py:449` — `def _receive_one(self):`
- `src/wxbot/inbox.py:479` — `def _abandon_unread(self, session, attempts):`
- `src/wxbot/inbox.py:367` — 放弃快照比较
- `src/wxbot/inbox.py:264` — `_capture` 的不可读守卫
- `src/wxbot/inbox.py:554` — `receive_ready`
- `src/wxbot/wechat/chat_window.py:350` — `read_bundle` 抛 `unread_messages_not_visible`
- `src/wxbot/queue_store.py:229` — `forget_session`

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-mention-residue-reverify](wechat-ui.md#doc-989f2003dec3a1)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 群聊采集与自动语音复核（2026-11-05）

采集前的越屏恢复和 row_offscreen 显式拒绝见 [concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66)；不放宽 gutter 阈值，不推进未知发送方快照。语音准备期间继续采集，恢复录音任务后本轮不再切换收件会话，见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。
<!-- end-migrated-part: doc-8bf7e570157f43 -->

<a id="doc-c251b5ba0c9ae7"></a>

### MentionSelection

来源：`llm wiki/wxbot/symbols/mention-selection.md:1`。

```yaml
type: symbol
module: wxbot
summary: UI 线程内的 @ 提及选择器，先等候选面板再输入昵称，失败时只清理并登记自己输入的字面前缀
coverage: core
last_verified: '2026-11-05'
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
  anchor: auto.SendKeys('{Back}',waitTime=0)
- path: src/wxbot/wechat/typing.py
  line: 129
  anchor: result = self._mention.step()
- path: src/wxbot/wechat/chat_window.py
  line: 434
  anchor: auto.SendKeys('{Back}', waitTime=0.05)
changes:
- raw/changes/2026-11-03-feat-voice-001-anchor-refresh
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-group-auto-voice
calls: []
called_by: []
```
### MentionSelection

#### 签名与职责

`MentionSelection(chat, win, edit, name, *, clock=time.monotonic)`，所属 [modules/wxbot](wxbot.md#doc-8508032cbe5131)。每次 `step()` 只做一小步 UI 操作、不 sleep、不用 Enter 选候选。阶段依次是 `mention_trigger` → `mention_filter` → `mention_choose` → `mention_verify`，失败后进入 `mention_fallback_cancel` → `mention_fallback_select` → `mention_fallback_delete` → `mention_fallback_verify`。

`mention_filter` 在输入 `@` 后先等候选面板出现（`wechat.mention.open_timeout`，默认 1 秒），面板出现后才键入成员名；超时仍没有面板时只保留 `@` 并进入回退链，不会把昵称写成普通文字。

返回 `'typing' | 'selected' | 'plain' | 'blocked'`。`'plain'` 表示放弃提及、改发不带 @ 的正文。

#### 调用方与反向引用

由 `TypingSession.step` 在 `src/wxbot/wechat/typing.py:115` 调用；`TypingSession` 只在 `ChatWindow.start_send(..., mention_name=...)` 里创建，调用链再往上是 `DeliveryPump._start`（`src/wxbot/delivery.py:149`）。`mention_name` 由服务签发的身份给出，不由模型正文推断。

#### 调用了谁

`auto.SendKeys` 发 `@`、筛选字面量和清理键；`find_all` 在面板里找候选；`rich_draft` 用 TextPattern 的 `\ufffc` 子对象与 RuntimeId 验证，Qt 不暴露子控件时退化为 `PickerReceipt`。`chat._can_send`、`chat._input_text` 做目标与草稿守卫。

#### 副作用（库/文件/事件/网络）

只操作微信窗口的键盘与鼠标，不写库、不联网。失败原因写进 `TypingSession.failure_details`（`mention_fallback`、`mention_verified`、`mention_residue`），最终落 `delivery_events.details`。`mention_residue` 出现时，`TypingSession` 还会把读回的字面 `@...` 通过 `on_verified_draft` 写成 `outbox.draft_text`，供下一次投递认领清理。

#### 契约、测试与风险

- 输入框必须是空的；`@` 之后每一步都要求草稿仍是我们写下的字面量，否则 `blocked` 且不回车。`_owned` 只接受本次会话输入过的 `@...` 前缀：尾随分隔空白、丢字和部分退格都算我们的，`\ufffc` 对象与用户追加的文字都不算。
- 只有候选唯一且 `Name` 完全等于目标昵称才点击。昵称是一句卡片文案时必然 `member_missing`，走 `_wait` → 回退链。
- 回退链删除阶段只能用 uiautomation 认识的特殊键。`SpecialKeyNames` 里退格是 `BACK`，`{Backspace}` 会被当成 Unicode 字面量交给 `SendUnicodeChar` 并抛 `TypeError`；2026-11-01 起改用 `{Back}`。2026-11-02 起，清理阶段若只删掉部分字符，会在 3 次上限内重新 `Ctrl+A` + `Back`，不再把半截 `@...` 留在输入框。
- 仍不能证明归属的 `\ufffc` 对象（rich_draft 与 PickerReceipt 都失败）保持 `blocked`，不自动删除；这类失败仍可能让后续发送停在 `draft_conflict`，需要人工清理。
- 本地覆盖在 `tests/unit/text/test_true_mentions.py`，含「面板未出现不得键入昵称」「尾随空白/部分删除仍能清干净」「blocked 时只登记自己的字面残留」等断言。

#### 代码依据

- `src/wxbot/wechat/mentions.py:67` — `class MentionSelection:`
- `src/wxbot/wechat/mentions.py:101` — `def _owned(self, value):`
- `src/wxbot/wechat/mentions.py:112` — `def owned_residue(self):`
- `src/wxbot/wechat/mentions.py:255` — `def _cleanup(self):`
- `src/wxbot/wechat/mentions.py:282` — `auto.SendKeys('{Back}',waitTime=0)`
- `src/wxbot/wechat/typing.py:129` — `result = self._mention.step()`
- `src/wxbot/wechat/chat_window.py:434` — `auto.SendKeys('{Back}', waitTime=0.05)`

#### 入库来源

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-mention-picker-gating-residue](wechat-ui.md#doc-980ea358badbe6)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 群聊采集与自动语音复核（2026-11-05）

采集前的越屏恢复和 row_offscreen 显式拒绝见 [concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66)；不放宽 gutter 阈值，不推进未知发送方快照。语音准备期间继续采集，恢复录音任务后本轮不再切换收件会话，见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。
<!-- end-migrated-part: doc-c251b5ba0c9ae7 -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [群聊提及回退清理与不可读未读的退避放弃](#doc-a5d65ee79e182a) · `llm wiki/wxbot/raw/changes/2026-11-01-mention-fallback-unread-retry.md`
- [README 补不可采集未读的说明与图谱来源修正](#doc-0dfa536a596503) · `llm wiki/wxbot/raw/changes/2026-11-01-readme-unread-note.md`
- [群聊提及先等候选面板，失败残留登记为可清理草稿](#doc-980ea358badbe6) · `llm wiki/wxbot/raw/changes/2026-11-02-mention-picker-gating-residue.md`
- [提及残留登记引发的来源复核](#doc-989f2003dec3a1) · `llm wiki/wxbot/raw/changes/2026-11-02-mention-residue-reverify.md`

<a id="doc-a5d65ee79e182a"></a>

### 群聊提及回退清理与不可读未读的退避放弃

来源：`llm wiki/wxbot/raw/changes/2026-11-01-mention-fallback-unread-retry.md:1`。

```yaml
type: change
title: 群聊提及回退清理与不可读未读的退避放弃
pages: [concepts/delivery-state, concepts/group-identity-evidence, concepts/identity-authority,
  concepts/message-pipeline, concepts/model-error-contract, concepts/unread-capture-retry,
  modules/telegram, modules/wxbot, symbols/mention-selection, symbols/queue-finish,
  symbols/queue-store, tables/queue-batches, tables/queue-inbox, tables/queue-outbox]
```
### 群聊提及回退清理与不可读未读的退避放弃

#### 目标与背景

线上两个症状：

1. 群聊回复带 @ 时，`@` 之后整条发送链路停摆，之后该会话的所有回复都卡在 `blocked`。
2. 收到无法采集的消息（当时是小程序分享卡片）后，采集以每个轮询周期一次的频率无限重试，每次都失败，日志持续刷「采集失败」，同一会话的新文字消息也采集不到。

第一件事的取证：`delivery_events.details` 记录 `exception_type=TypeError`、`phase=mention_fallback_delete`、`enter_attempted=false`、`characters_entered=0`，同批 `outbox.mention_name` 是一句卡片文案。回退清理链 `_cleanup` 在删除阶段发送 `auto.SendKeys('{Backspace}')`；uiautomation 的 `SpecialKeyNames` 只有 `BACK`/`DEL`/`DELETE`，未知 `{Xxx}` 会被当作 Unicode 字面量交给 `SendUnicodeChar`，对 9 个字符的字符串调用 `ord()` 抛 `TypeError`。异常打断清理链，`\ufffc` 提及对象留在输入框；由于提及草稿从不写入 `owned_draft`，`clear_owned_draft` 无法认领它，后续 `start_send` 一律 `draft_conflict`。

第二件事的取证：`pending` 只在 `_capture` 成功时 `pop`，`_receive_one` 失败只把 `_receive_retry[name]` 推到 `now + poll`，没有任何放弃出口。`read_bundle` 在 `count > 0` 且没有 `other`/`system` 条目时抛 `ReadDeferred('unread_messages_not_visible')`，只有卡片或消息区未加载时会一直命中。同一行 `pending_sessions` 还让 `QueueStore.prepare` 跳过该联系人，已有的收件永远不进入批次。

#### 文件与代码位置

- `src/wxbot/wechat/mentions.py:235` — `_cleanup` 删除阶段改用 `auto.SendKeys('{Back}')`，与 `src/wxbot/wechat/chat_window.py:402` 的 `clear_owned_draft` 保持一致。
- `src/wxbot/telegram_desktop.py:195` — `_Scan.close` 里同一处非法键名一并改为 `{Back}`。
- `src/wxbot/wechat/main_window.py:28` — 新增 `plausible_nickname`：长度上限 16（微信昵称上限）、拒绝换行、拒绝 `[` 前缀、拒绝以「你/我」开头且含空白的整句、拒绝含句读。
- `src/wxbot/wechat/main_window.py:45` — `preview_sender` 的前缀判定改调 `plausible_nickname`。
- `src/wxbot/inbox.py:440` — `_receive_one` 记录连续失败次数，失败按 `poll * 2 ** (n-1)` 退避。
- `src/wxbot/inbox.py:470` — 新增 `_abandon_unread`：达到 `bot.unread_give_up_attempts`（默认 5）后清 `pending`、清 `pending_sessions`、记住放弃时的未读快照。
- `src/wxbot/inbox.py:367` — `_discover` 跳过与放弃快照完全相同的未读，未读数或 `mentioned` 变化后重新纳入。
- `src/wxbot/inbox.py:318` — `_capture` 成功时同时清失败计数与放弃快照。
- `src/wxbot/queue_store.py:229` — 新增 `forget_session(contact)`，删除一行 `pending_sessions`。

#### 接口与字段

无 HTTP 契约变化。新增可选配置 `[bot].unread_give_up_attempts`（默认 5，最小 1），未配置时行为与旧代码的首次重试一致，只是不再无限重试。

`ReadDeferred.read_code` 的取值集合未变；`unread_messages_not_visible` 现在有消费出口。

#### 数据库与迁移

无 schema 迁移。`pending_sessions` 新增一种删除路径（`QueueStore.forget_session`），与 `capture()` 成功后的 `DELETE` 语义相同。

历史脏数据不在本次自动清理范围：`data/business.sqlite3` 的 `user_bindings.nickname`、`user_profiles.display_name`、`user_name_history`，以及 `group_member_names` 里已被学成卡片文案的昵称仍需人工确认后处理。修复后的运行时行为是退化为不带 @ 的纯正文发送，不再阻塞整条链路。

#### 前端消费点

不涉及。管理台的 workflow/queue 只读投影读取同名列，放弃未读不新增状态值。

#### 测试与异步任务

本地 `tests/`（不入 Git）：

- `tests/unit/text/test_true_mentions.py` — 假 `SendKeys` 的退格键名从 `{Backspace}` 改为 `{Back}`（原用例把非法键名当成合法键，遮蔽了这个 bug）；新增 `test_fallback_cleanup_uses_the_declared_uiautomation_back_key`，断言回退链走完能落到纯正文提交，且发送的键在 `auto.SpecialKeyNames` 里。
- `tests/unit/wxbot/test_group_nickname_mapping.py` — `test_preview_requires_complete_matching_body` 增补卡片/系统通知文案必须拒绝、正常带空格昵称仍可学。
- `tests/unit/wxbot/test_inbox_unread_backoff.py` — 退避时点、放弃后清 `pending_sessions`、放弃后 `prepare` 能成批、放弃快照未变时不重新采集、未读变化后重新纳入。
- `tests/unit/wxbot/test_capture_diagnostics.py` — 补 `MainInbox.__new__` 白盒夹具所需的计数器与 `store` 桩。

不涉及定时任务；退避与放弃都在 `MainInbox.tick()` 的 UI 时间片内同步完成。

#### 风险与回滚

- 退避只影响采集节奏，最长单次等待为 `poll * 2 ** 4`（默认 24 秒）。回滚只需把 `unread_give_up_attempts` 设为很大的值即可恢复旧的重试频率。
- 放弃会丢弃那一批未读，可读内容本来就取不到；代价是该批卡片消息不会被模型看到，收益是同会话的新文字消息恢复采集、已有收件恢复成批。
- 放弃快照以 `(unread_count, mentioned)` 为键，若微信角标不变化但内容变化，仍会等到下一次未读变化才重试；这是为了不再每个轮询周期抢一次会话窗口。
- 昵称护栏只影响自动学习，人工在管理台确认的昵称不受影响。
<!-- end-migrated-part: doc-a5d65ee79e182a -->

<a id="doc-0dfa536a596503"></a>

### README 补不可采集未读的说明与图谱来源修正

来源：`llm wiki/wxbot/raw/changes/2026-11-01-readme-unread-note.md:1`。

```yaml
type: change
title: README 补不可采集未读的说明与图谱来源修正
pages:
- modules/wiki
```
### README 补不可采集未读的说明与图谱来源修正

#### 目标与背景

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a) 给未读采集加了退避与放弃，并新增可选配置 `[bot].unread_give_up_attempts`。README 是项目主文档，需要在「微信 UI 与队列」一节写清这个运维可见的默认行为，否则运维只能从日志猜。README 插入三行后，`modules/wiki` 里指向「### 项目知识图谱」的来源行号随之下滑，需要同步登记。

#### 文件与代码位置

- `README.md`「微信 UI 与队列」段新增一条：未读只有读到文字才算采集成功，按 `poll_interval` 倍数退避，满 `[bot].unread_give_up_attempts`（默认 5）次放弃并清掉待读任务，未读数或「有人@我」变化后重新纳入；放弃前该会话的发送也被待读任务挡住。
- `modules/wiki` 的来源 `README.md:652` → `README.md:655`（`### 项目知识图谱` 实际位置），`last_verified` 不变（同日）。
- 实现依据仍是 `src/wxbot/inbox.py:440` 的 `_receive_one` 与 `:470` 的 `_abandon_unread`。

#### 接口与字段

不涉及接口变更。新增的是 wxbot 运行时可选配置键 `[bot].unread_give_up_attempts`，只在 `MainInbox` 里以 `self.bot.get(...)` 读取，缺省 5，无需改动任何配置文件或配置 schema。

#### 数据库与迁移

不涉及表结构。放弃未读时会调用 `QueueStore.forget_session`（`src/wxbot/queue_store.py:229`）删除 `pending_sessions` 中对应行，该表结构未变。

#### 前端消费点

不涉及。管理台不展示 `unread_give_up_attempts`，也未新增页面或接口字段。

#### 测试与异步任务

只改文档与图谱来源，不新增测试。后端行为测试见 [raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a) 与本地 `tests/unit/wxbot/test_inbox_unread_backoff.py`。图谱自身用 `wiki.py lint` 巡检。

#### 风险与回滚

纯文档改动，回滚即删除 README 新增条目并把 `modules/wiki` 的来源行号改回 652。风险是 README 说明与代码默认值脱节：若后续把 `unread_give_up_attempts` 的默认值从 5 改掉，必须同步这段文案。
<!-- end-migrated-part: doc-0dfa536a596503 -->

<a id="doc-980ea358badbe6"></a>

### 群聊提及先等候选面板，失败残留登记为可清理草稿

来源：`llm wiki/wxbot/raw/changes/2026-11-02-mention-picker-gating-residue.md:1`。

```yaml
type: change
title: 群聊提及先等候选面板，失败残留登记为可清理草稿
pages: [concepts/delivery-state, modules/wiki, modules/wxbot, symbols/mention-selection,
  symbols/queue-store, tables/queue-outbox]
```
### 群聊提及先等候选面板，失败残留登记为可清理草稿

#### 目标与背景

线上症状：群聊模拟 @ 成员失败后，输入框里留下字面 `@昵称`（不是真正的提及对象），随后该会话的消息一直粘贴不进去。

运行队列的 `delivery_events`（只读核对，不记录正文）与症状对应：

- 近期已确认的群回复多为 `mention_verified=false`，说明 @ 在验证阶段被静默降级为纯正文。
- 2026-10-28 两次 `blocked` 的 `phase=mention_verify`、`manual_required=true`、`characters_entered=0`：候选被选中后草稿校验未通过，`@昵称` 留在输入框，正文没有粘贴。
- 2026-10-29 一次 `blocked` 的 `phase=draft_cleanup`、`manual_required=true`：回退清理没有把草稿清空，下一次发送在准备阶段被挡。

代码原因是三件事叠加：

1. `mention_filter` 在输入 `@` 后不等候选面板出现就直接键入成员名。面板没打开时，昵称变成普通文字，形成字面 `@昵称`。
2. `mention_choose`/`_wait`/`mention_verify` 对草稿做逐字节比较。UIA 读回多一个尾随空格、换行，或清理时只删掉部分字符，都会判为「草稿变化」并 `blocked`。
3. `blocked` 的投递不会清 `outbox.draft_text`，但提及留下的字面草稿从来没有写进 `owned_draft`；下一次 `DeliveryPump._start` 无法认领，`start_send` 见到非空输入一律 `draft_conflict`，后续消息就永久粘贴失败。

#### 文件与代码位置

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

#### 接口与字段

无 HTTP 契约变化。新增可选配置 `wechat.mention.open_timeout`（秒，默认 1，非数值回退默认，超出范围夹到 0.1–5）。

`delivery_events.details` 新增标量键 `mention_residue`，只在 blocked 且读回的字面 `@...` 可证明属于本次操作时为 `true`；不写正文、不写昵称以外的新内容。原有 `mention_verified` / `mention_fallback` 语义不变。

#### 数据库与迁移

无 schema 迁移。复用 `outbox.draft_text`：

- `blocked` 保留 `draft_text`（原行为），所以提取失败后仍可在下一次发送前认领并清理。
- `sent` 继续清空 `draft_text`（原行为）。
- `owned_draft(contact)` 只按联系人取最新非空值；`clear_owned_draft` 清掉后 `forget_draft` 删除该联系人的所有 `draft_text`。

历史遗留的字面 `@昵称` 若发生在这次改动之前，没有登记过 `draft_text`，仍需人工清一次输入框；修复只保证新失败不再产生无法认领的残留。

#### 前端消费点

不涉及。管理台 `delivery_events` 的 details 只读投影；新键是标量，未知键的展示逻辑不需要改动。

#### 测试与异步任务

本地 `tests/`（不入 Git）：

- `tests/unit/text/test_true_mentions.py` — 原「面板不可见也要键入筛选词」用例改为 `test_filter_is_not_typed_when_picker_never_opens`，断言只发送 `@`、不键入昵称、回退原因 `picker_not_opened`，最终以纯正文提交并删除自己输入的 `@`。
- `test_blocked_mention_registers_only_its_own_literal_residue_as_a_draft` — 焦点丢失 blocked 时只登记 `@甲`，并记 `mention_residue` / `manual_required`。
- `test_cleanup_removes_our_prefix_despite_trailing_space_and_partial_delete` — 尾随空格 + 每次只删一个字符时，清理链重试到空再粘贴正文。
- `test_owned_draft_clear_tolerates_ui_trailing_whitespace` — `clear_owned_draft('@甲')` 能清掉 UI 读回的 `'@甲 '`。
- 既有 41 条提及用例全部通过；`tests/unit/wxbot` 202 条通过；`compileall src/wxbot` 通过。

不涉及定时任务。清理与登记都在 UI 时间片的 `TypingSession.step` 内同步完成，不新增后台线程。

#### 风险与回滚

- 面板 gating 会多等最多 `open_timeout` 秒。若某个微信版本确实在输入首字后才弹面板，会一直回退为纯正文；把 `open_timeout` 调到 5 秒可缓解，或按新面板重新校准 `[wechat.mention.panel]`。
- 残留登记只覆盖字面 `@...`；无法证明归属的 `\ufffc` 对象仍然 `blocked` 且不自动删除，避免误删用户的提及对象。这类失败仍需人工清理。
- `clear_owned_draft` 只放宽尾随分隔空白，不改变「必须完全匹配已登记草稿」的主体规则；用户改写草稿仍会 `draft_conflict`。
- 回滚：移除 `mention_filter` 的面板等待、`_owned`/`owned_residue` 与 `mention_residue` 即可恢复旧行为；`draft_text` 是既有列，无需迁移。
<!-- end-migrated-part: doc-980ea358badbe6 -->

<a id="doc-989f2003dec3a1"></a>

### 提及残留登记引发的来源复核

来源：`llm wiki/wxbot/raw/changes/2026-11-02-mention-residue-reverify.md:1`。

```yaml
type: change
title: 提及残留登记引发的来源复核
pages: [concepts/group-identity-evidence, concepts/identity-authority,
  concepts/message-pipeline, concepts/model-error-contract, concepts/unread-capture-retry,
  symbols/queue-finish, tables/queue-batches, tables/queue-inbox]
```
### 提及残留登记引发的来源复核

#### 目标与背景

[raw/changes/2026-11-02-mention-picker-gating-residue](wechat-ui.md#doc-980ea358badbe6) 为了登记可认领的提及残留，改了两处被多个词条引用的来源文件：

- `src/wxbot/queue_store.py:21` 的 `FAILURE_DETAIL_FIELDS` 增加一个标量键 `mention_residue`。
- `src/wxbot/wechat/chat_window.py:392` 新增 `_draft_equal`，并让 `clear_owned_draft` 在清理前等待焦点。

这些改动不改变下列词条描述的批次状态机、身份解析或未读重试，但源码指纹变了；需要逐条对照代码复核并登记，否则巡检会一直报 `source-drift`。

#### 文件与代码位置

- `src/wxbot/queue_store.py:21` — 白名单只多一个键，集合仍是单行到 `:26`；`claim_batch`、`finish_batch_parts`、`_insert_delivery`、`_recompute_batch`、`capture`、`finish_delivery`、`retry_failed_deliveries`、`forget_session` 的行号与实现均未变。
- `src/wxbot/wechat/chat_window.py:392` — 新增 `_draft_equal`（只容忍尾随分隔空白）与 `clear_owned_draft` 内的 0.5 秒焦点等待；`Message.ref`（`:36`）、`_classify` 的诊断节流（`:246` 附近）、`read_bundle` 的未读读取（`:356` 附近）均未变。
- 受影响词条：[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-inbox](inbox.md#doc-6529d9966e604a)、[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)、[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)。

#### 接口与字段

这 8 个词条描述的 HTTP 契约、批量状态、身份字段和未读退避都没有变化。唯一新增的投递事件键 `mention_residue` 与草稿清理规则已在 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf) 和 [symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7) 记录，不在本记录重复。

#### 数据库与迁移

不适用：无 schema 变化；`mention_residue` 只是 `delivery_events.details` 的读时白名单键，`draft_text` 是既有列。

#### 前端消费点

不适用：管理台复用同一份白名单常量，新增键自动透出。

#### 测试与异步任务

复核依据是既有离线用例与本次新增的提及用例（`tests/unit/text/test_true_mentions.py`、`tests/unit/queue/*`、`tests/unit/wxbot/*`）；未新增定时任务。

#### 风险与回滚

复核结论是「无影响」：批次/身份/未读路径都不读取草稿所有权或 `mention_residue`。若后续把 `mention_residue` 用于自动重试判定，必须同时更新 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6) 与 [symbols/queue-store](queue-storage.md#doc-37f6245b143a25)，避免与 `manual_required` 的人工处置语义混用。
<!-- end-migrated-part: doc-989f2003dec3a1 -->
