---
type: change
title: 词条代码引用行号复核
pages:
- concepts/group-identity-evidence
---
# 词条代码引用行号复核

## 目标与背景

上一份记录 [[raw/changes/2026-11-01-mention-fallback-unread-retry]] 入库后，`concepts/group-identity-evidence` 的 frontmatter 已把 `sync_users` 的引用改到 111，但正文「代码依据」段仍留 109。两份引用互相矛盾，且插入行后需要确认其它词条没有同类漂移，因此做一次机械核对并补本记录登记词条变更。

## 文件与代码位置

- `llm wiki/wxbot/concepts/group-identity-evidence.md`「代码依据」段：`src/wxbot/inbox.py:109` 改为 `src/wxbot/inbox.py:111`（`def sync_users(` 实际位置）。
- 复核范围：`llm wiki/wxbot/` 下各词条中所有 `- \`path:line\` — \`…\`` 形式的正文引用，逐条比对「该行是否包含该锚点」。
- 复核结果：命中 6 条差异，其中 5 条是核对脚本的误报——`apis/dashboard-knowledge.md` 两条把代码后的「（GET）」「（POST）」一起当成锚点，`modules/web.md` 一条用 `…` 省略了锚点，`concepts/unread-capture-retry.md` 三条写的是说明文字而不是锚点。真实漂移只有 `sync_users` 这一处。
- 脚本为一次性核对工具，不进仓库。

## 接口与字段

不涉及。

## 数据库与迁移

不涉及。

## 前端消费点

不涉及。

## 测试与异步任务

不改代码，不新增测试。功能测试结果沿用 [[raw/changes/2026-11-01-mention-fallback-unread-retry]]：`tests/unit/wxbot`、`tests/unit/text`、`tests/unit/queue`、`tests/unit/media`、`tests/butler/identity` 只剩 3 个与本轮无关的既有失败。本记录只做图谱引用核对。

## 风险与回滚

纯文档改动，回滚即把行号改回旧值。机械核对只能证明「该行包含该子串」，不能证明语义正确；语义仍需对照源码阅读，漂移也可能出现在锚点相同但上下文已变的情况。
