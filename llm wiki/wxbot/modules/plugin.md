---
type: module
module: plugin
summary: 角色和工具 Skill 分类，权限仍由业务服务验证
coverage: overview
last_verified: '2026-10-31'
sources:
- path: src/butler/agent/catalogue.py
  line: 8
  anchor: 'class SkillCatalogue:'
- path: src/butler/agent/skill_policy.py
  line: 8
  anchor: 'class SkillPolicyStore:'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
---
# Butler 运行时插件

## 范围

`plugins/butler-wechat/` 是运行时插件；角色在 skills/roles，工具在 skills/tools。SkillCatalogue 读取声明，SkillPolicyStore 按会话策略提供允许项。插件 Markdown 是运行时资产，修改会影响模型行为。

## 关系与边界

由 [[modules/butler]] 及 [[modules/runtime]] 使用，业务权限见 [[concepts/identity-authority]]。开发图谱 [[modules/wiki]] 不进入角色上下文，也不自动成为业务工具。分类和提示语均不能代替服务身份/权限校验。

## 代码依据

- `src/butler/agent/catalogue.py:8` — `class SkillCatalogue:`
- `src/butler/agent/skill_policy.py:8` — `class SkillPolicyStore:`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
