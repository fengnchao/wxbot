---
type: change
title: README 补不可采集未读的说明与图谱来源修正
pages:
- modules/wiki
---
# README 补不可采集未读的说明与图谱来源修正

## 目标与背景

[[raw/changes/2026-11-01-mention-fallback-unread-retry]] 给未读采集加了退避与放弃，并新增可选配置 `[bot].unread_give_up_attempts`。README 是项目主文档，需要在「微信 UI 与队列」一节写清这个运维可见的默认行为，否则运维只能从日志猜。README 插入三行后，`modules/wiki` 里指向「### 项目知识图谱」的来源行号随之下滑，需要同步登记。

## 文件与代码位置

- `README.md`「微信 UI 与队列」段新增一条：未读只有读到文字才算采集成功，按 `poll_interval` 倍数退避，满 `[bot].unread_give_up_attempts`（默认 5）次放弃并清掉待读任务，未读数或「有人@我」变化后重新纳入；放弃前该会话的发送也被待读任务挡住。
- `modules/wiki` 的来源 `README.md:652` → `README.md:655`（`### 项目知识图谱` 实际位置），`last_verified` 不变（同日）。
- 实现依据仍是 `src/wxbot/inbox.py:440` 的 `_receive_one` 与 `:470` 的 `_abandon_unread`。

## 接口与字段

不涉及接口变更。新增的是 wxbot 运行时可选配置键 `[bot].unread_give_up_attempts`，只在 `MainInbox` 里以 `self.bot.get(...)` 读取，缺省 5，无需改动任何配置文件或配置 schema。

## 数据库与迁移

不涉及表结构。放弃未读时会调用 `QueueStore.forget_session`（`src/wxbot/queue_store.py:229`）删除 `pending_sessions` 中对应行，该表结构未变。

## 前端消费点

不涉及。管理台不展示 `unread_give_up_attempts`，也未新增页面或接口字段。

## 测试与异步任务

只改文档与图谱来源，不新增测试。后端行为测试见 [[raw/changes/2026-11-01-mention-fallback-unread-retry]] 与本地 `tests/unit/wxbot/test_inbox_unread_backoff.py`。图谱自身用 `wiki.py lint` 巡检。

## 风险与回滚

纯文档改动，回滚即删除 README 新增条目并把 `modules/wiki` 的来源行号改回 652。风险是 README 说明与代码默认值脱节：若后续把 `unread_give_up_attempts` 的默认值从 5 改掉，必须同步这段文案。
