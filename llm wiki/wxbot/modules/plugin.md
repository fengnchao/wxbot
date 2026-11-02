---
type: module
module: plugin
summary: 角色和工具 Skill 分类，权限仍由业务服务验证
coverage: overview
last_verified: '2026-11-02'
sources:
- path: src/butler/agent/catalogue.py
  line: 8
  anchor: 'class SkillCatalogue:'
- path: src/butler/agent/skill_policy.py
  line: 8
  anchor: 'class SkillPolicyStore:'
- path: plugins/butler-wechat/knowledge/graph-template.md
  line: 21
  anchor: '## 节点目录'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-knowledge-graph-template
---
# Butler 运行时插件

## 范围

`plugins/butler-wechat/` 是运行时插件；角色在 skills/roles，工具在 skills/tools。SkillCatalogue 读取声明，SkillPolicyStore 按会话策略提供允许项。插件 Markdown 是运行时资产，修改会影响模型行为。

`knowledge/graph-template.md` 是知识图谱的内置模板：前端三节（`## 节点目录`、`## 分类`、`## 提炼规则`）决定新 vault 建哪些目录、事实分哪些类、提炼追加哪些规则。它只读，管理台保存的 `data/knowledge/template.md` 优先；解析失败时回退到这里。见 [[symbols/knowledge-template]]。

## 关系与边界

由 [[modules/butler]] 及 [[modules/runtime]] 使用，业务权限见 [[concepts/identity-authority]]。开发图谱 [[modules/wiki]] 不进入角色上下文，也不自动成为业务工具。分类和提示语均不能代替服务身份/权限校验。

## 代码依据

- `src/butler/agent/catalogue.py:8` — `class SkillCatalogue:`
- `src/butler/agent/skill_policy.py:8` — `class SkillPolicyStore:`
- `plugins/butler-wechat/knowledge/graph-template.md:21` — `## 节点目录`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

[[raw/changes/2026-11-01-knowledge-vault-graph]]

[[raw/changes/2026-11-02-knowledge-graph-template]]
