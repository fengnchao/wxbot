---
type: change
title: 联系人配置加入 IndexTTS 授权与语音设置联动
pages:
- modules/dashboard
- modules/web
- modules/wiki
- apis/dashboard-voice-assets
- apis/index-tts
- concepts/development-baseline
supersedes:
- raw/changes/2026-11-04-index-tts-skill
---
# 联系人配置中的 IndexTTS

## 目标与背景

用户要求将已实现的 IndexTTS 能力加入 Web 联系人配置。保留现有管理台布局和原角色/通用技能入口，在会话设置提供明确授权开关，与语音模式同屏。本条只补充并更正 supersedes 记录的“前端不适用”部分；既有生成工具参数/权限/投递协议不变，旧 raw 不改写。

## 文件与代码位置

- web/src/components/ContactDialog.vue：conversation 模式读取技能目录、显示 indexTtsEnabled 开关；沿当前策略只增删 index-tts；语音读取状态与按变化字段保存，部分保存失败留窗，用返回版本重试。saveVoiceBinding 重命名时复制 mode/asset_id 到新键，未重命名的模式修改不清参考音。
- web/src/views/ContactsView.vue：openConversation 调用现有 effectivePolicy，把当前有效策略传给弹窗，尊重 inherit_person_policy=false。
- web/src/styles/contacts.css：只为本次控件补禁用、边框对比度、提示色与标签宽度，沿既有令牌/焦点样式，不改全站主题。
- web/scripts/smoke.mjs：实际构建 Vue 的授权、继承、失败重试、变化字段、递增版本和重命名回归；web/dist 包含对应构建。
- README.md、关联图谱与影响报告记录使用路径与契约，具体稳定来源见 [[apis/index-tts]] sources。

## 接口与字段

不新增 HTTP 接口或后端字段。使用 GET /api/skills 和 /api/voice-bindings，POST /api/contacts 的原 policy.allowed_skills/role_skill/heartbeat_enabled/version；沿原确认头。只有授权开关变化才发送完整保留后的策略，未变化不建立覆盖。

原 POST /api/voice-assets action=bind 仅发送改变的 mode 或 asset_id，重命名例外复制当前值。读取失败不以默认空值回写；目录不可用/角色未设不允许更改授权。姓名/授权先保存成功而语音保存失败时明确提示部分保存，保留弹窗，使用新 version 重试。跨源操作不宣称原子性。

## 数据库与迁移

不适用：无新表/列/迁移。仍分别由既有联系人存储及语音 TOML 保存。仍使用服务端校验；没有自动修改真实用户配置、凭证、默认设备或运行数据。

## 前端消费点

路径为联系人 → 基本资料 → 编辑窗口与收发设置 → IndexTTS 文字转语音。AI 设置的允许功能列表也保留技能并显示中文名称。网页预设音色在聊天调用时指定，不新增联系人默认预设，不改变其他生成默认值。

语音总开关关闭、模式关闭、技能不可用、缺少角色分别显示说明；配置在加载中/保存中禁用相应操作，错误可重试。自动回复音色与网页预设的绑定条件分开说明。

## 测试与异步任务

先新增 DOM 烟测观察缺少控件失败，再实现。npm build/smoke 通过，覆盖保留其他授权、未改不写、模式不清旧绑定、目录失败重试、部分保存留窗/不重复改策略、真实递增 version、继承策略与会话重命名。独立审阅复现重命名丢绑定 P2，补失败→通过回归后复核闭环，未发现其余 P1/P2。

Hallmark component/app 静态联检新组件与共享样式为 0 FAIL/0 WARN，保留已有 spacing NOTE。独立只读假数据预览使用实际 /app/?tab=contacts 和构建资源，运行 Hallmark 多尺寸渲染并查看截图；新表单边缘对比度/焦点/375px 无横向溢出检查通过。全页渲染仍报告背景旧控件低对比度、旧卡片高度/字号、导航字色/字重等发现，未扩大修整旧页面。没有新增定时/后台业务任务，没有发送新的真实消息。

## 风险与回滚

授权开关不自动开启语音总开关/联系人模式、不创建默认角色。继承策略变化会保存为会话覆盖，并明确提示。旧语音配置以名字作键，重命名继续复制到新键并保留旧键，后续独立清理不在本次范围。回退本次前端文件与 dist 可移除入口，原 AI/语音配置入口仍可管理已有设置。既有服务不重启；前端刷新加载新构建。
