---
type: module
module: identity
summary: 统一人物、窗口和成员绑定，身份能力由服务端签发
coverage: overview
last_verified: '2026-10-31'
sources:
- path: src/butler/identity/contact_store.py
  line: 37
  anchor: 'class ContactStore:'
- path: src/butler/identity/user_registry.py
  line: 25
  anchor: 'class UserRegistry:'
- path: src/butler/agent/tools.py
  line: 47
  anchor: def issue(
- path: src/butler/agent/tools.py
  line: 56
  anchor: def verify(
- path: src/butler/identity/user_registry.py
  line: 355
  anchor: def observe(
- path: src/butler/identity/user_registry.py
  line: 244
  anchor: def _learn_nickname(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
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
- `src/butler/identity/user_registry.py:25` — `class UserRegistry:`
- `src/butler/agent/tools.py:47` — `def issue(`
- `src/butler/agent/tools.py:56` — `def verify(`
- `src/butler/identity/user_registry.py:355` — `def observe(`
- `src/butler/identity/user_registry.py:244` — `def _learn_nickname(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
