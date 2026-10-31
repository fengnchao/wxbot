---
type: module
module: wiki
summary: 本地关键词检索、证据入库和一致性巡检
coverage: core
last_verified: '2026-10-31'
sources:
- path: AGENTS.md
  line: 28
  anchor: '## Project knowledge graph'
- path: README.md
  line: 627
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
---
# 项目知识图谱工具

## 入口和流程

`llm wiki/wxbot/scripts/wiki.py` 是本地开发工具，依赖 [[modules/common]] 的 REPO_ROOT 和已有 PyYAML。query 展开双向双链；change 创建追加记录；ingest 验证词条来源并刷新索引/日志/快照；lint 只读检查；status 查看规模及待入库记录。操作见 [[guide]]。

## 边界

不会调用模型或业务服务；语义抽取/契约/字段血缘由开发模型对照源码维护。`ingest-state.json` 保存归一化文本摘要，来源完整文件任何变化都提示复核。只读命令不访问 runtime 数据。入口规则在根 AGENTS.md；[[modules/plugin]] 的运行时身份权限不受图谱影响。

## 验证

本地离线用例在 tests/unit/test_project_wiki.py，测试临时库与命令输出/写入行为，不依赖 Obsidian。测试目录本地忽略，源码中不新增测试接口。

## 代码依据

- `AGENTS.md:28` — `## Project knowledge graph`
- `README.md:627` — `### 项目知识图谱`
- `llm wiki/wxbot/scripts/wiki.py:69` — `class Wiki:`
- `llm wiki/wxbot/scripts/wiki.py:250` — `def ingest(`
- `llm wiki/wxbot/scripts/wiki.py:301` — `def query(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


[[raw/changes/2026-10-31-switchable-models]]
