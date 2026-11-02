---
type: concept
module: wxbot
summary: 窗口→收件→批次→Butler→分句→UI→只读投影
coverage: core
last_verified: '2026-11-02'
sources:
- path: src/wxbot/inbox.py
  line: 255
  anchor: def _capture(
- path: src/wxbot/queue_worker.py
  line: 141
  anchor: reply = self.router.handle_reply(
- path: src/wxbot/processor/butler.py
  line: 72
  anchor: body["msg_id"] = request_id
- path: src/butler/agent/core.py
  line: 304
  anchor: result.meta["msg_id"] = msg_id
- path: src/wxbot/wechat/chat_window.py
  line: 36
  anchor: "ref: str = ''"
- path: src/wxbot/ui_contract.py
  line: 56
  anchor: def persisted_rows(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch-core-emit
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-10-31-identity-placeholder-names
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-residue-reverify
---
# 消息主链路与字段传递

## 路径

[[modules/wxbot]] MainInbox → [[tables/queue-inbox]] → prepare 生成 [[tables/queue-batches]] → [[symbols/model-worker]] → Router → [[symbols/butler-processor]] → [[apis/butler-handle]] / [[apis/butler-handle-stream]] → [[symbols/butler-handle]] / [[symbols/butler-result]] → [[symbols/queue-finish]] → [[tables/queue-outbox]] → UI 发件器。

## 字段血缘与契约

- contact：UI 窗口标题 → inbox/batches → 请求 contact → 会话解析；不是微信账号/人物显示名。
- batches.id → worker.request_id → HTTP msg_id → Butler trace / meta.msg_id；decoder 可核对回包 ID，管理台按 request_id 关联。
- member_key/member_name/avatar：观察数据 → 批次/请求；服务端解析确认后返回 mention_name，第一分句才携带 @ 目标。见 [[concepts/identity-authority]]。
- Result.reply / reply_parts → wxbot Reply → outbox.text/part_seq；reply_complete 与投递 state 不同，见 [[concepts/delivery-state]]。
- 快照引用只在一次界面读取内有效：`Message.ref` 不落库，`observations.snapshot` 与 `outbox.baseline` 都保存去引用版本；重启后只能按正文对齐，不能当跨进程指针用。

## 反向消费

[[apis/dashboard-workflow]] 和 [[apis/dashboard-queue]] 只读队列/事件，再由 [[modules/web]] 展示。浏览器不直接访问 Butler 处理端点。主动推送会绕过收件/模型链路并允许 outbox.batch_id=NULL，不应强行补造批次。

模型来源在流转日志里按接入方式展示（deepseek 而不是 openai），字段仍走既有 trace，不新增队列列。

另有旁路支线：[[symbols/butler-handle]] 的 `_record_episode`（`src/butler/agent/core.py:318`）在请求返回前把本轮用户原文与回复写进 [[tables/knowledge-vault]]（`cfg.data_path()/'knowledge'` 下，一人一个 vault，落到 `p-<slug>/vault/对话/YYYY-MM-DD.md`，与队列库无关）。它只读不写队列状态，失败不影响主链路；写入同时还重画该 vault 的 `index.md` 中心索引页（同一轮多一次文件写）。管理台侧的只读消费见 [[apis/dashboard-knowledge]]。

## 代码依据

- `src/butler/agent/core.py:318` — `def _record_episode(self, c, contact_name, channel_type, text, reply, outcome):`
- `src/butler/agent/core.py:324` — `self.knowledge.record(`
- `src/wxbot/inbox.py:255` — `def _capture(`
- `src/wxbot/queue_worker.py:141` — `reply = self.router.handle_reply(`
- `src/wxbot/processor/butler.py:72` — `body["msg_id"] = request_id`
- `src/butler/agent/core.py:301` — `result.meta["msg_id"] = msg_id`
- `src/wxbot/wechat/chat_window.py:36` — `ref: str = ''`
- `src/wxbot/ui_contract.py:56` — `def persisted_rows(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch-core-emit]]

[[raw/changes/2026-11-01-knowledge-episodes]]

[[raw/changes/2026-11-01-knowledge-sharding]]

[[raw/changes/2026-11-01-mention-fallback-unread-retry]]

[[raw/changes/2026-11-01-knowledge-atlas-index]]

[[raw/changes/2026-11-02-ui-snapshot-ref-contract]]

[[raw/changes/2026-11-02-mention-residue-reverify]]
