# 项目知识图谱

先读 [[guide]]；覆盖范围见 [[coverage]]。代码是事实源，词条是经过核对的导航。

## modules / module

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [[modules/butler]] | 身份、权限、模型编排和业务工具的服务边界 | `src/butler/server.py:50` | 2026-11-01 |
| [[modules/common]] | 仓库根、事件追踪、流和 wire schema 的跨包纯基础层 | `src/common/paths.py:29` | 2026-11-01 |
| [[modules/dashboard]] | 聚合运行事实，读取队列不初始化或迁移数据库 | `src/dashboard/routes.py:57` | 2026-11-03 |
| [[modules/delivery]] | 主动推送、补发、媒体与提醒归业务服务所有 | `src/butler/delivery/push.py:19` | 2026-11-03 |
| [[modules/identity]] | 统一人物、窗口和成员绑定，身份能力由服务端签发 | `src/butler/identity/contact_store.py:37` | 2026-11-01 |
| [[modules/models]] | Butler 管理可切换模型与服务授权工具，wxbot 只调用 Butler | `src/butler/backends/__init__.py:12` | 2026-11-01 |
| [[modules/plugin]] | 角色和工具 Skill 分类，权限仍由业务服务验证 | `src/butler/agent/catalogue.py:8` | 2026-11-02 |
| [[modules/runtime]] | 安装、迁移、并发、MCP 与知识库提炼调度等运行基础设施 | `src/butler/runtime/setup.py:28` | 2026-11-02 |
| [[modules/telegram]] | Telethon、Bot API 和桌面中继三个不同边界 | `src/butler/channels/telegram/bot/queue.py:9` | 2026-11-01 |
| [[modules/web]] | 共享导航壳和现有请求封装的管理界面 | `web/src/router.js:11` | 2026-11-03 |
| [[modules/wiki]] | 本地关键词检索、证据入库和一致性巡检 | `AGENTS.md:28` | 2026-11-02 |
| [[modules/wxbot]] | 微信 UI 主线程与不接触 UI 的模型队列线程 | `src/wxbot/voice/assets.py:80` | 2026-11-03 |

## apis / api

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [[apis/butler-handle]] | 同步消息处理契约，从 wxbot 批次到完整 Butler 回复 | `src/butler/server.py:349` | 2026-11-01 |
| [[apis/butler-handle-stream]] | SSE 增量观察与最终 result，断流不能当完整结果 | `src/butler/server.py:370` | 2026-11-01 |
| [[apis/dashboard-knowledge]] | 对话原文与知识图谱事实的只读查询、自动提炼的状态与手动触发转发，以及知识模板的读取与校验保存；vault 不存在时返回空态而不是错误 | `src/dashboard/routes.py:45` | 2026-11-02 |
| [[apis/dashboard-queue]] | 队列分页诊断，展示状态和可用动作而不执行恢复 | `src/dashboard/routes.py:44` | 2026-11-02 |
| [[apis/dashboard-voice-assets]] | 音色资产 CRUD、参考音预览与会话 contact_refs 绑定 | `src/dashboard/routes.py:57` | 2026-11-03 |
| [[apis/dashboard-workflow]] | 队列与 Telegram 工作流只读聚合及前端消费 | `src/dashboard/routes.py:41` | 2026-11-02 |

## tables / table

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [[tables/kb-episodes]] | 已退场——SQLite 时代的 L1 原文表，现由 vault 里的「对话/YYYY-MM-DD.md」承担，只保留迁移读入口 | `src/butler/runtime/knowledge_store.py:48` | 2026-11-02 |
| [[tables/kb-facts]] | 已退场——L2 事实表被 vault 里的「人物/组织/话题」节点 Markdown 取代，只保留迁移读入口 | `src/butler/runtime/knowledge_store.py:50` | 2026-11-02 |
| [[tables/kb-owners]] | 已退场——owner 目录与提炼游标改为可重建的 index.json，SQLite 索引库只在迁移时被改名留底 | `src/butler/runtime/knowledge_store.py:325` | 2026-11-02 |
| [[tables/knowledge-vault]] | 用户知识图谱的存储形态——一人一个 Obsidian vault，目录骨架、事实分类与索引分区由 Markdown 模板决定 | `src/butler/runtime/knowledge_store.py:1` | 2026-11-02 |
| [[tables/queue-batches]] | 模型请求批次与最终回复完整性，非发送回执 | `src/wxbot/queue_schema.py:34` | 2026-11-02 |
| [[tables/queue-inbox]] | 原始收件与群成员证据，batch_id 指向合并批次 | `src/wxbot/queue_schema.py:34` | 2026-11-02 |
| [[tables/queue-outbox]] | 逐分句发件与不确定结果审计，包含迁移新增字段 | `src/wxbot/queue_schema.py:34` | 2026-11-03 |

## symbols / symbol

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [[symbols/butler-handle]] | 单轮身份解析、会话互斥、补发优先与最终合成 | `src/butler/agent/core.py:213` | 2026-11-01 |
| [[symbols/butler-processor]] | wxbot 的 Butler HTTP 适配及完整结果校验 | `src/wxbot/processor/butler.py:60` | 2026-10-31 |
| [[symbols/butler-result]] | 生成 reply/actions/reply_parts/meta 的公开边界 | `src/butler/agent/core.py:68` | 2026-11-01 |
| [[symbols/knowledge-auto]] | Butler 进程内的定时提炼调度器，一轮只喂模型一批，并与 CLI 共用跨进程单飞锁 | `src/butler/runtime/knowledge_auto.py:29` | 2026-11-01 |
| [[symbols/knowledge-extract]] | 从对话原文提炼知识图谱节点的链路，模板决定分类、节点类型与追加规则，CLI 与进程内调度器共用，游标只在整批成功后前移 | `src/butler/runtime/knowledge_extract.py:25` | 2026-11-02 |
| [[symbols/knowledge-template]] | 知识图谱模板的解析与加载——一份 Markdown 决定节点目录、事实分类、索引分区与提炼规则，覆盖层优先，坏模板回退内置 | `src/butler/runtime/knowledge_template.py:28` | 2026-11-02 |
| [[symbols/local-model-backend]] | 原生函数工具走服务签发身份，完整结果才进入历史 | `src/butler/backends/models.py:16` | 2026-11-01 |
| [[symbols/mention-selection]] | UI 线程内的 @ 提及选择器，先等候选面板再输入昵称，失败时只清理并登记自己输入的字面前缀 | `src/wxbot/wechat/mentions.py:67` | 2026-11-02 |
| [[symbols/model-worker]] | 领取批次、调用模型并保存回复，绝不访问 UI | `src/wxbot/queue_worker.py:45` | 2026-11-03 |
| [[symbols/queue-finish]] | 完整分句入 outbox，模型完成和发送完成分开 | `src/wxbot/queue_store.py:339` | 2026-11-02 |
| [[symbols/queue-store]] | 短事务管理收件、合批、模型状态与 UI 发件状态 | `src/wxbot/queue_store.py:91` | 2026-11-02 |
| [[symbols/reloadable-backend]] | 请求固定后端代际，在途完成后才关闭旧工作进程 | `src/butler/runtime/model_switch.py:50` | 2026-10-31 |
| [[symbols/voice-asset-store]] | 本地 WAV 音色资产清单与文件存储 | `src/wxbot/voice/assets.py:80` | 2026-11-03 |

## concepts / concept

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [[concepts/delivery-state]] | 完整回复、排队、已发送和结果不确定分别处理 | `src/wxbot/queue_store.py:339` | 2026-11-03 |
| [[concepts/group-identity-evidence]] | 群成员先按同群 member_key 与昵称认人，头像 dhash 只作证据且不足以区分个体 | `src/butler/identity/user_registry.py:350` | 2026-11-02 |
| [[concepts/identity-authority]] | 窗口/头像/昵称是证据，服务签发上下文才是工具授权边界 | `src/butler/agent/tools.py:43` | 2026-11-02 |
| [[concepts/message-pipeline]] | 窗口→收件→批次→Butler→分句→UI→只读投影 | `src/wxbot/inbox.py:264` | 2026-11-03 |
| [[concepts/model-error-contract]] | 模型失败的分类、脱敏、自动重试与超时放行契约 | `src/butler/agent/hermes.py:36` | 2026-11-03 |
| [[concepts/unread-capture-retry]] | 未读任务只有采集成才清除，读不到文字时必须退避并最终放弃，否则阻塞发送队列 | `src/wxbot/inbox.py:449` | 2026-11-02 |
| [[concepts/voice-asset-binding]] | 会话须有可用音色绑定才合成/RALT；绑定与 voice.contacts 模式正交 | `src/wxbot/voice/policy.py:103` | 2026-11-03 |

## 影响分析与台账

影响报告包含待核对的草稿，不能当成已验证的业务结论。

- [[impacts/2026-10-31-group-identity-nickname]]
- [[impacts/2026-10-31-knowledge-graph-bootstrap]]
- [[impacts/2026-10-31-switchable-models]]
- [[impacts/2026-11-01-knowledge-atlas-index]]
- [[impacts/2026-11-01-knowledge-vault-graph]]
- [[impacts/2026-11-02-knowledge-graph-template]]
- [[raw/changes/2026-10-31-group-identity-nickname]]
- [[raw/changes/2026-10-31-identity-placeholder-names]]
- [[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
- [[raw/changes/2026-10-31-model-access-switch-core-emit]]
- [[raw/changes/2026-10-31-model-access-switch]]
- [[raw/changes/2026-10-31-queue-batches-format]]
- [[raw/changes/2026-10-31-switchable-models]]
- [[raw/changes/2026-11-01-citation-sweep]]
- [[raw/changes/2026-11-01-knowledge-atlas-index]]
- [[raw/changes/2026-11-01-knowledge-atomic-retry]]
- [[raw/changes/2026-11-01-knowledge-auto]]
- [[raw/changes/2026-11-01-knowledge-episodes]]
- [[raw/changes/2026-11-01-knowledge-migrate-source-recheck]]
- [[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]
- [[raw/changes/2026-11-01-knowledge-sessions]]
- [[raw/changes/2026-11-01-knowledge-sharding]]
- [[raw/changes/2026-11-01-knowledge-vault-alignment]]
- [[raw/changes/2026-11-01-knowledge-vault-graph]]
- [[raw/changes/2026-11-01-mention-fallback-unread-retry]]
- [[raw/changes/2026-11-01-model-error-contract]]
- [[raw/changes/2026-11-01-model-request-error-visibility]]
- [[raw/changes/2026-11-01-readme-unread-note]]
- [[raw/changes/2026-11-02-details-whitelist-reverify]]
- [[raw/changes/2026-11-02-knowledge-graph-template]]
- [[raw/changes/2026-11-02-mention-picker-gating-residue]]
- [[raw/changes/2026-11-02-mention-residue-reverify]]
- [[raw/changes/2026-11-02-ui-snapshot-ref-contract]]
- [[raw/changes/2026-11-02-web-global-search-clear]]
- [[raw/changes/2026-11-03-feat-voice-001-anchor-refresh]]
- [[raw/changes/2026-11-03-feat-voice-001-virtual-mic]]
- [[raw/changes/2026-11-03-feat-voice-002-indextts]]
- [[raw/changes/2026-11-03-feat-voice-003-model-worker-drift]]
- [[raw/changes/2026-11-03-feat-voice-003-voice-assets]]
- [[raw/changes/2026-11-03-indextts-enqueue-media]]
