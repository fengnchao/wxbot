---
type: change
title: 投递细节白名单扩展的词条复核
pages: [concepts/identity-authority, concepts/model-error-contract, symbols/queue-finish,
  tables/queue-batches, tables/queue-inbox]
---
# 投递细节白名单扩展的词条复核

## 目标与背景

[[raw/changes/2026-11-02-ui-snapshot-ref-contract]] 扩展了 `queue_store.py` 的
`FAILURE_DETAIL_FIELDS`（增加 `retry`、`confirm_evidence`、`ref_available`）。这 5 个词条都以该文件为来源，
虽然没有语义变化，但源码指纹变了，需要逐条对照复核并登记，否则巡检会一直报 `source-drift`。

## 文件与代码位置

- `src/wxbot/queue_store.py:21` — `FAILURE_DETAIL_FIELDS` 的集合字面量行数未变，`claim_batch`（`:309`）、
  `finish_batch_parts`（`:339`）、`_insert_delivery`（`:321`）、`_recompute_batch`（`:359`）、
  `capture`（`:239`）、`finish_delivery`（`:591`）、`retry_failed_deliveries`（`:632`）的位置与实现均未变。
- `src/wxbot/queue_store.py:350` — `member_name = str(mention_name or '').strip()` 仍只取服务给出的 mention_name。

## 接口与字段

这 5 个词条描述的字段、状态机、放行规则都没有变。唯一新增的是投递事件细节白名单里的键，
已在 [[concepts/delivery-state]] 与 [[tables/queue-outbox]] 记录，不在本记录重复。

## 数据库与迁移

不适用：无 schema 变化，`FAILURE_DETAIL_FIELDS` 只是读时过滤常量。

## 前端消费点

不适用：管理台复用同一常量，新增键自动透出，本记录不引入网页改动。

## 测试与异步任务

复核依据是既有离线用例（`tests/unit/queue/test_delivery_queue.py`、`test_delivery_failure_policy.py`、
`test_queue_store.py`）与本次新增的 `tests/unit/wxbot/test_ui_contract.py`；未新增定时任务。

## 风险与回滚

复核结论是「无影响」：批次状态机、模型失败放行、身份 mention_name 解析都不经过细节白名单。
若后续把 `retry` 用于自动重试判定，必须同时更新 [[concepts/delivery-state]] 与
[[concepts/model-error-contract]]，避免两套失败语义混用。
