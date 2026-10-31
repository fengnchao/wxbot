---
type: change
title: 模型来源上报改用接入方式（core.py 相关词条更正）
pages:
- apis/butler-handle
- concepts/message-pipeline
- symbols/butler-handle
- symbols/butler-result
---
# 模型来源上报改用接入方式（core.py 相关词条更正）

## 目标与背景

补充 [[raw/changes/2026-10-31-model-access-switch]] 漏登记的受影响词条。该记录改了 `src/butler/agent/core.py:255` 的 `emit('backend')`，但只把模型配置相关词条列进 pages；lint 的 source-drift 指出同一源文件的 handle/result/pipeline 词条也应有对应记录，因此单列此条，不改写已入库的历史记录。

## 文件与代码位置

- `src/butler/agent/core.py:255`：`emit('backend', provider=model_cfg.model_identity, ...)`，去掉 `hermes_model` 兜底。
- `src/butler/config.py:86`：新增 `model_identity` property，Codex 固定 codex，其它按 `[model].provider` 产品名、回退协议名。

## 接口与字段

不涉及。`/v1/handle` 与 `/v1/handle-stream` 的请求/响应字段、`Result.as_dict()` 的输出结构和 `meta` 语义均未变；变化只出现在流转 trace 的 `backend.provider` 展示值上（deepseek 不再显示为 openai）。队列表结构不变。

## 数据库与迁移

不适用。无表结构、无迁移、无定时任务。

## 前端消费点

[[modules/web]] 的实时工作流与模型面板读的是同一份 trace 字段，显示值随接入方式变化，不需要新增列或新接口。

## 测试与异步任务

`pytest tests/dashboard tests/butler tests/unit/codex` 736 项通过，`tests/butler/test_model_switch_runtime.py` 覆盖 `butler_business_identity_survives_provider_change`。未发送真实微信消息、未调用真实模型、未重启服务。

## 风险与回滚

若接入方式填了协议不认识的字符串，展示会退回协议名，不影响实际调用。回滚只需恢复 core.py 的 emit 参数与删除 `model_identity`；已写入的 `[model].provider` 在旧代码下作为未知值被忽略。
