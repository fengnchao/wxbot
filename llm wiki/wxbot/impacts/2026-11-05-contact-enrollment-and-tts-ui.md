---
type: impact
status: draft
date: 2026-11-05
---
# 新消息补建会话与移除会话 IndexTTS 专区

## 需求关键词与图谱命中

查询 contact_store、contact_admin、IndexTTS、dashboard-contact-policy，核对 [[modules/identity]]、[[concepts/message-pipeline]]、[[apis/dashboard-contact-policy]]、[[apis/index-tts]]、[[modules/web]]。图谱缺少自动身份登记和窗口管理投影的区别。`user_registry.py:275` 私聊观察只创建人物/绑定，`contact_admin.py:294` 从 `conversations` 投影窗口，`contactPresentation.js:26` 据此筛选私聊。只有私聊绑定的记录甚至可能没有前端待确认原因。

## 要改的文件、符号与调用方

- `src/butler/agent/core.py:181,273`：群聊归档（含静默批次）及正常处理入站消息时补建，沿用身份解析结果。启动快照走 `observe_users`，心跳走 `heartbeat_contact`，两者不补建窗口。专用 HTTP 转发继续绕开身份流程。
- `src/butler/identity/user_registry.py:350` 附近：同一业务库事务内检查已存在窗口和启用的私聊绑定，复用 `src/butler/identity/contact_store.py:122` 提交。
- `web/src/components/ContactDialog.vue:155,317,477`、`web/src/views/ContactsView.vue:152`、`web/src/styles/contacts.css:28`：移除会话专用授权和预设区及其请求，保留 AI 设置与语音回复控件，按 Hallmark 的现有管理台局部修改范围处理。

## 接口、字段与风险

HTTP 请求和响应格式保持兼容。现有 `GET /api/contacts` 返回补建后的会话。`unified_contacts.payload.conversations` 使用实际窗口名称、默认路由字段、私聊 `person_id` 与 `needs_route` 标记。复用业务库的版本控制，无迁移，不写手工监听、订阅或技能授权。原 `GET/POST /api/tts-presets` 与保存的预设继续供已有运行时使用，重命名会话时本弹窗不再复制旧名称的网页预设。已有本地音色资产保存与改名仍走原接口。

## 验证、异步任务与回滚

在临时库验证删除、重收、幂等、停用、群聊静默归档；用管理台假数据验证无预设请求且普通语音设置仍可保存。沿用现有队列，不新增后台任务。回滚源码和 dist 即停止补建，已经登记的会话可从联系人页面管理。
