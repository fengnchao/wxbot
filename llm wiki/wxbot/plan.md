# 项目知识图谱 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 在当前会话完成各项，保留用户已有工作。

**Goal:** 在已有 Obsidian 库内形成可执行、可追溯的查图与增量维护闭环。

**Architecture:** Markdown 是语义知识，raw 是追加台账，Python 仅做检索、结构检查和入库登记。AGENTS.md 约束开发模型维护流程。

**Tech Stack:** Python、现有 PyYAML、Markdown、Obsidian 双链。

**Spec:** [[design]]

## Global Constraints

所有图谱文件置于 `llm wiki/wxbot/`；不覆盖 Obsidian 配置；不读取运行时数据和秘密；不重启或发消息；保留脏工作树中其他改动。

## Review Focus

- 路径越界或指向秘密的来源必须拒绝，失败前不得写图谱。
- raw 入库后改写必须报错，再次入库相同记录不能重复追加日志。
- 查询应同时找到出链和入链，命中为空时明确要求回到源码建档。
- 代码变化、断链及漏入库应有可操作的巡检诊断。
- 词条关系及契约有人工核对边界，不将脚本检查当作语义证明。

## Tasks

- [x] 1. 用临时仓库编写命令测试，运行确认功能缺失；实现 query / change / ingest / lint / status 并运行回归。
- [x] 2. 阅读消息处理链路源码，建模块导航和核心 API、表、符号、概念词条；补齐模板、覆盖范围和操作说明。
- [x] 3. 在根 AGENTS.md 接入查图/修改记录/入库规范，README 加入口；本次实施也写 raw 和影响分析，完成真实入库。
- [x] 4. 执行离线测试、真实查询及 lint；核查仅修改本次范围并报告边界。专项 20 passed / 1 skipped；整库回归限制见 [[verification]]。
