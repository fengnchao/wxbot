---
type: symbol
module: models
coverage: core
summary: 请求固定后端代际，在途完成后才关闭旧工作进程
last_verified: '2026-10-31'
sources:
- path: src/butler/runtime/model_switch.py
  line: 50
  anchor: class ReloadableBackend
- path: src/butler/runtime/model_switch.py
  line: 134
  anchor: def request(
- path: src/butler/runtime/model_switch.py
  line: 109
  anchor: def _refresh(
changes:
- raw/changes/2026-10-31-switchable-models
---
# ReloadableBackend


所属 [[modules/models]]。`request()` 使用 ContextVar 固定本轮 generation；chat/reset/session_id 复用固定上下文。只复制模型字段，保留启动时服务身份、存储和路径；实际配置文件名由 Config.config_path 保存。

新请求读取配置并按差异构造后端，旧后端在用户计数归零后关闭；在途请求不迁移、不重放。Codex 代际工具凭据映射只在其生命周期内共同有效。解析/构造失败阻止新请求并暴露脱敏错误，保留旧代际供诊断与在途完成。

`runtime_status()` 报实际 backend/model、configured_backend、reload_error、active_requests 与 retiring_backends。数据库身份不随代际重建；消费方 [[symbols/butler-handle]]，相关行为通过临时 fake 后端并发测试验证。


## 代码依据

- `src/butler/runtime/model_switch.py:50` — `class ReloadableBackend`
- `src/butler/runtime/model_switch.py:134` — `def request(`
- `src/butler/runtime/model_switch.py:109` — `def _refresh(`

## 入库来源


[[raw/changes/2026-10-31-switchable-models]]
