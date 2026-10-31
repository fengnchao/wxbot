---
type: change
title: 截图占位名不再当作群昵称重放
pages:
- concepts/group-identity-evidence
- concepts/message-pipeline
- modules/wxbot
---
# 截图占位名不再当作群昵称重放

## 目标与背景

[[raw/changes/2026-10-31-group-identity-nickname]] 落地后清空了 5 条待命名档案，随后用真实数据库跑启动重放仿真，发现还会再冒两条：`待命名-178c1373d18d` 与 `待命名-22591d351243`。

原因不在头像，而在名字的判定口径。启动重放读的是 `observations.snapshot` 里的截图原始行，截图读不出真名时写的是 `成员-<ID前8位>`。它是非空字符串，能穿过「没有昵称就不重放」的守卫；而 butler 端 `contact_identity.normalize_name` 把 `成员-` 前缀视为无名，于是 `named=False`，转而新建 `待命名-<hash>`。同一件事两边口径不一致，档案就来回长。

完整诊断与清理记录见 [[impacts/2026-10-31-group-identity-nickname]]。

## 文件与代码位置

- `src/wxbot/inbox.py:23` 新增 `member_nickname`：`成员-<ID前8位>` 与空名字等价。
- `src/wxbot/inbox.py:109` `sync_users` 的两个循环都改用它取昵称，快照分支不再把占位名上送。
- `src/wxbot/inbox.py:253` `_capture` 改用同一函数，去掉原来内联的判断，两处口径合一。
- 规则写进 [[concepts/group-identity-evidence]] 与 [[modules/wxbot]]；顺带修正 `inbox.py` 增行后 [[concepts/message-pipeline]] 的 `_capture` 行号。

## 接口与字段

无接口改动。`POST /api/users/observe` 的 `member_name` 可能为空——这正是本次要的效果：宁可等下一次发言补真名，也不要用占位名建档案。

## 数据库与迁移

无结构变更，无迁移。

## 前端消费点

无前端改动。管理台不再出现新的 `待命名-` 行。

## 测试与异步任务

`tests/butler/identity` + `tests/unit/wxbot` 共 298 项全过。新增 `test_startup_identity_sync_does_not_treat_a_screenshot_placeholder_as_a_name`。

用真实数据库副本跑完整重放（真实 `MainInbox.sync_users` + `UserRegistry.observe`）：`user_profiles` 23→23、`user_bindings` 13→13，零新建。此前一版仿真拿 `user_bindings.nickname` 当昵称来源，而真实来源是 `unified_contacts.aliases`，因此误报两个新建；这个坑记在影响面报告里。

## 风险与回滚

真名一直读不出来的成员不会被启动重放建档，要等他下次发言。这是有意的：占位名建出来的档案无法核对。回滚只需撤销 `inbox.py` 三处改动。
