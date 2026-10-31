---
type: module
module: models
coverage: core
summary: Butler 管理可切换模型与服务授权工具，wxbot 只调用 Butler
last_verified: '2026-10-31'
sources:
- path: src/butler/backends/__init__.py
  line: 12
  anchor: def create_backend(
- path: src/butler/backends/models.py
  line: 16
  anchor: class LocalModelBackend
- path: src/butler/backends/compatible.py
  line: 31
  anchor: PRODUCT_ENDPOINTS =
- path: src/butler/runtime/model_switch.py
  line: 50
  anchor: class ReloadableBackend
- path: src/dashboard/config_schema.py
  line: 156
  anchor: def row_metadata(
- path: src/dashboard/config_schema.py
  line: 126
  anchor: def access_provider(
- path: web/src/views/ConfigurationView.vue
  line: 37
  anchor: const backendName =
changes:
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch
---
# 统一模型后端


所属 [[modules/butler]]；微信入口 [[modules/wxbot]] → Butler → codex/hermes/openai/responses/openclaw/cursor/ollama/echo。

`[agent].provider` 选择后端，Codex 读取 `[codex]`；通用后端读取 `[model]` 的 url/model/api_key/timeout/max_history/system_prompt，以及 Cursor executable/work_dir 或 OpenClaw agent。`[hermes]` 兼容旧配置。页面 [[modules/web]] 使用草稿 provider 过滤适用字段，密钥使用既有保持/替换/清空语义。

分层语义：`[model].provider` 是接入方式（产品身份，可含 deepseek/custom），`[agent].provider` 与 `[model].backend` 是运行协议。页面只维护接入方式，由 `config_schema.ACCESS_PROTOCOLS` 推导协议并同时写入两处；`config_schema.access_fields()` 决定该接入方式真正要填的字段，未填的用 `ACCESS_HINTS` 占位而不是写入文件。CompatibleBackend 用 `PRODUCT_ENDPOINTS` 按产品身份选默认端点，空 url/model 也算未填，避免留空时落到另一家服务的官方地址。

模型通过 [[symbols/reloadable-backend]] 在后续请求切换；身份、业务库、认证、端口和监听目录仍是启动配置，不随模型重载。配置保存并非网络验证，真实服务可用性需另行授权验证。

[[symbols/local-model-backend]] 对 OpenAI/Responses 支持经 ToolService 许可的原生函数工具；Codex 保留原工具实现。Hermes/OpenClaw/Cursor/Ollama 是完整结果路径，不宣称具有 Butler 原生工具桥；未处理的工具调用会失败。Cursor 始终 ask/sandbox 且独立目录，不执行来自聊天的 CLI 选项。

旧 direct 安装使用 `python -m butler migrate` 显式迁移；迁移仅将本机参数移到 Butler 并备份，禁止把备份提交 Git。业务表结构不变；远端模型对话会话不保证跨后端移植。模型 API Key 不是本地身份授权，见 [[concepts/identity-authority]]。


## 代码依据

- `src/butler/backends/__init__.py:12` — `def create_backend(`
- `src/butler/backends/models.py:16` — `class LocalModelBackend`
- `src/butler/backends/compatible.py:31` — `PRODUCT_ENDPOINTS =`
- `src/butler/runtime/model_switch.py:50` — `class ReloadableBackend`
- `src/dashboard/config_schema.py:156` — `def row_metadata(`
- `src/dashboard/config_schema.py:126` — `def access_provider(`
- `web/src/views/ConfigurationView.vue:37` — `const backendName =`

## 入库来源


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch]]
