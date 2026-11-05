---
type: module
module: plugin
summary: 角色和工具 Skill 分类，权限仍由业务服务验证
coverage: overview
last_verified: '2026-11-04'
sources:
- path: src/butler/agent/tools.py
  line: 24
  anchor: '''tts_generate'':(''text'',),'
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
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
---
# Butler 运行时插件

## 范围

`plugins/butler-wechat/` 是运行时插件；角色在 skills/roles，工具在 skills/tools。SkillCatalogue 读取声明，SkillPolicyStore 按会话策略提供允许项。插件 Markdown 是运行时资产，修改会影响模型行为。

`knowledge/graph-template.md` 是知识图谱的内置模板：前端三节（`## 节点目录`、`## 分类`、`## 提炼规则`）决定新 vault 建哪些目录、事实分哪些类、提炼追加哪些规则。它只读，管理台保存的 `data/knowledge/template.md` 优先；解析失败时回退到这里。见 [[symbols/knowledge-template]]。

## 关系与边界

IndexTTS 工具的 preset 现可省略，由服务端当前会话绑定提供默认；tts_presets 只返回当前会话默认和网页列表，显式指定优先。Skill 提示不授予身份权限，也不能指定另一联系人；配置/默认变化不重放既有生成操作，见 [[apis/index-tts]]。

`tools/index-tts` 声明 `tts_presets/tts_generate`，文字与预设名是唯一生成参数，参考音之外使用网页默认值。由 [[apis/index-tts]] 实现服务端授权、幂等、分段与当前会话投递；技能文本不授予权限。

由 [[modules/butler]] 及 [[modules/runtime]] 使用，业务权限见 [[concepts/identity-authority]]。开发图谱 [[modules/wiki]] 不进入角色上下文，也不自动成为业务工具。分类和提示语均不能代替服务身份/权限校验。

## 代码依据

- `src/butler/agent/catalogue.py:8` — `class SkillCatalogue:`
- `src/butler/agent/skill_policy.py:8` — `class SkillPolicyStore:`
- `plugins/butler-wechat/knowledge/graph-template.md:21` — `## 节点目录`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

[[raw/changes/2026-11-01-knowledge-vault-graph]]

[[raw/changes/2026-11-02-knowledge-graph-template]]


## 本次核对

[[raw/changes/2026-11-04-index-tts-skill]]：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [[apis/index-tts]]，其余已述契约未改。


## 联系人语音配置核对

[[raw/changes/2026-11-04-webui-preset-binding]]：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [[apis/index-tts]]。


图谱契约说明来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]。
