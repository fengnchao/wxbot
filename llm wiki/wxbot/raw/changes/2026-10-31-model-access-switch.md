---
type: change
title: 配置页接入方式下拉与模型字段随选择变化
pages:
- modules/models
- modules/dashboard
- modules/web
- modules/butler
- symbols/local-model-backend
---
# 配置页接入方式下拉与模型字段随选择变化

## 目标与背景

上一轮 [[raw/changes/2026-10-31-switchable-models]] 把运行时统一到 `wxbot → Butler → 所选模型`，但管理台页面没跟上：CLI 安装向导已支持 DeepSeek 和自定义 API，页面下拉里没有这两个值；`model_stream_view.LABELS` 与 `WorkflowView.vue` 的 deepseek/custom 标签永远走不到；切到 API 直调后 `[model].url` 和 `[model].model` 全空且没有任何提示。本次把「接入方式」收敛成页面上的一个入口，并让连接字段随选择变化。

约定沿用并写实：`[agent].provider` 是运行协议，`[model].provider` 是接入方式（产品身份），`[model].backend` 是自定义 API 的协议。页面只维护接入方式，另外两个由服务端推导，避免同一件事在两个下拉里各填一半。

## 文件与代码位置

- `src/dashboard/config_schema.py`：`ACCESS_PROVIDERS`(10 种)、`ACCESS_LABELS`、`ACCESS_PROTOCOLS`、`ACCESS_NOTE`、`ACCESS_HINTS`、`access_provider()`、`access_fields()`；`row_metadata()` 为 `model.provider`/`model.backend`/`agent.provider` 补中文标签；`choices()` 增加两行；`validate_value()` 分开校验接入方式与协议。
- `src/dashboard/config_view.py`：`BT_DEFAULTS['model']` 补 `provider` 和 `backend` 两个键；行内按接入方式补 `placeholder`/`note`/`choice_labels`/`applicable`；响应增加 `model_access`。
- `src/dashboard/config_editor.py`：`_access_changes()` 把接入方式展开成 `[agent].provider` 与 `[model].backend`；Codex 用 `op:default` 删除多余协议字段。
- `src/butler/backends/compatible.py`：`PRODUCT_ENDPOINTS`、`self.identity`；空 url/model 也回退默认值；`scope()` 与 `emit('backend')` 使用接入方式。
- `src/butler/backends/models.py`、`src/butler/config.py`（`model_identity`）、`src/butler/agent/core.py`：模型来源上报用接入方式。
- `web/src/views/ConfigurationView.vue`：`draftRaw()`、`backendName`、`applicable()`、`categoryOf()`、`choicesOf()`、`fieldOf()`；`model.provider` 豁免兼容降级，避免选完 Codex 就切不回来。
- `web/src/components/ConfigField.vue`：显示 `field.note`，文本/数字输入带占位提示。
- `web/scripts/smoke.mjs`：配置页假数据补接入方式行与 `model_access`，下拉定位改为按 `deepseek` 选项识别。

## 接口与字段

`GET /api/configuration` 的响应新增 `model_access`：

```
model_access = { current: <接入方式>, fields: {<接入方式>: [字段名…]}, notes: {<接入方式>: <说明>} }
```

`fields` 与 `notes` 覆盖全部 10 种接入方式，页面不维护第二份映射表。请求体仍是原有的 `source/version/changes/acknowledge`；`changes` 里出现 `model.provider` 或 `model.backend` 时由服务端展开，客户端不额外传协议。

## 数据库与迁移

不涉及。无业务表结构变更、无数据迁移、无新增定时任务。旧配置只有 `[agent].provider` 时按协议名回退接入方式，不需要重写文件；用户下次保存时才落盘。

## 前端消费点

`ConfigurationView.vue` 用 `draftRaw('butler.model.provider')` 优先、`model_access.current` 兜底决定当前接入方式，草稿一改字段就跟着变。`agent.provider` 收进「高级配置」避免两个下拉并存，`model.provider` 不参与兼容降级判断。字段占位提示只作展示，留空由运行时默认值兜底，不写入配置文件。

## 测试与异步任务

`pytest tests/dashboard tests/butler tests/unit/codex` 共 736 项通过。`npm.cmd --prefix web run build` 与 `npm.cmd --prefix web run smoke` 通过。Hallmark `sloplint.mjs --scope app --render` 在隔离假数据预览上渲染，0 FAIL、2 REFLEX、1 WARN，均为既有壳层条目（详见 [[model-switch-verification]]）。全程未发送真实微信消息、未调用真实模型、未重启任何服务。

## 风险与回滚

接入方式与协议由服务端同时写入，手动只改一个字段仍会出现两者不一致，页面因此把它移入高级配置并标注用途。空地址按产品身份回退默认端点，若新增产品未登记 `PRODUCT_ENDPOINTS` 仍会落到协议默认地址，需同步补表。回滚需同时恢复 `config_schema`/`config_view`/`config_editor` 与前端源码，并重新构建 `web/dist`；已保存的 `[model].provider` 值在旧代码下会被当成未知协议忽略。
