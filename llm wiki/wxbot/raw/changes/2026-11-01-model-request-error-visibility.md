---
type: change
title: 模型请求失败保留脱敏状态码
pages: [symbols/local-model-backend, modules/models]
---
# 模型请求失败保留脱敏状态码

## 目标与背景

切换接入方式为 API + Key 后，用户只看到 `openai model request failed (HTTPError)`，无法判断是密钥、地址还是模型名的问题。原实现把任何异常压成类型名，故意丢弃状态码；同时存在两层包装：`LocalModelBackend.chat` 会再包一次内层 `HermesError`，把真实原因替换成 `HermesError`。本次让失败原因带上 HTTP 状态码与一句本地提示，仍不暴露地址、密钥和远端响应正文。

## 文件与代码位置

- `src/butler/backends/compatible.py:36` — 新增 `_STATUS_HINTS`，状态码到本地排查提示的映射。
- `src/butler/backends/compatible.py:112` — 新增 `CompatibleBackend._error_detail`，只读取异常的 `response.status_code`。
- `src/butler/backends/compatible.py:153` — `chat` 的失败分支改用 `_error_detail` 组装 `HermesError`，并写入 `last_error`。
- `src/butler/backends/models.py:72` — 新增 `except HermesError` 直通分支：内层已带脱敏原因，不再二次包装，并显式设 `retry_safe=False`。
- `src/butler/backends/models.py:79` — 非 `HermesError` 分支同样使用 `_error_detail`。
- `tests/butler/test_backend_adapters.py` — 新增 HTTP 状态码可见性与不泄露地址/密钥的用例，以及原生工具路径的状态码用例。

## 接口与字段

错误消息格式由 `{provider} model request failed ({类型名})` 变为 `{provider} model request failed ({类型名} {状态码}：{本地提示})`，非 HTTP 失败仍是纯类型名。`HermesError.status` 未改，仍是 `0`；状态码只出现在消息文本中。该文本经 `Result.meta['error']` 进入 SSE `error` 事件与 flow 日志，属既有字段，无新增字段。

## 数据库与迁移

不涉及：没有表结构或字段变化，也没有迁移脚本。

## 前端消费点

不涉及：管理台只展示既有 error 文本，未改组件、契约或 smoke 假数据。

## 测试与异步任务

`tests/butler/test_backend_adapters.py` 覆盖 401/404/400 的提示文本、密钥与地址不出现在错误里、`last_error` 取值，以及 `LocalModelBackend` 不再返回 `(HermesError)`。同目录的 model switch、transport、pipeline 用例回归通过。无异步任务或定时任务变化。

## 风险与回滚

提示文本会出现在日志与看板，长度略有增加，不含地址或凭据。若远端返回 5xx，仅显示状态码而不显示正文，排障仍需服务端日志。回滚方式是删除 `_error_detail` 与 `_STATUS_HINTS`，恢复为 `type(exc).__name__`，并移除 `models.py` 的 `except HermesError` 直通分支。
