---
type: change
title: FEAT-VOICE-003 连带复核 model-worker 锚点
pages:
  - symbols/model-worker
---
# FEAT-VOICE-003 连带复核 model-worker 锚点

## 目标与背景

queue_worker.py 在 FEAT-VOICE-003 中增加绑定门控后，[[symbols/model-worker]] 来源摘要漂移；复核并刷新锚点行号，不改变符号语义。

## 文件与代码位置

- src/wxbot/queue_worker.py：语音绑定门控（既有 003 改动）；本记录只复核 wiki 锚点
- llm wiki/wxbot/symbols/model-worker.md：更新 sources 行号与 changes

## 接口与字段

不涉及。

## 数据库与迁移

不涉及。

## 前端消费点

不涉及。

## 测试与异步任务

不涉及；wiki.py lint 清除本词条 source-drift。

## 风险与回滚

无运行时风险；回滚删除本 raw 与词条 changes 项即可。
