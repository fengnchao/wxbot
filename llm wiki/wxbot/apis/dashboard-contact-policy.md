---
type: api
module: identity
summary: 联系人策略事务外校验、并发版本复查及未安装技能显式取消
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/identity/contact_admin.py
  line: 345
  anchor: 'def save(self, payload):'
- path: src/butler/identity/contact_admin.py
  line: 383
  anchor: validated_policy = None
- path: src/dashboard/http.py
  line: 168
  anchor: 'def _contact_admin(self):'
- path: src/dashboard/api/contacts.py
  line: 29
  anchor: 'def save(ctx):'
- path: src/butler/identity/contact_store.py
  line: 27
  anchor: 'def clean_policy(value):'
- path: web/src/components/ContactDialog.vue
  line: 372
  anchor: 'function submitPolicy()'
- path: web/src/components/ContactDialog.vue
  line: 546
  anchor: 'v-for="name in unavailableSkills"'
changes:
- raw/changes/2026-11-05-contact-policy-save
depends_on:
- modules/identity
- modules/dashboard
- modules/web
---
# 联系人策略保存

## 方法、路径与鉴权

POST /api/contacts 由 dashboard.api.contacts.save 接收（src/dashboard/api/contacts.py:29），仍要求可信本机同源、JSON 和 X-Wxbot-Contact-Action。属于 [[modules/dashboard]] 与 [[modules/identity]] 的管理操作，不是模型凭提示授予权限。

## 请求字段与响应

策略写入使用 action=person 或 conversation、id、整数 version、policy。policy 为 null（清除覆盖）或包含 role_skill、allowed_skills、heartbeat_enabled 的对象；结构与规范化来自 src/butler/identity/contact_store.py:27 clean_policy。角色必须属于当前安装目录的角色，技能必须是已安装工具；未知名称仍拒绝，并在错误中列出具体名字（src/dashboard/http.py:168）。没有新增字段或放宽授权。

成功返回完整联系人快照供前端替换；非法输入 400，版本冲突 409，表单保留错误供使用者处理（src/dashboard/api/contacts.py:29、web/src/contactState.js:132 submitDialog 与 :143 contactSave）。

## 实现链与锁边界

ContactDialog.submitPolicy → contactSave → POST /api/contacts → ContactAdmin.save。save 先用只读快照检查目标、版本并确定校验路由，关闭连接后调用目录验证器；然后开始写事务，重新读取并比较 version，再应用策略（src/butler/identity/contact_admin.py:383）。人物默认策略与会话覆盖使用同一边界；会话改名/profile 等仍用请求更新后的路由验证，心跳目的地约束仍在事务内检查。

目录验证会经 dashboard 的配置读取再次访问 DirectoryStore → ContactStore；原实现把验证放在 BEGIN IMMEDIATE 内，第二条连接再次申请写锁，导致超时回滚。事务外验证消除这条自锁链；验证期间其他保存若提交，新写事务必须报版本冲突，不能覆盖较新数据。

## 数据血缘

人物策略写 unified_contacts.payload.person_policies[id]；会话策略写 conversations[].policy；version 提交时增长（contact_store.py:122 _save）。无新表、字段或迁移。运行时工具仍由 SkillPolicyStore/ToolService 验证，不根据 UI 勾选直接执行。

## 前端与已有未安装技能

属于 [[modules/web]]，复用既有布局和 user-skill 原生复选框。技能目录加载后保留已有 allowed_skills，把目录里缺失的名字显示为“未安装”（ContactDialog.vue:137、:546）。默认不取消、不静默删除；使用者明确取消勾选后才从提交数组移除。保存按钮等待回执时显示“保存中…”，成功才关闭；重新打开从返回快照加载新策略。[[apis/index-tts]] 与 [[apis/dashboard-voice-assets]] 的授权、预设及音色协议未改。

## 测试与风险

tests/dashboard/test_contact_admin.py 的人物/会话同库目录验证回归在修复前均以 database is locked 失败，修复后可持久化并重新读取；并发保存回归保证旧请求冲突而非覆盖。现有非法目录、同源、版本和原子回滚测试继续执行。web/scripts/smoke.mjs 覆盖未安装技能保留、显式取消、保存等待和重新打开。

无消息发送、定时任务或后台消费者变更。需使用者自行重启管理台加载后端，刷新前端加载 dist；不自动重启服务，不改生产策略。回滚对应源码与 dist，无数据回滚或迁移。

来源 [[raw/changes/2026-11-05-contact-policy-save]]。
