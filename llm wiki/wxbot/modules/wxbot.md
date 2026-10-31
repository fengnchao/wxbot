---
type: module
module: wxbot
summary: 微信 UI 主线程与不接触 UI 的模型队列线程
coverage: overview
last_verified: '2026-10-31'
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
  line: 109
  anchor: def sync_users(
- path: src/wxbot/queue_store.py
  line: 192
  anchor: def identity_observations(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-10-31-identity-placeholder-names
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

## 启动时的身份补登

`MainInbox.sync_users` 只重放头像证据，不重放历史消息正文，也不建回复。重放时丢弃空白头像（遮挡时抓到的纯色块）和没有昵称的群成员观测：这两类建不出可核对的人，只会在每次启动时多出一条「待命名」。昵称取群目录当前映射，而不是入库那一刻的快照；截图给不出真名时的占位名（`成员-<ID前8位>`）也当作无名，否则照样建出待命名档案。见 [[concepts/group-identity-evidence]]。

## 代码依据

- `src/wxbot/inbox.py:45` — `class MainInbox:`
- `src/wxbot/queue_worker.py:25` — `class ModelWorker:`
- `src/wxbot/queue_store.py:91` — `class QueueStore(`
- `src/wxbot/main.py:29` — `def build_processor(`
- `src/wxbot/inbox.py:23` — `def member_nickname(`
- `src/wxbot/inbox.py:109` — `def sync_users(`
- `src/wxbot/queue_store.py:192` — `def identity_observations(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

## 统一模型通道

有 installation 配置的安装仅允许 model.backend=butler；旧 direct 安装需显式 migrate。模型选择由 Butler 管理，见 [[modules/models]]。


[[raw/changes/2026-10-31-switchable-models]]
