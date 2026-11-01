---
type: change
title: 模型失败契约补齐为概念词条
pages: [concepts/model-error-contract, concepts/delivery-state, modules/models]
---
# 修改记录

## 目标与背景

`coverage.md` 的「待扩展」长期列着「全部模型后端的错误/重试契约」未建档。实际排查线上报错时，这条链路横跨 Butler 后端、SSE 事件、wxbot 处理适配和队列四层，只看单个模块词条拼不出来，只能反复读源码。本次把跨层契约收敛成 [[concepts/model-error-contract]]，并更新覆盖清单。

本次只补文档，不改代码。上一轮 `raw/changes/2026-11-01-model-request-error-visibility` 已把 HTTP 状态码加进错误消息，本词条按修改后的现状叙述。

## 文件与代码位置

无源码改动。核对并作为事实来源的位置：

- `src/butler/agent/hermes.py:36` — `HermesError`，字段 `status`/`detail`，无 `retry_safe` 类属性。
- `src/butler/backends/compatible.py:112` — `_error_detail`，失败原因只保留类型名与状态码。
- `src/butler/backends/compatible.py:149` — 失败包装成 `HermesError` 的唯一点。
- `src/butler/backends/models.py:72` — 内层 `HermesError` 直通，不再二次包装。
- `src/butler/backends/codex.py:349` — `retry_safe=not submitted`，按是否已提交判定。
- `src/butler/runtime/model_switch.py:21` — `ModelConfigurationError.retry_safe = True`。
- `src/butler/agent/core.py:363` — `except HermesError` 转成 `reply_complete=False` 的 `Result`。
- `src/butler/agent/core.py:249` — SSE `error` 事件 `code='incomplete_result'`。
- `src/butler/server.py:354` — 未捕获异常兜底事件恒为 `retry_safe=False`。
- `src/wxbot/processor/butler.py:99` — SSE `error` 事件转成 `ValueError`；`:137` 从 `meta` 取 `retry_safe`。
- `src/wxbot/queue_worker.py:174` — 逐批次读取 `retry_safe` 后调 `fail_batch`。
- `src/wxbot/queue_store.py:384` — `fail_batch` 写 `model_retryable`/`model_uncertain`。
- `src/wxbot/model_recovery.py:2` — `MODEL_MAX_ATTEMPTS=3`，重试间隔 5/15 秒。
- `src/wxbot/queue_store.py:409` — 放弃时的用户可见原因文案。

## 接口与字段

无新增或变更字段。词条只登记既有语义：

- SSE `error` 事件字段 `code`/`message`/`retry_safe`。
- `Result.meta` 字段 `error`/`status`/`reply_complete`/`retry_safe`。
- `batches` 表 `error`/`attempts` 与 `delivery_events.action` 的 `model_retryable`/`model_uncertain`/`model_retry`/`model_abandoned`。
- `queue.failure_discard_seconds` 配置项，默认 180 秒，范围 1–86400（`src/wxbot/config.py:53`）。

## 数据库与迁移

不涉及。只读既有表结构与事件动作，不新增列、不写迁移。

## 前端消费点

不涉及。管理台通过既有只读投影展示失败倒计时与动作，未改前端代码，也未新增接口。

## 测试与异步任务

无新增测试。词条引用的本地用例（不入 Git）：`test_backend_adapters.py`、`test_model_switch_runtime.py`、`test_model_recovery.py`、`test_transport.py`、`test_pipeline.py`。队列侧异步任务为后台维护线程 `_maintain`，每 0.2 秒调用一次 `recover_model_failures`。

## 风险与回滚

风险：词条把四层状态语义写在一起，若后续只改其中一层而未更新本页，会产生过期导航。缓解：词条每条事实都带 `path:line` 与锚点，`lint` 可检出漂移。

回滚：删除 `concepts/model-error-contract.md` 与 `raw/changes/2026-11-01-model-error-contract.md`，还原 `coverage.md` 的「待扩展」条目，重新 `ingest` + `lint`。本记录不影响运行时代码。
