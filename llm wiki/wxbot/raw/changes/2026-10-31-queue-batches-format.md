---
type: change
title: 保留 batches 词条后续表格排版
pages:
- tables/queue-batches
---
# 保留 batches 词条后续表格排版

## 目标与背景

首批入库后，交付前的再次巡检发现 queue-batches.md 摘要变化。检查发现字段表格列对齐和空白行变化，事实内容未变；保留当前排版，不用初始生成内容覆盖它。此记录接续 [[raw/changes/2026-10-31-knowledge-graph-bootstrap]]。

## 文件与代码位置

`llm wiki/wxbot/tables/queue-batches.md:36` 的最终结构字段表发生排版变化。核对 `src/wxbot/queue_schema.py:34`、`:84`、`:149` 及 `src/wxbot/queue_store.py:300`、`:330`，字段和来源仍一致。更新 [[tables/queue-batches]] 修改来源并重新登记快照。

## 接口与字段

不涉及接口/DTO 变更；表格中的字段名、类型、约束和默认值未改变。

## 数据库与迁移

不涉及数据库或迁移，只核对源码中的 schema，未读取实际数据库。

## 前端消费点

不涉及业务前端，只保留 Obsidian Markdown 排版；不修改原有 Obsidian 设置。

## 测试与异步任务

无新增任务或业务代码。脚本专项回归仍为 20 passed / 1 skipped；重新执行 ingest / lint / status 核对图谱闭环。验证限制见 [[verification]]。

## 风险与回滚

没有业务语义影响。后续对已入库词条的编辑仍会触发 page-drift，必须复核后以新记录入库，不改历史 raw 或直接改证据摘要。保留本次排版，无需业务服务重启。
