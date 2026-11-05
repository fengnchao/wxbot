---
type: impact
status: verified
date: '2026-11-04'
---
# 联系人配置中的 IndexTTS

## 需求与方案

延续已实现的文字/预设工具，在 Web 联系人的会话设置中提供可见的 IndexTTS 授权开关，和已有语音模式一起配置。保留现有页面布局、角色策略入口、音色资产绑定和所有收发字段。工具调用仍传文字与预设名，不新增联系人默认预设或隐式改变高级生成参数。

## 文件与调用方

`web/src/components/ContactDialog.vue` 的 conversation 模式增加授权状态/加载错误/重试，复用 /api/skills 验证技能存在；`web/src/views/ContactsView.vue` 的 openConversation 传递已有生效策略，避免误用或覆盖继承策略。web/scripts/smoke.mjs 用实际构建组件验证保存请求与异常状态。样式复用现有表单和 theme.css，按 Hallmark component/app scope 原位修改。

## 契约与血缘

现有 GET /api/skills、GET /api/voice-bindings、POST /api/contacts（X-Wxbot-Contact-Action）、POST /api/voice-assets bind（X-Wxbot-Voice-Action）保持原 schema。只有开关确实改变才更新该会话 policy.allowed_skills，并保留 role_skill/heartbeat_enabled/其他技能；继承策略转换为明确会话覆盖前给出说明。原语音模式、资产保持正交，网页预设路径不需要资产绑定。读取失败不提交对应默认值，提交成功后才关闭弹窗；多步骤部分失败必须告知已保存范围。

业务验证仍在 ContactAdmin._policy 与服务端技能目录；前端勾选不绕过权限。无新表/列/迁移，无模型后端变更，无自动服务重启，无额外真实消息发送。角色/功能原可在 AI 设置中修改，该入口保留。

## 实施与验证计划

1. 新增实际 Vue 构建烟测：授权控件存在、保存仅改变 IndexTTS、保留其他字段、未改不写策略。
2. 实现弹窗/入口，验证加载、错误/重试、未配置角色、继承提示，防止未读完就保存。
3. npm build/smoke，Hallmark 指定 Vue 文件静态检查及可用时独立预览渲染；不重启已有服务。
4. 复核与追加 raw，更新关联图谱 source/契约并 ingest/lint。保留工作区此前功能和文档修改。

## 风险与回滚

联系人策略和语音模式原来分属联系人数据/配置文件，不能声称跨源原子提交；遇到部分失败保持弹窗并说明已保存/待保存，使用刷新后的版本重试，不重复扩大授权。新控件默认不自动开启总语音/联系人模式或新增默认角色。回滚本次前端源与 dist 即移除新入口，已有设置继续由原入口管理。

## 完成验证

- npm build/smoke 通过，覆盖实际 Vue 的授权保留、未改不写、技能失败重试、部分保存与真正递增的响应版本、继承来源、会话重命名复制语音模式/资产。独立审阅的重命名 P2 先复现失败、修复后闭环。
- Hallmark 静态组件/页面联检无 FAIL/WARN，既有 spacing NOTE 保留。对实际 /app/?tab=contacts 只读假数据预览运行多尺寸渲染并查看截图；新输入/复选框/下拉边缘对比度 5.16-5.80，键盘焦点 2px，375px 弹窗 clientWidth=scrollWidth=333。全页渲染仍有背景旧控件、字号、旧卡片等发现，未扩大修改。
- 新构建保存在 web/dist；未改真实用户设置/设备或自动重启服务，无额外真人消息。图谱记录 [[raw/changes/2026-11-04-contact-index-tts]] 入库 6 页，lint 仅余本任务前的 4 项旧待办。
