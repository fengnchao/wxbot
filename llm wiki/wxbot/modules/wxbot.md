---
type: module
module: wxbot
summary: 微信 UI 主线程与不接触 UI 的模型队列线程
coverage: overview
last_verified: 2026-11-03
sources:
- path: src/wxbot/inbox.py
  line: 45
  anchor: 'class MainInbox:'
- path: src/wxbot/queue_worker.py
  line: 25
  anchor: 'class ModelWorker:'
- path: src/wxbot/queue_store.py
  line: 91
  anchor: class QueueStore(
- path: src/wxbot/main.py
  line: 29
  anchor: def build_processor(
- path: src/wxbot/inbox.py
  line: 124
  anchor: def sync_users(
- path: src/wxbot/queue_store.py
  line: 192
  anchor: def identity_observations(
- path: src/wxbot/ui_contract.py
  line: 65
  anchor: 'class Snapshot:'
- path: src/wxbot/wechat/locator.py
  line: 9
  anchor: def wait_until(
- path: src/wxbot/wechat/chat_window.py
  line: 36
  anchor: 'ref: str = '''''
changes:
- raw/changes/2026-11-03-feat-voice-001-virtual-mic
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-10-31-identity-placeholder-names
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
depends_on:
- modules/common
---
# wxbot UI 与持久队列

## 职责与范围

`src/wxbot/` 负责窗口、轮询、差分、收发队列及微信发送。`MainInbox` 在 UI 主线程收集消息，[[symbols/model-worker]] 在后台调用模型，UI 操作不能进入模型线程。

## 入口、依赖和数据

入口 `src/wxbot/main.py`。消息持久化在 [[symbols/queue-store]]，核心表 [[tables/queue-inbox]]、[[tables/queue-batches]]、[[tables/queue-outbox]]；数据库路径由 queue_database(cfg) 解析，不从图谱读取真实库。

模型适配通过 processor.router.Router；Butler 适配是 [[symbols/butler-processor]]，消费 [[apis/butler-handle]] / [[apis/butler-handle-stream]]。主动推送入口属于 outbound 服务，详细契约待建档。

## 影响边界

改队列字段需检查 [[modules/dashboard]] 的只读 SQL 和 [[modules/web]] 展示。改分句/流式协议需检查 [[symbols/queue-finish]]、[[concepts/delivery-state]] 及 [[concepts/message-pipeline]]。用户自己重启服务，离线验证不能发送真人微信。

## 采集与提及

未读任务只在采集成（`_capture`）时清除；读不到可采内容的未读按指数退避，达到 `[bot].unread_give_up_attempts`（默认 5）后放弃并清掉 `pending_sessions`，否则同一行记录会让 `prepare` 永远跳过该联系人。细节见 [[concepts/unread-capture-retry]]。

群聊 @ 提及由 [[symbols/mention-selection]] 完成：先等候选成员面板出现再输入昵称，候选不唯一或昵称不可信时回退为不带 @ 的纯正文；回退清理只能使用 uiautomation `SpecialKeyNames` 里声明过的键。面板在 `wechat.mention.open_timeout`（默认 1 秒）内没出现时只删除自己的 `@`，不会把昵称写成普通文字。失败后读回仍能证明是本会话输入的字面 `@...` 时，登记为 `outbox.draft_text`（`mention_residue=true`），下一次投递前自动清理，避免后续消息一直 `draft_conflict`。

## 快照与引用

一次界面读取就是一个快照，每行带只属于这次读取的引用（`Message.ref`，来自控件运行期标识）。发件确认、会话切换后的就绪判定都不再依赖固定 sleep，而是「重读一次再比较」：条件等待由 `wechat/locator.wait_until` 提供，始终带超时上限。引用缺失、行数为空或被复用（不唯一）时显式降级为正文对齐，降级事实写进 `delivery_events.details` 的 `confirm_evidence` / `ref_available`；确认规则与失败码见 [[concepts/delivery-state]]。引用不落库，`observations.snapshot` 与 `outbox.baseline` 只保存去引用版本。

## 启动时的身份补登

`MainInbox.sync_users` 只重放头像证据，不重放历史消息正文，也不建回复。重放时丢弃空白头像（遮挡时抓到的纯色块）和没有昵称的群成员观测：这两类建不出可核对的人，只会在每次启动时多出一条「待命名」。昵称取群目录当前映射，而不是入库那一刻的快照；截图给不出真名时的占位名（`成员-<ID前8位>`）也当作无名，否则照样建出待命名档案。见 [[concepts/group-identity-evidence]]。

## 代码依据

- `src/wxbot/inbox.py:45` — `class MainInbox:`
- `src/wxbot/queue_worker.py:25` — `class ModelWorker:`
- `src/wxbot/queue_store.py:91` — `class QueueStore(`
- `src/wxbot/main.py:29` — `def build_processor(`
- `src/wxbot/inbox.py:23` — `def member_nickname(`
- `src/wxbot/inbox.py:111` — `def sync_users(`
- `src/wxbot/queue_store.py:192` — `def identity_observations(`
- `src/wxbot/ui_contract.py:65` — `class Snapshot:`
- `src/wxbot/wechat/locator.py:9` — `def wait_until(`
- `src/wxbot/wechat/chat_window.py:36` — `ref: str = ''`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

## 统一模型通道

有 installation 配置的安装仅允许 model.backend=butler；旧 direct 安装需显式 migrate。模型选择由 Butler 管理，见 [[modules/models]]。


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-11-02-ui-snapshot-ref-contract]]

[[raw/changes/2026-11-02-mention-picker-gating-residue]]

## 变更

- 2026-11-03: FEAT-VOICE-001 P1 outbox kind=voice（虚拟麦+RALT）；见 [[raw/changes/2026-11-03-feat-voice-001-virtual-mic]]
