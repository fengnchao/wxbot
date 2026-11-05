---
type: change
title: 网页预设图谱契约说明补充
pages:
- modules/butler
- modules/dashboard
- modules/delivery
- modules/identity
- modules/plugin
- modules/web
- modules/wiki
- apis/dashboard-knowledge
- apis/dashboard-queue
- apis/dashboard-voice-assets
- apis/dashboard-workflow
- apis/index-tts
- tables/knowledge-vault
- concepts/development-baseline
- concepts/identity-authority
supersedes:
- raw/changes/2026-11-04-webui-preset-binding
---

# 网页预设图谱契约说明

## 目标与背景

补充前条记录后的图谱措辞核对：更正自动追加的“后端契约保持”泛化表述。只有原有音频/图文/联系人接口保持；网页预设增加 GET/POST /api/tts-presets，且工具 preset 改为可省略。本条仅更正图谱说明，不改写已入库 raw，不撤销前条实现。

## 文件与代码位置

记录所列词条的说明与来源已核对；原实现及稳定锚点仍见 [[apis/index-tts]]。无源码、构建或测试修改。

## 接口与字段

新增管理端列表/默认绑定接口，原确认机制、完整联系人校验和版本检查见前条；原有其他接口不变。省略工具 preset 按服务端当前会话默认解析。

## 数据库与迁移

不适用：本条无运行数据或迁移变化。

## 前端消费点

不适用：仅澄清图谱，不改变已构建的下拉框。

## 测试与异步任务

复用前条最终 256 项通过、Vue 烟测与实际路由显示验证；本条仅运行图谱 ingest/lint。无后台任务。

## 风险与回滚

没有运行时风险；保持历史记录不可变，当前词条使用本条补充来源。原有四项图谱待办不在本次修订范围。
