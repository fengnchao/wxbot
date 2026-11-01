---
type: change
title: 迁移改动后复核知识库词条来源
pages:
- apis/dashboard-knowledge
- symbols/knowledge-extract
---
# 迁移改动后复核知识库词条来源

## 目标与背景

上一条记录 [[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]] 在 `src/butler/runtime/knowledge_store.py` 的迁移段插入了 `_checkpoint_legacy`，文件 sha 变化，凡把该文件列为来源的词条都被标成 `source-drift`。本条记录专门收掉这两个词条的复核：确认它们的行号没有被推移，内容也不需要改写。

## 文件与代码位置

- `llm wiki/wxbot/apis/dashboard-knowledge.md`
- `llm wiki/wxbot/symbols/knowledge-extract.md`

两者的 `sources` 里指向 `knowledge_store.py` 的行号分别是 `:501`（`read`）、`:530`（`facts`）、`:568`（`sessions`）与 `:485`（`episodes_of`）。插入位置在 `:593`，全部落在这之前，锚点文本未变，`last_verified` 保持 `2026-11-01`。

## 接口与字段

不适用：没有接口或字段变化。受影响的只是词条的来源指纹。

## 数据库与迁移

不适用：本次不改迁移逻辑，只补复核记录。迁移本身的修复见 [[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]。

## 前端消费点

不适用：`FactsView.vue` / `KnowledgeView.vue` 读的仍是 `KnowledgeStore.read` 与 `.facts`，行为不变。

## 测试与异步任务

不适用：没有新增测试。改动前的验证是 `pytest tests/butler` 全绿，见上一条记录。

## 风险与回滚

风险：无。本条只追加 changes 条目，未改词条正文、未改代码。

回滚：删掉两个词条 `changes` 里的本记录条目即可。
