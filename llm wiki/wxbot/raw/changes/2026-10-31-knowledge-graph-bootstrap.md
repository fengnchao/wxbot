---
type: change
title: 项目知识图谱首批建档与维护闭环
pages:
- apis/butler-handle
- apis/butler-handle-stream
- apis/dashboard-queue
- apis/dashboard-workflow
- concepts/delivery-state
- concepts/identity-authority
- concepts/message-pipeline
- modules/butler
- modules/common
- modules/dashboard
- modules/delivery
- modules/identity
- modules/plugin
- modules/runtime
- modules/telegram
- modules/web
- modules/wiki
- modules/wxbot
- symbols/butler-handle
- symbols/butler-processor
- symbols/butler-result
- symbols/model-worker
- symbols/queue-finish
- symbols/queue-store
- tables/queue-batches
- tables/queue-inbox
- tables/queue-outbox
---
# 项目知识图谱首批建档与维护闭环

## 目标与背景

按用户提供的方案实现可持续维护的 Markdown 知识图谱。使用已有 llm wiki/wxbot Obsidian 库，与项目一起版本化；不创建另一套运行时知识或服务。初建前无词条可查询，先读 README/AGENTS 和匹配源码，影响分析见 [[impacts/2026-10-31-knowledge-graph-bootstrap]]。

## 文件与代码位置

- `AGENTS.md:28`：开发模型改前查询、改后记录/整合/入库的纪律；保留已有 Hallmark 等规则。
- `README.md:611`：图谱目录、操作入口与命令。
- `llm wiki/wxbot/scripts/wiki.py`：Wiki 读取、结构检查、证据快照；准确行号及 ingest/query/main 位置以 [[modules/wiki]] 为准。
- `llm wiki/wxbot/`：27 个 modules/apis/tables/symbols/concepts 词条、7 个模板、guide/coverage/design/plan/verification、影响分析、索引、日志与 ingest-state.json。词条逐项携来源路径、行号和锚点；完整词条范围见本记录 pages。
- `src/butler/server.py:308`、`src/butler/agent/core.py:205`、`src/wxbot/queue_store.py:330` 等仅作为核对来源，未修改它们。

本次基于脏工作树快照建档，不替已有源码变更追认作者/目的或验证结果。指定的 knowledge/资料库/README.md 在本安装不存在，未使用不存在的外部知识。

## 接口与字段

不涉及业务 HTTP/DTO 变更。新增开发命令 query/change/ingest/lint/status；语义抽取由模型完成，CLI 只检索、检查和登记。词条元信息 sources 是 path/line/anchor 对象列表，changes 指向追加 raw。calls/called_by 表示已核对关键关系，depends_on 只用于显式模块依赖，不等于全部静态调用分析。

## 数据库与迁移

不涉及业务数据库变更或运行时迁移，不读真实数据库。三个队列表按 queue_schema.py 的初始建表与升级补列建立最终结构说明；额外的 ingest-state.json 只是开发证据台账，存归一化文本摘要和来源路径，不存业务内容。

## 前端消费点

不涉及前端实现改动或 dist 重建。只读 WorkflowView.vue:356 和 QueueView.vue:248 等消费点，将它们链到管理台 API。前端契约不是另造 TypeScript DTO；项目实际采用 Vue/JS 消费字段。保留既有 Obsidian 配置，忽略个人工作区/缓存。

## 测试与异步任务

新增本地 tests/unit/test_project_wiki.py，以临时库执行真实 CLI。最终 20 项通过、1 项因无法创建真实 Windows 目录联接而跳过；另有确定性路径解析回归验证拒绝逻辑，详见 [[verification]]。首次失败来自命令尚未实现，随后逐项完成。审查修复来源/词条路径重定向和历史来源丢失问题，增量更新也已测试。工具不调模型、服务、调度器或消费者，没有新增运行任务。

整库回归已有多项失败并在约 10% 后停滞，中止本次测试后用 --maxfail=1 定位：53 passed / 1 failed，失败在 test_contact_migration.py:412 的 nonlocal deepseek 安装用例；不宣称整个工作树通过。

## 风险与回滚

首批完整覆盖消息处理核心，其余模块只做概览，缺口见 [[coverage]]。完整来源文件摘要对无关行修改也提示复核；机械 lint 无法证明接口语义、遗漏调用方和业务规则正确。避免并发写图谱；同一记录已入库后不可改写，有错追加 supersedes 更正记录。

本次未重启服务、未发微信、未读凭据/运行数据，未提交或发布。回退本次新增知识资产及 AGENTS/README 新增入口时保留已有 Obsidian 设置和用户其它改动；历史记录不静默改写。待办：逐模块补齐身份/提醒/Telegram 等细节；整库失败由相应功能任务处理。
