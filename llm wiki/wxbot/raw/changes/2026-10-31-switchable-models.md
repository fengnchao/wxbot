---
type: change
title: 统一 Butler 模型链路与随时切换
pages:
- apis/butler-handle
- apis/butler-handle-stream
- concepts/message-pipeline
- modules/butler
- modules/models
- modules/runtime
- modules/web
- modules/wiki
- modules/wxbot
- symbols/butler-handle
- symbols/butler-processor
- symbols/butler-result
- symbols/local-model-backend
- symbols/reloadable-backend
---
# 统一 Butler 模型链路与随时切换

## 目标与背景

用户要求 wxbot→Butler→Codex/Hermes/Cursor/API+Key/其它智能体，页面随选择变化，模型运行中可切换。影响与设计见 [[impacts/2026-10-31-switchable-models]]。

## 文件与代码位置

后端工厂、compatible.py/models.py、config.py；runtime/model_switch.py/model_migration.py/upgrade.py；agent/core.py/server.py/heartbeat.py；wxbot/main.py；dashboard 的 config_schema/view/editor、model_stream_view、api/support/jobs；ConfigurationView.vue、smoke 及 web/dist。准确位置见本记录 pages 所列词条的 sources。

## 接口与字段

Butler 处理消息完整回复契约保持，模型选择移到 [agent].provider/[model]/[codex]，runtime 追加实际模型、配置模型、重载错误和在途代际状态。原生工具只通过服务签发身份授权，模型 Key 不授予本地权限。

## 数据库与迁移

无业务表结构变更。通用远端会话仅保存不透明标识；联系人、记忆和提醒继续由 Butler 持有。旧 direct 配置显式迁移、私有备份并修改本机链路，不自动处理真实运行配置。已有工作树安装向导的统一链路改动予以保留并验证。

## 前端消费点

配置页按草稿 provider 显示适用字段，保持/替换/清空密钥原值不回传；模型字段热生效、非模型字段提示手动重启。保留 Vue 壳、主题及用户已有联系人 UI 工作；重新构建 dist 并运行 smoke。

## 测试与异步任务

临时 fake 后端覆盖协议、工具授权、完整结果、身份隔离、并发代际和显式迁移；配置和前端假数据验证见 [[model-switch-verification]]。不发送真实微信，不调用真实模型，不重启业务进程。

## 风险与回滚

这次代码首次加载需使用者手动重启相关进程，之后模型参数才由新代码热切换。失败配置不静默回旧模型；已执行工具而最终回答失败不可重放。未承诺跨模型远端会话连续。回滚代码需同时恢复兼容配置；模型迁移原配置备份只留本机，避免泄漏。旧 Hermes 远端业务模式仍是兼容入口，不自动转换既有业务身份。
