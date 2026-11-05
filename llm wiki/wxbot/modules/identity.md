---
type: module
module: identity
summary: 统一人物、窗口和成员绑定，身份能力由服务端签发
coverage: overview
last_verified: '2026-11-05'
sources:
- path: src/butler/identity/contact_store.py
  line: 37
  anchor: 'class ContactStore:'
- path: src/butler/identity/user_registry.py
  line: 24
  anchor: 'class UserRegistry:'
- path: src/butler/agent/tools.py
  line: 47
  anchor: def issue(
- path: src/butler/agent/tools.py
  line: 55
  anchor: def verify(
- path: src/butler/identity/user_registry.py
  line: 350
  anchor: def observe(
- path: src/butler/identity/user_registry.py
  line: 239
  anchor: def _learn_nickname(
- path: src/butler/identity/contact_admin.py
  line: 345
  anchor: 'def save(self, payload):'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-policy-save
---
# 联系人身份与权限

## 范围

`src/butler/identity/` 维护窗口联系人、统一人物、绑定与记忆归属；ContactStore 使用配置确定的业务库，UserRegistry 完成人物/绑定身份解析。

## 权限及关联

属于 [[modules/butler]]。ToolService.issue / verify 处理服务签发上下文，模型提示和同名/头像观察都不能授予工具权限。见 [[concepts/identity-authority]]。

## 群成员认人顺序

群成员按「已登记 member_key → 同群昵称 → 新建」认人，头像只补证据和展示。群目录后来学到的昵称会补到待命名档案上，管理员确认过的名字不被覆盖；同群同名且唯一时会并回既有档案。实测 dhash 无法区分同一个人和不同的人，不能用头像相似度防误并。规则与实测数据见 [[concepts/group-identity-evidence]]。

## 待建档

完整业务表、合并预览/版本摘要契约、用户 API/管理台消费点尚未在本批逐项建立；修改这些功能必须先查源码扩展，不能从概览推断字段。

## 代码依据

- `src/butler/identity/contact_store.py:37` — `class ContactStore:`
- `src/butler/identity/user_registry.py:24` — `class UserRegistry:`
- `src/butler/agent/tools.py:47` — `def issue(`
- `src/butler/agent/tools.py:55` — `def verify(`
- `src/butler/identity/user_registry.py:350` — `def observe(`
- `src/butler/identity/user_registry.py:239` — `def _learn_nickname(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


## 本次核对

[[raw/changes/2026-11-04-index-tts-skill]]：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [[apis/index-tts]]，其余已述契约未改。


## 联系人语音配置核对

[[raw/changes/2026-11-04-webui-preset-binding]]：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [[apis/index-tts]]。


图谱契约说明来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]。


## 策略保存复核（2026-11-05）

联系人策略保存的事务外目录校验、事务内版本复查及未安装技能的显式取消入口见 [[apis/dashboard-contact-policy]]。保留原角色与工具权限规则，无数据库迁移，不自动删除已有技能引用。来源 [[raw/changes/2026-11-05-contact-policy-save]]。
