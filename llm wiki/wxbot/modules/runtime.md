---
type: module
module: runtime
summary: 安装、迁移、并发和 MCP 等运行基础设施
coverage: overview
last_verified: '2026-10-31'
sources:
- path: src/butler/runtime/setup.py
  line: 28
  anchor: def initialize(
- path: src/butler/runtime/setup.py
  line: 34
  anchor: def doctor(
- path: src/butler/runtime/mcp_gateway.py
  line: 5
  anchor: 'def '
- path: src/butler/runtime/model_migration.py
  line: 13
  anchor: def migrate_model_connection(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
---
# Butler 运行支撑

## 范围和入口

`src/butler/runtime/` 承载安装、迁移、并发、MCP、心跳与插件验证。initialize 复用初始化实现；doctor 是环境自检入口。命令行来自 `butler/__main__.py`，详细操作见 README。

## 关系与约束

属于 [[modules/butler]]；运行时读取 [[modules/plugin]] 的插件契约。必须使用安装者本人的登录，不能复制其他安装的认证/数据；服务由用户启动和重启。MCP 权限见 [[concepts/identity-authority]]。

## 覆盖缺口

配置字段/迁移兼容和全部 MCP method 尚未逐项建档。

## 代码依据

- `src/butler/runtime/setup.py:28` — `def initialize(`
- `src/butler/runtime/setup.py:34` — `def doctor(`
- `src/butler/runtime/mcp_gateway.py:5` — `def `
- `src/butler/runtime/model_migration.py:13` — `def migrate_model_connection(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

## 模型运行支撑

[[symbols/reloadable-backend]] 固定请求代际；model_migration.py 将旧 direct 配置显式迁移为 wxbot→Butler，保留本机私有备份且不启动服务。见 [[modules/models]]。


[[raw/changes/2026-10-31-switchable-models]]
