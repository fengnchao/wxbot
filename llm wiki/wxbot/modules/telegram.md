---
type: module
module: telegram
summary: Telethon、Bot API 和桌面中继三个不同边界
coverage: overview
last_verified: '2026-10-31'
sources:
- path: src/butler/channels/telegram/bot/queue.py
  line: 9
  anchor: 'class Queue:'
- path: src/butler/channels/telegram/relay/store.py
  line: 12
  anchor: 'def '
- path: src/wxbot/telegram_desktop.py
  line: 41
  anchor: 'class '
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
---
# Telegram 外部通道

## 范围

Butler 的 `channels/telegram/` 包括 Telethon 接收、bot/ 入库和 relay/ 配置/持久任务；桌面自动化仅在 wxbot 的 telegram_desktop 中执行。三者不能混为一个队列或共享认证。

## 关系与缺口

通道属于 [[modules/butler]]，桌面 UI 属于 [[modules/wxbot]]；聚合展示由 [[modules/dashboard]] 承担。完整队列表、消息去重和媒体重试协议尚待建档。禁止为图谱收集真实频道消息或 session 文件。

## 代码依据

- `src/butler/channels/telegram/bot/queue.py:9` — `class Queue:`
- `src/butler/channels/telegram/relay/store.py:12` — `def `
- `src/wxbot/telegram_desktop.py:41` — `class `

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
