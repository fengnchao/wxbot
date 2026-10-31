---
type: impact
status: done
date: '2026-10-31'
---
# 统一 Butler 模型接入与运行中切换

目标：微信固定走 wxbot → Butler → Codex/Hermes/Cursor/兼容 API 或其他智能体。保存模型设置后新请求采用新后端，正在处理的请求保留原后端；不重启既有服务，不重放未知结果。

## 查询与覆盖

已查询关键词“模型/backend/direct”，读取 [[modules/butler]]、[[modules/web]]、[[symbols/butler-handle]] 并核对源码。原图谱对非 Codex 后端和安装迁移仅概览；本次补建模型后端及切换词条。

## 文件、调用与边界

- `src/butler/backends/__init__.py:12` 原先非 Codex 全部落入 Hermes，需要统一工厂与兼容适配。
- `src/butler/agent/core.py:84` / `server.py:122` 原先业务存储、工具与 runtime 接口只对 Codex 开启，需按 Butler 本地业务能力判断。
- `src/butler/config.py` 持有 provider/model 配置；保存后的模型相关字段按请求边界刷新，监听地址、服务 token、存储目录不热改。
- `src/dashboard/config_schema.py:111`、config_view/editor、`web/src/views/ConfigurationView.vue:27` 处理后端选项、字段和保存文案；页面按草稿选择显示字段，凭据原值只留服务端。
- 旧 direct 配置通过明确的 migrate 操作迁到本机 Butler；保留本机原配置备份，不自动修改正在使用的真实配置。

## 接口与数据

保持 [[apis/butler-handle]]、[[apis/butler-handle-stream]] 的完整回复契约，API/CLI 错误抛出并由既有错误路径处理。API Key、模型名、URL、协议、Cursor 工作目录等属于模型配置；不是身份权限凭证。

无需改业务表结构。联系人/记忆/提醒留在同一个 Butler 业务库；换模型不改变其归属。各后端对话历史按身份、策略和用途隔离，不能把其他人的历史带到新请求。

## 页面与验证

保留 Vue 壳和主题，按 Hallmark app/polish 检查；新增后端选项/字段动态显示，既有 API secret keep/replace/clear 语义保留。前端 build、smoke 和实际应用 URL 渲染检查；失败或环境限制如实记录。

临时配置、假后端测试工厂、完整结果、会话隔离、运行请求固定代际、失败配置不污染现有后端、显式旧配置迁移。真实模型连接/微信发送不在离线验收范围。

## 实施结果

运行时与后端已由 [[raw/changes/2026-10-31-switchable-models]] 完成；页面侧的接入方式入口由 [[raw/changes/2026-10-31-model-access-switch]] 补齐，`core.py` 上报改动另见 [[raw/changes/2026-10-31-model-access-switch-core-emit]]。验证结果见 [[model-switch-verification]]。

页面只保留一个「接入方式」下拉（`[model].provider`），`[agent].provider` 与 `[model].backend` 由 `config_editor._access_changes()` 同时写入；字段适用性与说明随接口的 `model_access` 下发。空 url/model 按产品身份回退默认端点。遗留：只手工改 `[agent].provider` 仍会造成两处不一致，页面已把它移入「高级配置」并标注用途；新增产品需同时补 `PRODUCT_ENDPOINTS`。

## 实施选择

沿用 ModelBackend 接口与现有纯 HTTP/CLI 协议实现，不引入新的常驻服务。通用 API 支持 Chat Completions/Responses，其他智能体需暴露支持的协议。热切换保留旧代际直到其在途请求结束，配置解析失败返回明确错误而非悄悄切回另一个模型。
