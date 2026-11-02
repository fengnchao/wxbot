---
type: change
title: 提及残留登记引发的来源复核
pages: [concepts/group-identity-evidence, concepts/identity-authority,
  concepts/message-pipeline, concepts/model-error-contract, concepts/unread-capture-retry,
  symbols/queue-finish, tables/queue-batches, tables/queue-inbox]
---
# 提及残留登记引发的来源复核

## 目标与背景

[[raw/changes/2026-11-02-mention-picker-gating-residue]] 为了登记可认领的提及残留，改了两处被多个词条引用的来源文件：

- `src/wxbot/queue_store.py:21` 的 `FAILURE_DETAIL_FIELDS` 增加一个标量键 `mention_residue`。
- `src/wxbot/wechat/chat_window.py:392` 新增 `_draft_equal`，并让 `clear_owned_draft` 在清理前等待焦点。

这些改动不改变下列词条描述的批次状态机、身份解析或未读重试，但源码指纹变了；需要逐条对照代码复核并登记，否则巡检会一直报 `source-drift`。

## 文件与代码位置

- `src/wxbot/queue_store.py:21` — 白名单只多一个键，集合仍是单行到 `:26`；`claim_batch`、`finish_batch_parts`、`_insert_delivery`、`_recompute_batch`、`capture`、`finish_delivery`、`retry_failed_deliveries`、`forget_session` 的行号与实现均未变。
- `src/wxbot/wechat/chat_window.py:392` — 新增 `_draft_equal`（只容忍尾随分隔空白）与 `clear_owned_draft` 内的 0.5 秒焦点等待；`Message.ref`（`:36`）、`_classify` 的诊断节流（`:246` 附近）、`read_bundle` 的未读读取（`:356` 附近）均未变。
- 受影响词条：[[tables/queue-batches]]、[[tables/queue-inbox]]、[[symbols/queue-finish]]、[[concepts/group-identity-evidence]]、[[concepts/identity-authority]]、[[concepts/message-pipeline]]、[[concepts/model-error-contract]]、[[concepts/unread-capture-retry]]。

## 接口与字段

这 8 个词条描述的 HTTP 契约、批量状态、身份字段和未读退避都没有变化。唯一新增的投递事件键 `mention_residue` 与草稿清理规则已在 [[concepts/delivery-state]]、[[tables/queue-outbox]] 和 [[symbols/mention-selection]] 记录，不在本记录重复。

## 数据库与迁移

不适用：无 schema 变化；`mention_residue` 只是 `delivery_events.details` 的读时白名单键，`draft_text` 是既有列。

## 前端消费点

不适用：管理台复用同一份白名单常量，新增键自动透出。

## 测试与异步任务

复核依据是既有离线用例与本次新增的提及用例（`tests/unit/text/test_true_mentions.py`、`tests/unit/queue/*`、`tests/unit/wxbot/*`）；未新增定时任务。

## 风险与回滚

复核结论是「无影响」：批次/身份/未读路径都不读取草稿所有权或 `mention_residue`。若后续把 `mention_residue` 用于自动重试判定，必须同时更新 [[concepts/delivery-state]] 与 [[symbols/queue-store]]，避免与 `manual_required` 的人工处置语义混用。
