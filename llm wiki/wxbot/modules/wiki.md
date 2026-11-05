---
type: module
module: wiki
summary: 本地关键词检索、证据入库和一致性巡检
coverage: core
last_verified: '2026-11-05'
sources:
- path: AGENTS.md
  line: 28
  anchor: '## Project knowledge graph'
- path: README.md
  line: 785
  anchor: '### 项目知识图谱'
- path: llm wiki/wxbot/scripts/wiki.py
  line: 69
  anchor: 'class Wiki:'
- path: llm wiki/wxbot/scripts/wiki.py
  line: 250
  anchor: def ingest(
- path: llm wiki/wxbot/scripts/wiki.py
  line: 301
  anchor: def query(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-readme-unread-note
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
- raw/changes/2026-11-03-development-doc-baseline
- raw/changes/2026-11-04-root-workspace-unification
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
---
# 项目知识图谱工具

## 入口和流程

`llm wiki/wxbot/scripts/wiki.py` 是本地开发工具，依赖 [[modules/common]] 的 REPO_ROOT 和已有 PyYAML。query 展开双向双链；change 创建追加记录；ingest 验证词条来源并刷新索引/日志/快照；lint 只读检查；status 查看规模及待入库记录。操作见 [[guide]]。

开发前先核对实际工作树、分支、SHA、未提交修改及解释器的 `REPO_ROOT`，见 [[concepts/development-baseline]]。
若可编辑安装误指向另一工作树，本地工具支持 `--repo-root <当前项目根目录>` 显式限定图谱读写；
这不能替代修正业务运行环境，也不授权切分支、合并或重启服务。
2026-11-04 的主目录与可编辑安装统一已在 [[concepts/development-baseline]] 记录；
仍须按当前解释器和实际导入位置核验，不能把本次结果当成后续永久保证。

## 边界

不会调用模型或业务服务；语义抽取/契约/字段血缘由开发模型对照源码维护。`ingest-state.json` 保存归一化文本摘要，来源完整文件任何变化都提示复核。只读命令不访问 runtime 数据。入口规则在根 AGENTS.md；[[modules/plugin]] 的运行时身份权限不受图谱影响。

## 验证

本地离线用例在 tests/unit/test_project_wiki.py，测试临时库与命令输出/写入行为，不依赖 Obsidian。测试目录本地忽略，源码中不新增测试接口。

## 代码依据

- `AGENTS.md:28` — `## Project knowledge graph`
- `README.md:785` — `### 项目知识图谱`
- `llm wiki/wxbot/scripts/wiki.py:69` — `class Wiki:`
- `llm wiki/wxbot/scripts/wiki.py:250` — `def ingest(`
- `llm wiki/wxbot/scripts/wiki.py:301` — `def query(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-11-01-knowledge-auto]]

[[raw/changes/2026-11-01-readme-unread-note]]

[[raw/changes/2026-11-02-knowledge-graph-template]]

[[raw/changes/2026-11-02-mention-picker-gating-residue]]

[[raw/changes/2026-11-03-development-doc-baseline]]

[[raw/changes/2026-11-04-root-workspace-unification]]


## 本次核对

[[raw/changes/2026-11-04-index-tts-skill]]：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [[apis/index-tts]]，其余已述契约未改。


## 联系人语音配置核对

[[raw/changes/2026-11-04-contact-index-tts]]：新增会话授权控件与原接口消费，源码位置已核对；后端契约保持。


## 联系人语音配置核对

[[raw/changes/2026-11-04-webui-preset-binding]]：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [[apis/index-tts]]。


图谱契约说明来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]。


## 群聊采集与自动语音复核（2026-11-05）

README 追加自动语音真实 WebUI 默认、配置热读和窗口越屏恢复说明；安装路径、静态文件位置及图谱 CLI 合同不变。功能依据见 [[concepts/automatic-voice-reply]]、[[concepts/capture-viewport]]。来源 [[raw/changes/2026-11-05-group-auto-voice]]。

## 本次核对

README 的图谱维护流程沿用，更新联系人操作路径。 来源 [[raw/changes/2026-11-05-contact-enrollment-and-tts-ui]]。
