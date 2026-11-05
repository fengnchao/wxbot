---
type: impact
status: completed
date: 2026-11-05
---
# 启用停用的群成员身份

## 需求与现有路径

核对 [[modules/identity]]、[[modules/web]]、[[apis/dashboard-contact-policy]] 与 [[concepts/group-identity-evidence]]。联系人已能编辑群绑定，但现有 `binding` 动作会同时确认身份与昵称。`src/butler/identity/contact_admin.py:507` 的 `binding_disable` 则只改开关，适合作为启用动作的对称入口。

## 文件、调用与数据

- `web/src/views/ContactsView.vue:269,442`：群成员列表、联系人群身份及折叠绑定列表提供「启用」，沿用 `web/src/contactState.js:45` 的请求与版本冲突反馈。
- `src/butler/identity/contact_admin.py:345,507`：在 `POST /api/contacts` 下添加 `binding_enable`，要求人物 `id`、`binding_id`、`version`，沿用本机同源确认和完整快照响应。事务中核对群绑定及人物归属，只写 `user_bindings.enabled/version`、`user_audit` 和现有联系人版本。保留确认标记、昵称和会话开关，无迁移。

## 验证与回滚

临时业务库测试仅恢复目标群绑定、保留身份状态、拒绝错归属和旧版本；假数据 smoke 测试启用按钮及刷新。没有新增异步任务。回滚源文件和 dist 即移除按钮与动作，已有开关仍可经现有管理流程调整。

实际改动见 [[raw/changes/2026-11-05-enable-group-binding]]。
