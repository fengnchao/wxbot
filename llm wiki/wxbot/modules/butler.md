---
type: module
module: butler
summary: 身份、权限、模型编排和业务工具的服务边界
coverage: overview
last_verified: '2026-11-04'
sources:
- path: src/butler/server.py
  line: 50
  anchor: def make_handler(
- path: src/butler/agent/core.py
  line: 79
  anchor: 'class Butler:'
- path: src/butler/agent/tools.py
  line: 30
  anchor: 'class ToolService:'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
depends_on:
- modules/common
---
# Butler 编排层

## 职责与范围

`src/butler/` 持有业务编排；HTTP 从 server.make_handler 进入 agent.core.Butler，工具执行以 ToolService 验证的服务身份为边界。入口 `python -m butler.server`；操作细节见根 README。

## 关键入口与依赖

消息 API：[[apis/butler-handle]]、[[apis/butler-handle-stream]] → [[symbols/butler-handle]] → [[symbols/butler-result]]。模型后端位于 `backends/`，调用共享接口；业务不能塞进 wxbot UI 层。

知识库管理接口：`GET /v1/knowledge/extract`（`src/butler/server.py:142`）只回 [[symbols/knowledge-auto]] 的 `status()`；`POST /v1/knowledge/extract`（`:322`）校验 `owner`/`batch`/`dry_run` 后交给 `trigger()` 后台跑，鉴权后只回 202。调度器本身在 `serve()` 里构造与启停（`:477`、`:488`、`:496`），不占 HTTP 线程。

子模块：[[modules/identity]]、[[modules/delivery]]、[[modules/runtime]]、[[modules/telegram]]；共享基础能力 [[modules/common]]。运行时角色/工具定义见 [[modules/plugin]]，不是开发知识图谱的权限来源。

## 数据和消费方

业务 SQLite 由 BusinessStore 持有；本轮未完整建档其表。HTTP 消费方是 [[modules/wxbot]]，管理接口经 [[modules/dashboard]] 代理。微信队列属于 wxbot，不属于 Butler 业务库。主链路见 [[concepts/message-pipeline]]，权限边界见 [[concepts/identity-authority]]。

另有一套旁路库：[[tables/kb-episodes]]（`data/knowledge/p-<slug>/episodes.sqlite3`）只存每轮对话的用户原文与回复，[[tables/kb-facts]]（同目录 `facts.sqlite3`）存从原文提炼的长期事实，两者由 [[tables/kb-owners]]（`data/knowledge/index.sqlite3`）当目录。**一人一库**：任何一个联系人的数据损坏或整体清空都不牵连别人；原文按保留期过期，事实不跟着消失。它们和 BusinessStore 分库，因为 business 库每次启动整库备份，塞入聊天原文会让备份体积失控。原文写入点只在 `_handle_request`，失败只记日志。

保留期清理与事实提炼现在由 `serve()` 里的常驻调度器 [[symbols/knowledge-auto]] 驱动（`knowledge.auto_extract` 与 `knowledge.auto_prune` 两个开关，默认关），提炼仍只经 [[symbols/knowledge-extract]] 这一条写路径；`python -m butler knowledge-extract|knowledge-prune|knowledge-migrate` 保留为人工补跑与旧库拆分入口，其中提炼要先拿同一把跨进程锁。

## 代码依据

- `src/butler/server.py:50` — `def make_handler(`
- `src/butler/agent/core.py:79` — `class Butler:`
- `src/butler/agent/tools.py:30` — `class ToolService:`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

## 可切换后端

统一后端见 [[modules/models]]；本地业务按 uses_local_runtime 初始化，适用于 Codex 和通用模型。旧 Hermes 空 model 配置保留历史远端业务兼容路径。

模型来源上报用 `Config.model_identity`：Codex 固定报 codex，其它按 `[model].provider` 产品名、回退协议名。因此流转日志和模型面板显示 deepseek 而不再是 openai。


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch]]

[[raw/changes/2026-11-01-knowledge-episodes]]

[[raw/changes/2026-11-01-knowledge-sharding]]

[[raw/changes/2026-11-01-knowledge-auto]]


## 本次核对

[[raw/changes/2026-11-04-index-tts-skill]]：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [[apis/index-tts]]，其余已述契约未改。


## 联系人语音配置核对

[[raw/changes/2026-11-04-webui-preset-binding]]：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [[apis/index-tts]]。


图谱契约说明来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]。
