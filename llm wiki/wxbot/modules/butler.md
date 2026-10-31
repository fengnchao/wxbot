---
type: module
module: butler
summary: 身份、权限、模型编排和业务工具的服务边界
coverage: overview
last_verified: '2026-10-31'
sources:
- path: src/butler/server.py
  line: 47
  anchor: def make_handler(
- path: src/butler/agent/core.py
  line: 75
  anchor: 'class Butler:'
- path: src/butler/agent/tools.py
  line: 31
  anchor: 'class ToolService:'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch
depends_on:
- modules/common
---
# Butler 编排层

## 职责与范围

`src/butler/` 持有业务编排；HTTP 从 server.make_handler 进入 agent.core.Butler，工具执行以 ToolService 验证的服务身份为边界。入口 `python -m butler.server`；操作细节见根 README。

## 关键入口与依赖

消息 API：[[apis/butler-handle]]、[[apis/butler-handle-stream]] → [[symbols/butler-handle]] → [[symbols/butler-result]]。模型后端位于 `backends/`，调用共享接口；业务不能塞进 wxbot UI 层。

子模块：[[modules/identity]]、[[modules/delivery]]、[[modules/runtime]]、[[modules/telegram]]；共享基础能力 [[modules/common]]。运行时角色/工具定义见 [[modules/plugin]]，不是开发知识图谱的权限来源。

## 数据和消费方

业务 SQLite 由 BusinessStore 持有；本轮未完整建档其表。HTTP 消费方是 [[modules/wxbot]]，管理接口经 [[modules/dashboard]] 代理。微信队列属于 wxbot，不属于 Butler 业务库。主链路见 [[concepts/message-pipeline]]，权限边界见 [[concepts/identity-authority]]。

## 代码依据

- `src/butler/server.py:47` — `def make_handler(`
- `src/butler/agent/core.py:75` — `class Butler:`
- `src/butler/agent/tools.py:31` — `class ToolService:`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

## 可切换后端

统一后端见 [[modules/models]]；本地业务按 uses_local_runtime 初始化，适用于 Codex 和通用模型。旧 Hermes 空 model 配置保留历史远端业务兼容路径。

模型来源上报用 `Config.model_identity`：Codex 固定报 codex，其它按 `[model].provider` 产品名、回退协议名。因此流转日志和模型面板显示 deepseek 而不再是 openai。


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch]]
