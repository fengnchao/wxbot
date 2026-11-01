---
type: change
title: 知识库 vault 词条与实现对齐
pages:
- tables/knowledge-vault
---
# 知识库 vault 词条与实现对齐

## 目标与背景

[[tables/knowledge-vault]] 首次入库后，用真实历史数据跑了一遍 `migrate_legacy` 演练，发现词条复述了 `knowledge_store.py` 模块 docstring 的两处**设想**，与实现行为不符：

1. docstring 说「事实可以双链溯源到当天日记」，但 `_fact_line`（`knowledge_store.py:128`）只把 `links` 里的实体名写成双链，**从不生成指向日记文件的双链**。溯源靠事实行尾注释的 `at` 与 `quote`。
2. docstring 说「事实要能点回原话才有说服力」，同样暗示了并不存在的链接关系；实际能力是「注释里保留原话片段 `quote` + 时间戳」，不是可点击的链接。

这两句会误导后来者以为 graph view 里能看到「事实指向对话」的边，实际日记文件是孤立节点。词条以代码为准，不照抄 docstring。

第三处是 `_safe()` 的描述不精确：实现是**替换成 `-`**（`re.sub`），不是「去掉」。

## 文件与代码位置

- `src/butler/runtime/knowledge_store.py:11` — docstring 里的错误表述「事实可以双链溯源到当天日记」，本次**不改代码**，只在词条里标注它属于早期设想。
- `src/butler/runtime/knowledge_store.py:19` — docstring 里的「事实要能点回原话才有说服力」。
- `src/butler/runtime/knowledge_store.py:128` — `_fact_line`，双链只来自 `links` 参数。
- `src/butler/runtime/knowledge_store.py:69` — `_safe`，`re.sub(r'[\x00-\x1f<>:"/\\|?*#^\[\]]', '-', ...)`。
- `llm wiki/wxbot/tables/knowledge-vault.md` — 三处表述修正。

## 接口与字段

不适用：本次只改词条，不涉及任何 HTTP 接口、DTO 或工具 schema。

## 数据库与迁移

不适用：不涉及 schema 与迁移脚本改动。本次改动来自一次**在副本上执行的迁移演练**（把 `data/knowledge` 与 `data/business.sqlite3` 复制到临时目录后跑 `migrate_legacy`），真实数据未被触碰。

演练结果作为事实依据：5 条原文 + 1 条事实 + 1 条 `memory` 记录迁入 vault，产出 `p-*/vault/人物/101.md`、`p-*/vault/对话/2026-11-01.md` 与 `index.json`；旧库改名为 `*.migrated`。

## 前端消费点

不适用：词条改动不影响 `KnowledgeView.vue` / `FactsView.vue`。

## 测试与异步任务

不适用：无代码改动，无新增用例。演练脚本是一次性命令，未入库。图谱校验为 `wiki.py lint`。

## 风险与回滚

风险：无运行时风险，纯文档订正。

遗留：`knowledge_store.py` 的 docstring 仍保留两处与实现不符的说法。本次按「代码是事实源、词条是导航」的原则在词条里显式标注差异，没有修改源码注释——改注释属于代码改动，需要单独一次变更与测试，不在文档收口范围内。

回滚：删除本条记录并把 `tables/knowledge-vault` 的三处表述改回即可；但那样会重新引入误导，不建议。

[[tables/knowledge-vault]]
