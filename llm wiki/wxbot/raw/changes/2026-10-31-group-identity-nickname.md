---
type: change
title: 群成员身份改用昵称优先，头像只作证据
pages:
- concepts/group-identity-evidence
- concepts/identity-authority
- concepts/delivery-state
- concepts/message-pipeline
- modules/common
- modules/identity
- modules/wxbot
- symbols/queue-finish
- symbols/queue-store
- tables/queue-batches
- tables/queue-inbox
- tables/queue-outbox
---
# 群成员身份改用昵称优先，头像只作证据

## 目标与背景

诊断「每次启动 wxbot 就多出几条待命名联系人、还没有头像」时查到四层原因：启动重放把 `inbox` 里的头像证据反复上送；上送用的是入库那一刻的昵称快照，群目录后来学到的名字不回填；空白截图（遮挡窗口）被当成合法证据永久重放；butler 只拿头像 hash 当身份标识。改法是让群成员按「已登记 member_key → 同群昵称 → 新建」认人，头像退为展示证据。完整诊断与实测数据见 [[impacts/2026-10-31-group-identity-nickname]]。

## 文件与代码位置

- `src/common/avatar_identity.py:57` 新增 `avatar_is_informative` 与 `BLANK_AVATAR_COLORS`。
- `src/wxbot/wechat/chat_window.py:236` `_runtime_avatar` 在源头丢弃空白块。
- `src/wxbot/queue_store.py:192` `identity_observations` 去掉 base64 长度启发式。
- `src/wxbot/inbox.py:103` `sync_users` 补昵称、丢空白头像、跳过无名观测。
- `src/butler/identity/user_registry.py:355` `observe` 与新增的 `:244` `_learn_nickname`。
- 规则与实测边界写进新建的 [[concepts/group-identity-evidence]]，并同步 [[modules/common]]、[[modules/identity]]、[[modules/wxbot]]、[[concepts/identity-authority]]。
- 顺带修正 [[concepts/delivery-state]]、[[concepts/message-pipeline]]、[[symbols/queue-finish]]、[[symbols/queue-store]]、[[tables/queue-batches]]、[[tables/queue-inbox]]、[[tables/queue-outbox]] 里已经过期的 `queue_store.py` / `inbox.py` 来源行号（此前队列改动留下的偏移，`wiki.py lint` 一直报 source-anchor）。

## 接口与字段

`POST /api/users/observe` 字段不变，只是 `avatar` 可能为空、`member_name` 更完整。`GET /api/contacts` 的 `avatar` 语义不变。没有新增或删除 HTTP 接口。

## 数据库与迁移

无结构变更。只新增 `user_audit` 动作 `nickname_learned` 与 `avatar_alias`。现有 5 条 `待命名-*` 与 `inbox` 里的空白头像证据需要一次性清理，属于运维动作，需单独授权后执行；清理后重放不会再把它们建回来。

## 前端消费点

无前端代码改动。管理台联系人列表「头像不显示」的根因之一（待命名档案 `identity_confirmed=0` 拿不到头像）随昵称补全自动缓解，不需要改 `src/dashboard/` 或 `web/`。

## 测试与异步任务

`tests/butler/identity` + `tests/unit/wxbot` 共 297 项全过。新增用例：空白块拒绝、3 色图形头像保留、归一化后空白块仍为空、启动重放跳过无名群成员观测。第一版判据是「颜色数 ≥64」，被测试实测证伪（3 色 fixture 被误杀），已改为只拒绝颜色数 ≤2；亮度标准差与 dhash 位数实测同样无区分度，记录在词条里避免以后重犯。

全套 `tests` 仍有 3 条与本次无关的旧失败：`test_queue_admin` 与 `test_queue_store` 的批次状态被判成 `done`、`test_typing` 的时序断言。本次没有触碰 `_recompute_batch` 与输入时序，属于既有问题，未在本记录内修复。

## 风险与回滚

同群两个人用完全相同的昵称会被并成一条，这是有意的取舍：dhash 实测无法区分同一个人和不同的人。管理员确认过的昵称不会被群昵称覆盖；同名冲突仍走 `ambiguous`。回滚只需撤销上述 5 处改动，数据库无结构变更。
