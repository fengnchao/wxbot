# Skill

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### Skill

冯草草的技能分支，目前图中列出刷抖音。

## 使用说明

- [wxbot / Butler / 模块与文件职责 / plugins/butler-wechat —— Codex 插件](#doc-9600492f18d384) · `README.md`

<a id="doc-9600492f18d384"></a>

### wxbot / Butler / 模块与文件职责 / plugins/butler-wechat —— Codex 插件

来源：`README.md:490`。

##### plugins/butler-wechat —— Codex 插件

| 位置 | 职责 |
|---|---|
| `skills/roles/butler-companion/SKILL.md` | 角色：日常陪伴对话 |
| `skills/roles/paimon/SKILL.md` 与同目录 md | 角色：派蒙（人物设定、关系、记忆、冲突处理） |
| `skills/roles/tong-jincheng-perspective/` | 角色：童锦程视角及研究参考材料 |
| `skills/tools/create-cron-job/SKILL.md` | 工具：创建定时任务 |
| `skills/tools/telegram-relay/SKILL.md` | 工具：Telegram 频道窗口转发 |
| `skills/tools/index-tts/SKILL.md` | 工具：文字和网页音色预设生成微信语音，长文本自动分段 |
| `skills/tools/setup/SKILL.md` | 工具：安装引导（仅安装时使用，不进入业务工具白名单） |
| `knowledge/graph-template.md` | 知识图谱内置模板：节点目录、事实分类、索引分区与追加规则 |
| `THIRD_PARTY.md` | 第三方素材来源与许可 |

插件的 `.md` 是运行时资产，改动会影响模型行为，不当普通文档处理。
角色放在 `skills/roles/`，工具放在 `skills/tools/`；插件清单分别声明这两个加载目录。
Butler 递归读取统一的 `skills/` 根目录，按 `roles/` 和 `tools/` 子目录识别类型；角色不需要声明 `metadata.butler.tags`，旧平铺目录仍兼容标签识别。
工具权限声明保留，并由服务端结合当前会话授权校验；目录分类本身不授予工具执行权限。
<!-- end-migrated-part: doc-9600492f18d384 -->

## 技术资料

- [Butler 运行时插件](#doc-709338d3e083eb) · `llm wiki/wxbot/modules/plugin.md`

<a id="doc-709338d3e083eb"></a>

### Butler 运行时插件

来源：`llm wiki/wxbot/modules/plugin.md:1`。

```yaml
type: module
module: plugin
summary: 角色和工具 Skill 分类，权限仍由业务服务验证
coverage: overview
last_verified: '2026-11-07'
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
- path: src/butler/agent/catalogue.py
  line: 14
  anchor: 'def _entries(self):'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-resident-xiaochao
- raw/changes/2026-11-07-stale-regression-tests
```
### Butler 运行时插件

#### 范围

`plugins/butler-wechat/` 是运行时插件；角色在 skills/roles，工具在 skills/tools。SkillCatalogue 读取声明，SkillPolicyStore 按会话策略提供允许项。插件 Markdown 是运行时资产，修改会影响模型行为。

`knowledge/graph-template.md` 是知识图谱的内置模板：前端三节（`## 节点目录`、`## 分类`、`## 提炼规则`）决定新 vault 建哪些目录、事实分哪些类、提炼追加哪些规则。它只读，管理台保存的 `data/knowledge/template.md` 优先；解析失败时回退到这里。见 [symbols/knowledge-template](knowledge-vault.md#doc-4656beba355895)。

#### 关系与边界

IndexTTS 工具的 preset 现可省略，由服务端当前会话绑定提供默认；tts_presets 只返回当前会话默认和网页列表，显式指定优先。Skill 提示不授予身份权限，也不能指定另一联系人；配置/默认变化不重放既有生成操作，见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。

`tools/index-tts` 声明 `tts_presets/tts_generate`，文字与预设名是唯一生成参数，参考音之外使用网页默认值。由 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) 实现服务端授权、幂等、分段与当前会话投递；技能文本不授予权限。

由 [modules/butler](butler.md#doc-38393df7a7b4da) 及 [modules/runtime](butler-functions.md#doc-241e7c8bdd1c05) 使用，业务权限见 [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。开发图谱 [modules/wiki](wxbot.md#doc-ed5d88ddcd1b47) 不进入角色上下文，也不自动成为业务工具。分类和提示语均不能代替服务身份/权限校验。

#### 代码依据

- `src/butler/agent/catalogue.py:8` — `class SkillCatalogue:`
- `src/butler/agent/skill_policy.py:8` — `class SkillPolicyStore:`
- `plugins/butler-wechat/knowledge/graph-template.md:21` — `## 节点目录`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)

[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。

#### 常驻角色接入核对

小潮的角色正文在 `resident/xiao-chao.md`，由 [symbols/resident-role](resident.md#doc-81303bd5af31f1) 专用日记入口加载。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。


#### 插件完整性回归

本地安装测试按 manifest 导出的技能文件与实际 skills 目录比对，同时断言核心技能路径（含 IndexTTS），不再以旧的固定数量 6 判断完整性。引导技能、MCP、协议版本和目录边界检查保留。当前生产插件未改。

来源 [raw/changes/2026-11-07-stale-regression-tests](wxbot.md#doc-df3c99eaa835f8)。
<!-- end-migrated-part: doc-709338d3e083eb -->
