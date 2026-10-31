# 项目知识图谱

先读 [[guide]]；覆盖范围见 [[coverage]]。代码是事实源，词条是经过核对的导航。

## modules / module

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [[modules/butler]] | 身份、权限、模型编排和业务工具的服务边界 | `src/butler/server.py:47` | 2026-10-31 |
| [[modules/common]] | 仓库根、事件追踪、流和 wire schema 的跨包纯基础层 | `src/common/paths.py:29` | 2026-10-31 |
| [[modules/dashboard]] | 聚合运行事实，读取队列不初始化或迁移数据库 | `src/dashboard/routes.py:26` | 2026-10-31 |
| [[modules/delivery]] | 主动推送、补发、媒体与提醒归业务服务所有 | `src/butler/delivery/push.py:19` | 2026-10-31 |
| [[modules/identity]] | 统一人物、窗口和成员绑定，身份能力由服务端签发 | `src/butler/identity/contact_store.py:37` | 2026-10-31 |
| [[modules/models]] | Butler 管理可切换模型与服务授权工具，wxbot 只调用 Butler | `src/butler/backends/__init__.py:12` | 2026-10-31 |
| [[modules/plugin]] | 角色和工具 Skill 分类，权限仍由业务服务验证 | `src/butler/agent/catalogue.py:8` | 2026-10-31 |
| [[modules/runtime]] | 安装、迁移、并发和 MCP 等运行基础设施 | `src/butler/runtime/setup.py:28` | 2026-10-31 |
| [[modules/telegram]] | Telethon、Bot API 和桌面中继三个不同边界 | `src/butler/channels/telegram/bot/queue.py:9` | 2026-10-31 |
| [[modules/web]] | 共享导航壳和现有请求封装的管理界面 | `web/src/router.js:4` | 2026-10-31 |
| [[modules/wiki]] | 本地关键词检索、证据入库和一致性巡检 | `AGENTS.md:28` | 2026-10-31 |
| [[modules/wxbot]] | 微信 UI 主线程与不接触 UI 的模型队列线程 | `src/wxbot/inbox.py:45` | 2026-10-31 |

## apis / api

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [[apis/butler-handle]] | 同步消息处理契约，从 wxbot 批次到完整 Butler 回复 | `src/butler/server.py:312` | 2026-10-31 |
| [[apis/butler-handle-stream]] | SSE 增量观察与最终 result，断流不能当完整结果 | `src/butler/server.py:333` | 2026-10-31 |
| [[apis/dashboard-queue]] | 队列分页诊断，展示状态和可用动作而不执行恢复 | `src/dashboard/routes.py:42` | 2026-10-31 |
| [[apis/dashboard-workflow]] | 队列与 Telegram 工作流只读聚合及前端消费 | `src/dashboard/routes.py:39` | 2026-10-31 |

## tables / table

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [[tables/queue-batches]] | 模型请求批次与最终回复完整性，非发送回执 | `src/wxbot/queue_schema.py:34` | 2026-10-31 |
| [[tables/queue-inbox]] | 原始收件与群成员证据，batch_id 指向合并批次 | `src/wxbot/queue_schema.py:34` | 2026-10-31 |
| [[tables/queue-outbox]] | 逐分句发件与不确定结果审计，包含迁移新增字段 | `src/wxbot/queue_schema.py:34` | 2026-10-31 |

## symbols / symbol

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [[symbols/butler-handle]] | 单轮身份解析、会话互斥、补发优先与最终合成 | `src/butler/agent/core.py:207` | 2026-10-31 |
| [[symbols/butler-processor]] | wxbot 的 Butler HTTP 适配及完整结果校验 | `src/wxbot/processor/butler.py:60` | 2026-10-31 |
| [[symbols/butler-result]] | 生成 reply/actions/reply_parts/meta 的公开边界 | `src/butler/agent/core.py:64` | 2026-10-31 |
| [[symbols/local-model-backend]] | 原生函数工具走服务签发身份，完整结果才进入历史 | `src/butler/backends/models.py:16` | 2026-10-31 |
| [[symbols/model-worker]] | 领取批次、调用模型并保存回复，绝不访问 UI | `src/wxbot/queue_worker.py:43` | 2026-10-31 |
| [[symbols/queue-finish]] | 完整分句入 outbox，模型完成和发送完成分开 | `src/wxbot/queue_store.py:334` | 2026-10-31 |
| [[symbols/queue-store]] | 短事务管理收件、合批、模型状态与 UI 发件状态 | `src/wxbot/queue_store.py:91` | 2026-10-31 |
| [[symbols/reloadable-backend]] | 请求固定后端代际，在途完成后才关闭旧工作进程 | `src/butler/runtime/model_switch.py:50` | 2026-10-31 |

## concepts / concept

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [[concepts/delivery-state]] | 完整回复、排队、已发送和结果不确定分别处理 | `src/wxbot/queue_store.py:334` | 2026-10-31 |
| [[concepts/group-identity-evidence]] | 群成员先按同群 member_key 与昵称认人，头像 dhash 只作证据且不足以区分个体 | `src/butler/identity/user_registry.py:355` | 2026-10-31 |
| [[concepts/identity-authority]] | 窗口/头像/昵称是证据，服务签发上下文才是工具授权边界 | `src/butler/agent/tools.py:47` | 2026-10-31 |
| [[concepts/message-pipeline]] | 窗口→收件→批次→Butler→分句→UI→只读投影 | `src/wxbot/inbox.py:253` | 2026-10-31 |

## 影响分析与台账

影响报告包含待核对的草稿，不能当成已验证的业务结论。

- [[impacts/2026-10-31-group-identity-nickname]]
- [[impacts/2026-10-31-knowledge-graph-bootstrap]]
- [[impacts/2026-10-31-switchable-models]]
- [[raw/changes/2026-10-31-group-identity-nickname]]
- [[raw/changes/2026-10-31-identity-placeholder-names]]
- [[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
- [[raw/changes/2026-10-31-model-access-switch-core-emit]]
- [[raw/changes/2026-10-31-model-access-switch]]
- [[raw/changes/2026-10-31-queue-batches-format]]
- [[raw/changes/2026-10-31-switchable-models]]
