---
type: change
title: 新消息补建联系人窗口与移除会话 IndexTTS 专区
pages:
- modules/identity
- concepts/message-pipeline
- symbols/butler-handle
- modules/web
- apis/index-tts
- apis/dashboard-contact-policy
- apis/dashboard-voice-assets
- apis/butler-handle
- concepts/development-baseline
- concepts/group-identity-evidence
- concepts/model-error-contract
- modules/butler
- modules/wiki
- symbols/butler-result
supersedes:
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
---
# 修改记录

## 目标与背景

私聊新消息可登记人物与身份，但缺失管理台私聊分类要求的窗口字段。删除后再次收到消息仍可能看不到联系人。补建缺失窗口，并移除「编辑窗口与收发设置」的 IndexTTS 授权和预设专区。对上面两条历史记录的更正仅涉及页面入口与其调用，后端接口与运行时语音行为仍按原契约。

## 文件与代码位置

- `src/butler/identity/user_registry.py:350` `enroll_conversation` 用既有业务库事务建立窗口。`src/butler/agent/core.py:181` `archive_group` 与 `:275` `_handle_request` 调用。
- `web/src/components/ContactDialog.vue:236` `submitConversation` 只提交窗口资料与语音回复设置；`:373` 语音回复 fieldset 仍在。`web/src/views/ContactsView.vue:152` `openConversation` 不再传专用的有效策略参数。`web/src/styles/contacts.css:28` 删除退场的专用样式。README 更新操作路径，`web/dist` 已重建。

## 接口与字段

不涉及新增 HTTP 路由或 DTO。正常 `/v1/handle`、流式处理和群归档补建窗口，`GET /api/contacts` 按现有字段投影。仅处理群归档的对方消息；历史快照 `/v1/users/observe`、心跳和专用 HTTP 转发不补建。原 `/api/tts-presets` 仍支持兼容客户端。

## 数据库与迁移

不涉及新表或迁移。`unified_contacts.payload.conversations` 补建唯一窗口名的条目，私聊取同库启用绑定的 `user_id` 作 `person_id`，群条目没有人物归属。采用窗口名与 default profile 的原回退路由，状态 `needs_route=true`，初始独立监听关闭、无订阅、无策略且不继承已有个人策略。复核与保存同事务，已有窗口包括停用、同名异类型窗口均保留。

## 前端消费点

联系人会话列表使用原 `conversations[]`，无需客户端补造记录。会话弹窗停止读取技能目录和预设接口，也停止提交网页预设或技能策略；AI 设置仍可单独保存技能授权。本地语音模式、音色绑定和异步保存的固定目标逻辑仍可用。旧网页预设按旧窗口名称保留，改名不再自动复制。

## 测试与异步任务

本地 `tests/butler/identity/test_identity_runtime.py` 先复现私聊和群聊缺窗口，再通过删除后补建、幂等、停用与历史快照隔离。目标离线套件 130 项、前端展示规则 8 项、build 和 smoke 通过。Hallmark 静态 0 FAIL、0 WARN，一条已有间距备注；浏览器进程启动失败。较广的 HTTP 回归受本机连接权限限制。无新增后台任务或定时任务。

## 风险与回滚

补建以实际采集的新消息为前提，全局监听关闭且未绑定窗口时不会从微信采集新消息。此次没有操作运行实例，加载需手动重启 Butler 和刷新管理台。回滚源码和前端构建即可停止补建，已写入的记录可在联系人管理中调整或删除。详见 [[impacts/2026-11-05-contact-enrollment-and-tts-ui]]。
