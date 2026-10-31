---
type: impact
status: completed
date: '2026-10-31'
---
# 知识图谱落地影响分析

## 需求与初建依据

需求：实现用户提供的 Markdown 项目图谱方案，文件放在 `llm wiki/`。初建前仅有 `llm wiki/wxbot/.obsidian/`，无可查询词条，故先读 README、AGENTS 和消息处理源码建档。实施方案 [[design]]，步骤 [[plan]]，覆盖界限 [[coverage]]。

## 实际修改范围与调用方

- 根 `AGENTS.md:28` 接入查图、影响分析、raw、模型整合和命令入库纪律。
- 根 `README.md:611` 增加项目入口和命令，不重复项目运行说明。
- [[modules/wiki]] 记录本地命令的准确代码位置；其唯一共享路径依赖是 `src/common/paths.py:29` 的 REPO_ROOT。
- [[modules/wiki]] 及 26 个其它词条、7 个模板、索引、日志和证据快照均在既有库内。保留 Obsidian 个人设置。

## 接口、前端与数据库

业务 HTTP/DTO、SQL schema、前端源码/构建产物均未修改。本次只读代码建立 [[apis/butler-handle]]、[[apis/butler-handle-stream]]、[[apis/dashboard-workflow]]、[[apis/dashboard-queue]] 以及三个队列表映射。图谱脚本不读取真实数据库、运行时配置或认证。

## 验证与风险

CLI 回归使用临时库，详见 [[verification]]。机器检查不能替代模型读代码；语义盲区见 [[coverage]]。来源完整文件摘要对无关修改也敏感，需要后续核对。脏工作树既有其它变更，本次建档不代表那些变更的验证。

不启动、停止或重启服务，不发送微信，不调用模型或网络。回滚可移除本次知识目录新增资产并撤销 AGENTS/README 中本段入口，保留此前已有 `.obsidian` 设置和其它用户工作。历史修改记录不能为了回滚而改写。

## 修改记录

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
