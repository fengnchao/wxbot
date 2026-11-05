---
type: change
title: 为停用的群成员身份增加启用按钮
pages:
- apis/dashboard-contact-policy
- apis/index-tts
- modules/identity
- modules/web
---
# 修改记录

## 目标与背景

为停用的单条群身份提供直接启用动作，避免编辑绑定同时确认身份或改变整个人物的开关。

## 文件与代码位置

- `src/butler/identity/contact_admin.py:360,508` 注册 `binding_enable` 并和停用复用绑定归属校验。
- `web/src/views/ContactsView.vue:270,452,460` 增加启用处理、请求等待和按钮。`web/dist` 已重新构建。

## 接口与字段

`POST /api/contacts` 新增 `action=binding_enable`，提交人物 `id`、`binding_id`、全局 `version`。沿用本机同源确认、旧版本 409 与完整快照响应。服务端拒绝不属于该人物的绑定及非群绑定。

## 数据库与迁移

在现有业务库事务中写 `user_bindings.enabled=1`、推进绑定和联系人版本，并在 `user_audit` 记录 `enabled`。保留昵称、确认标记、识别证据与窗口开关。不涉及新增表、字段或迁移。

## 前端消费点

群成员列表、个人群身份和折叠绑定列表均可启用停用的单条记录。显示启用中，阻止重复提交；成功采用服务端快照，失败沿用页面错误提示。

## 测试与异步任务

临时库的 48 项联系人和身份回归以及前端 build、smoke 通过。测试覆盖保留未确认状态、拒绝错归属及旧版本、等待回执与启用后刷新投影。Hallmark 静态 0 FAIL、0 WARN，浏览器进程无法启动。不涉及新增后台任务。

## 风险与回滚

启用会让此群绑定重新参与之后的识别，仍受原有确认与权限规则约束。回滚源码和 dist 即移除入口与新动作，不需要回滚数据库。详见 [[impacts/2026-11-05-enable-group-binding]]。
