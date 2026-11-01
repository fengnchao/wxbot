---
type: change
title: 会话维度：左栏按人、右栏按私聊/群聊再筛
pages: [apis/dashboard-knowledge, tables/kb-episodes, tables/kb-facts, tables/kb-owners,
  symbols/knowledge-extract, modules/web]
---
# 会话维度：左栏按人、右栏按私聊/群聊再筛

## 目标与背景

管理台选中「101」以后，右栏同时列出这个人的私聊与群聊原文，而左栏只有一行「101」，既看不出这个人在几个会话里说过话，也无法只看其中一个会话。原因是左栏一行代表一个 `owner`（人），而 [[tables/kb-episodes]] 里一个 `owner` 可以对应多个 `(contact, channel_type)`。

本批不推翻「一人一库」：左栏仍按人一行，把会话维度补成左栏副标题的说明加右栏的二次筛选。

## 文件与代码位置

- `src/butler/runtime/knowledge_store.py`
  - `_filters`（`:107`）新增 `contact` / `channel_type` 两个可选精确匹配条件。
  - `read_episodes`（`:150`）把这两个条件透传给 `_filters`；签名从 5 参变 7 参，默认值保持向后兼容。
- `src/dashboard/knowledge_view.py`
  - 新增 `_sessions`（`:85`）、`owners(kind)`（`:103`）、`_episode_sessions`（`:186`）、`_fact_sessions`（`:194`）。
  - `read`（`:116`）加 `contact` / `channel_type`，`facts`（`:152`）加 `contact`。
  - `_fact_where`（`:207`）/ `_count_facts`（`:218`）/ `_read_facts`（`:223`）新增 `contact` 条件。
- `src/dashboard/api/knowledge.py`
  - 新增 `_session(ctx)`（`:16`）：`channel_type` 只认 `dm` / `group`，其余当没填。
  - `read`（`:25`）与 `facts`（`:36`）改成经 `_session` 取参数。
- `web/src/views/KnowledgeView.vue`、`web/src/views/FactsView.vue`
  - 新增 `session` 状态、`sessions` / `activeSession` 计算属性与 `keyOf` / `sessionText` / `sessionSummary` / `selectSession`。
  - 左栏副标题改成会话摘要；右栏标题下新增会话 chips（`KnowledgeView.vue:154`、`FactsView.vue:162`），仅当这个人有多个会话时出现。
- `web/src/styles/knowledge.css`：新增 `.session-bar` 一节，只用既有令牌（`--bg2` / `--bg3` / `--line` / `--line-2` / `--wx` / `--fg` / `--fg2` / `--fg3`）。

## 接口与字段

两条 GET 各加两个可选查询参数，响应外层结构不变：

| 参数 | 取值 | 语义 |
|---|---|---|
| contact | 任意字符串 | 精确匹配 `kb_episodes.contact` / `kb_facts.contact`；空表示不缩 |
| channel_type | `dm` / `group` | 与 `contact` 组合定位一个会话；**只对原文生效**，事实表没有这一列 |

[[apis/dashboard-knowledge]] 的 `owners[]` 每项新增 `sessions: [{contact, channel_type, count}]`，按 `count` 倒序。原文页的 `channel_type` 取自 `kb_episodes`；事实页恒为空串，因为 [[tables/kb-facts]] 不记会话类型——页面不假装能分。

`owners` 依旧恒为全量：会话筛选只缩 `rows` 与 `total`，不把人从左栏拿走。

## 数据库与迁移

不涉及。没有新增表、列或索引；`contact` 与 `channel_type` 都是 [[tables/kb-episodes]] 的既有列，[[tables/kb-facts]] 只用到既有的 `contact`。索引库 [[tables/kb-owners]] 不参与本批改动。

## 前端消费点

- 左栏副标题由「群聊，N 条原文」改成「私聊 101、群聊 鸭王集训营，N 条原文，0 条事实」，超过两个会话折成「等 N 个会话」。
- 右栏的会话 chips 与顶部计数 chips 同样式，用 `aria-pressed` 表达选中态，`:focus-visible` 用既有强调色内描边。
- 换人时清空会话筛选，避免把上一个人的会话条件带到下一个人。

## 测试与异步任务

- `tests/dashboard/test_knowledge_view.py` 新增 `test_sessions_list_every_conversation_of_one_person`、`test_session_filter_narrows_rows_within_one_person`，并在事实用例与 HTTP 用例里补 `contact` / `channel_type` 断言（含非法 `channel_type` 回落成不筛）。该文件用例数由 9 增至 12。
- 未新增异步任务：筛选全部在请求内同步完成。

## 风险与回滚

- 左栏现在要为每个 owner 多开一次 `episodes.sqlite3` / `facts.sqlite3` 只读连接来取会话清单，联系人规模大时是 O(人数) 次文件打开；库文件缺失时按空数组短路，不建文件。
- 事实页的 `channel_type` 恒为空，同名的私聊与群聊在事实页分不开。这是数据模型限制，不是实现漏项。
- 回滚只需撤掉前端 chips 与 `_sessions` 调用；`_filters` 的新参数有默认值，单独保留不改变既有行为。
