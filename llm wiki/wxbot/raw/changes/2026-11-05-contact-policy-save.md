---
type: change
title: 修复联系人策略保存锁等待与不可见旧技能
pages:
- apis/dashboard-contact-policy
- modules/identity
- modules/dashboard
- modules/web
- apis/index-tts
- apis/dashboard-voice-assets
- concepts/development-baseline
---
# 修复联系人策略保存锁等待与不可见旧技能

## 目标与背景

修复“保存策略”长时间等待、关闭后重新打开未生效。根因是 ContactAdmin 写事务内的目录验证回调重新读取同一联系人库，经 ContactStore 构造函数申请第二把写锁，等待超时后回滚。另一个阻塞是已保存但未安装的技能被 UI 隐藏，服务器仍严格拒绝该值。详见 [[impacts/2026-11-05-contact-policy-save]]。

## 文件与代码位置

- src/butler/identity/contact_admin.py:383：事务外只读快照确定校验路由并完成目录验证，事务内复查版本、目标和心跳约束；人物/会话共用。
- src/dashboard/http.py:181：未知技能错误包含具体名称和明确处理办法，仍严格拒绝。
- web/src/components/ContactDialog.vue:137、:546、:554：保留并显示未安装技能，使用者明确取消才移除；显示保存中状态。web/dist 已随源码重新构建。
- tests/dashboard/test_contact_admin.py:79、:107 与 web/scripts/smoke.mjs:695：同库读取、并发旧写、未安装技能、保存后重开回归。
- 图谱新建 [[apis/dashboard-contact-policy]] 并与相关模块/接口关联，更新移动的 ContactDialog 来源行号。开发基线页只复核 http 来源摘要，原基线事实不变。

## 接口与字段

无新增 API/DTO。继续使用 POST /api/contacts 的 action/id/version/policy，policy 结构和服务端角色/工具验证规则不变。非法策略返回 400，版本冲突返回 409，成功返回完整快照。未安装技能不自动移除、不授予执行能力。

## 数据库与迁移

无数据库迁移。仍写 unified_contacts.payload 的 person_policies 或 conversations[].policy，并增加 version；预校验与提交之间变化通过事务内版本检查拒绝。未写生产配置或权限数据。

## 前端消费点

ContactDialog.submitPolicy → contactState.contactSave；Vue 3/Vite、现有布局、字段/事件/路由和主题令牌保持。原生复选框继承共享 focus-visible/disabled 样式，无新增动画；未安装项初始勾选，只有明确取消才改变请求。

## 测试与异步任务

- TDD：3 个临时 SQLite 用例在修复前以 database is locked 失败；修复后联系人管理 16 项测试通过，含人物/会话保存重读、并发版本冲突及同源/原子性。
- npm --prefix web run build / smoke 通过；新增 UI 回归先以缺少显式取消入口失败，再验证未安装技能保留/取消、保存中和保存重开。
- compileall 与 git diff --check 通过（Git 提示已有文件的 LF/CRLF 转换）。
- 全量离线 pytest 有 4 项失败：test_portable_install.py::test_plugin_references_and_protocol_are_self_contained（技能数量预期 6、实际 7）；test_queue_admin.py::test_multipart_cli_sent_and_retry_preserve_other_parts；test_queue_store.py::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker；test_typing.py::test_typing_steps_keep_half_second_between_batches_and_one_final_enter。分别在安装、队列状态和输入节奏路径，不改这些业务。
- Hallmark component 静态检查单独扫描组件时因共享样式未纳入报 focus/active/disabled；连同实际共享样式、实际 /app/?tab=contacts 渲染后，检查产出 5 张图，报告共享主题/现有页面 116 FAIL、3 REFLEX、2 WARN。无新增 CSS；未扩大到旧主题清理，不声称 Hallmark 全通过。新弹窗逻辑由假数据 smoke 验证，渲染检查未操作生产弹窗。
- 无新增或更改异步任务。所有测试使用临时库/假 HTTP/假投递，不访问真实剪贴板，不发送微信。

## 风险与回滚

预校验不持写锁；写入仍检查版本，避免并发覆盖。未放宽角色/工具目录边界，不绕过服务签发能力。保留工作树原有未提交修改。回滚本次源码和 dist 即可，无迁移。管理台进程需使用者自行重启、页面需刷新后加载；本次未重启服务，未移除生产权限记录，也未发送之前请求的语音。
