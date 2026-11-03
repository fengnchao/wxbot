---
type: change
title: FEAT-VOICE-001 连带锚点刷新
pages:
- symbols/model-worker
- symbols/queue-finish
- symbols/queue-store
- concepts/group-identity-evidence
- concepts/identity-authority
- concepts/model-error-contract
- concepts/unread-capture-retry
- tables/queue-batches
- tables/queue-inbox
- symbols/mention-selection
supersedes: []
---
# FEAT-VOICE-001 连带锚点刷新

## 目标与背景

`finish_batch_parts` / inbox / chat_window / push 行号位移后，刷新未列入主变更 `pages` 的词条 `sources.line`，消除 source-drift / page-drift。语义仍以主记录 [[raw/changes/2026-11-03-feat-voice-001-virtual-mic]] 为准。

## 文件与代码位置

仅图谱词条 frontmatter `sources.line`；无业务代码。

## 接口与字段

不涉及。

## 数据库与迁移

不涉及。

## 前端消费点

不涉及。

## 测试与异步任务

`wiki.py ingest` + `lint`。

## 风险与回滚

低；回滚本记录即可。
