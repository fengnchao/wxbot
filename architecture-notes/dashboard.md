# 管理台

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 管理台

提供运行状态和配置入口，可查看收发队列、业务数据与本地日记。

## 使用说明

- [wxbot / Butler / 模块与文件职责 / src/dashboard —— 管理台](#doc-3e3095a0cf397c) · `README.md`
- [wxbot / Butler / 模块与文件职责 / src/dashboard —— 管理台 / 组装与传输](#doc-c2fed6bbc9b2f7) · `README.md`
- [wxbot / Butler / 模块与文件职责 / src/dashboard —— 管理台 / api/ —— 只做 HTTP 胶水](#doc-5838a9ba748b33) · `README.md`
- [wxbot / Butler / 模块与文件职责 / src/dashboard —— 管理台 / 视图、数据源与动作](#doc-8a288bbf5df118) · `README.md`
- [wxbot / Butler / 模块与文件职责 / web/ —— 管理台前端](#doc-5c0dd8694810ec) · `README.md`
- [wxbot / Butler / 接口与协议 / 管理台 HTTP](#doc-ac630fe13429c5) · `README.md`
- [wxbot / Butler / 管理台](#doc-e6175b44a5c084) · `README.md`

<a id="doc-3e3095a0cf397c"></a>

### wxbot / Butler / 模块与文件职责 / src/dashboard —— 管理台

来源：`README.md:294`。

##### src/dashboard —— 管理台
<!-- end-migrated-part: doc-3e3095a0cf397c -->

<a id="doc-c2fed6bbc9b2f7"></a>

### wxbot / Butler / 模块与文件职责 / src/dashboard —— 管理台 / 组装与传输

来源：`README.md:296`。

###### 组装与传输

| 文件 | 职责 |
|---|---|
| `dashboard/server.py` | 进程入口（组装层）：`build_server()` + `main()` |
| `dashboard/http.py` | HTTP 传输层：请求解析、鉴权、静态文件、`/app/assets/` 路径校验、异常包装 |
| `dashboard/routes.py` | 单张路由表：方法 + 路径 → api 处理器 |
| `dashboard/services.py` | 服务函数的延迟绑定 |
| `dashboard/settings.py` | 持久化 log 设置；命令行参数与环境变量仍然优先 |
<!-- end-migrated-part: doc-c2fed6bbc9b2f7 -->

<a id="doc-5838a9ba748b33"></a>

### wxbot / Butler / 模块与文件职责 / src/dashboard —— 管理台 / api/ —— 只做 HTTP 胶水

来源：`README.md:306`。

###### api/ —— 只做 HTTP 胶水

统一形态：解析参数 → 调 view／数据源 → 返回 `(status, body)`。

| 文件 | 职责 |
|---|---|
| `api/config.py` | 配置总览与保存：wxbot／Butler 配置、新闻分组设置 |
| `api/contacts.py` | 联系人档案：读取、审计流水、保存（需本机页面确认） |
| `api/users.py` | Butler 用户目录代理；凭证只留服务端，浏览器只看脱敏结果 |
| `api/groups.py` | 用户分组字典：读取与 bind／unbind |
| `api/heartbeat.py` | 角色心跳：策略读写、执行状态、技能目录、立即触发 |
| `api/jobs.py` | 定时任务：按归属分组的总览 + 显式确认后的删除 |
| `api/queue.py` | 收发队列：只读总览 + 显式确认后的重试／确认已发／丢弃 |
| `api/workflow.py` | 消息工作流：总览、单条全文、模型实时输出、记录删除 |
| `api/flow.py` | 消息流转与 wxbot 通道流水（只读日志／库） |
| `api/knowledge.py` | 知识库只读投影与模板读写；模板保存需页面确认头与版本比对 |
| `api/runtime.py` | Butler 运行时状态（经 loopback 代理，凭证不出服务端） |
| `api/relay.py` | Telegram 转发：只读写本机配置，核对动作走 Butler |
| `api/support.py` | Butler 配置、联系人、技能目录与心跳策略的读写（非 HTTP 层） |
| `api/system.py` | 连接方式与进程自查 |
<!-- end-migrated-part: doc-5838a9ba748b33 -->

<a id="doc-8a288bbf5df118"></a>

### wxbot / Butler / 模块与文件职责 / src/dashboard —— 管理台 / 视图、数据源与动作

来源：`README.md:327`。

###### 视图、数据源与动作

| 文件 | 职责 |
|---|---|
| `dashboard/sources.py` | 只读数据源：Hermes 状态库、联系人口径、定时任务、收发消息统计 |
| `dashboard/flowlog.py` | wxbot 流水日志解析、用户分组字典与消息流转聚合 |
| `dashboard/flow_view.py` | 把队列事实与请求 ID 精确关联，不猜测服务是否成功 |
| `dashboard/workflow_view.py` | 只读首页投影：一条消息只占一个当前节点 |
| `dashboard/workflow_content.py` | 按需读单条全文，不在每次轮询里载入正文 |
| `dashboard/workflow_history.py` | 显式清理历史，只针对固定配置的队列路径 |
| `dashboard/model_stream_view.py` | 有界只读的模型身份与公开流投影 |
| `dashboard/reply_rounds.py` | 先分页完整回复组，再取它们的组成块 |
| `dashboard/queue_view.py` | 只读队列诊断，绝不初始化／恢复／迁移队列 |
| `dashboard/queue_actions.py` | 显式恢复动作；不碰 UI，不调 shell |
| `dashboard/config_view.py` | 配置清单，服务端移除密钥 |
| `dashboard/config_editor.py` | 校验后的配置补丁；浏览器输入永远选不到文件系统目标 |
| `dashboard/config_schema.py` | 字段描述与校验（读写共用） |
| `dashboard/directory_view.py` | 目录投影与带版本编辑（走 Butler 的目录服务） |
| `dashboard/runtime_view.py` | 与后端无关的运行时投影；模型凭据不会到浏览器 |
| `dashboard/user_admin.py` | 服务端鉴权的用户管理代理；浏览器不持凭据 |
| `dashboard/knowledge_view.py` | 只读投影：把 vault 里的原文与事实读成页面要的列表 |
| `dashboard/knowledge_template_view.py` | 模板读写：覆盖层优先，严格校验带行号；跨进程锁、版本比对、备份与原子替换 |
| `dashboard/job_admin.py` | 管理台 → Butler 的提醒删除代理 |
| `dashboard/telegram_view.py` | 只读 Telegram 入库／新闻投影；绝不迁移或恢复数据库 |
| `dashboard/telegram_relay_admin.py` | 本机转发配置编辑；不做生命周期或投递操作 |
<!-- end-migrated-part: doc-8a288bbf5df118 -->

<a id="doc-5c0dd8694810ec"></a>

### wxbot / Butler / 模块与文件职责 / web/ —— 管理台前端

来源：`README.md:407`。

##### web/ —— 管理台前端

```
web/index.html            Vite 入口（构建后由服务端在 /app/ 返回）
web/vite.config.js        base=/app/，开发时把 /api 代理到 8788
web/scripts/smoke.mjs     jsdom 冒烟测试（只读，固定假数据）
web/dist/                 构建产物，随仓库提交
```

| 文件 | 职责 |
|---|---|
| `src/main.js` | 应用挂载入口 |
| `src/App.vue` | 导航壳：分组、标题、刷新、自动刷新、列表折叠、全局搜索 |
| `src/router.js` | 扁平标签表：导航顺序、分组与 `?tab=` 路由 |
| `src/api.js` | GET／POST 封装与时间格式化 |
| `src/prefs.js` | 仅展示偏好的 localStorage 读写（白名单控制） |
| `src/flow.js` | 工作流流转文案、事件分组与队列诊断的共用纯函数 |
| `src/workflowState.js` | 工作流页跨标签页保留的快照、选中与概览状态 |
| `src/contactState.js` | 联系人页分类、详情分区、共享状态与动作头请求封装 |
| `src/contactPresentation.js` | 联系人状态、待确认原因、组合筛选和有效角色来源的纯展示规则 |
| `src/configDraft.js` | 配置页草稿、保存状态与文件版本 |
| `src/queueFocus.js` | 工作流 → 收发队列的一次性筛选传递 |
| `src/views/WorkflowView.vue` | 实时工作流首页：消息列表、节点详情、模型实时输出 |
| `src/views/QueueView.vue` | 收发队列：分区、筛选、异常核对按钮与失败记录 |
| `src/views/ContactsView.vue` | 联系人：监听、群昵称、角色／心跳与订阅 |
| `src/views/JobsView.vue` | 定时任务：按归属分组，支持逐条删除 |
| `src/views/ConfigurationView.vue` | 配置管理：分类、搜索、草稿、保存与版本冲突提示 |
| `src/views/TelegramRelayView.vue` | Telegram 转发设置与核对 |
| `src/views/KnowledgeView.vue` | 对话记录：按人与会话筛选的原文与回复（只读） |
| `src/views/FactsView.vue` | 知识库：vault 里提炼出的事实、类型、原话与置信度（只读） |
| `src/views/KnowledgeTemplateView.vue` | 知识模板：展示生效模板全文与解析摘要，校验、保存、恢复内置（仅本机） |
| `src/components/WorkflowNode.vue` | 工作流节点卡片 |
| `src/components/WorkflowTrace.vue` | 单条消息的流转详情与阶段耗时 |
| `src/components/WorkflowWires.vue` | 服务之间的动态连线 |
| `src/components/ConfigField.vue` | 单个配置项的输入控件 |
| `src/components/StructuredEditor.vue` | 复杂结构的 JSON 编辑器 |
| `src/components/ContactDialog.vue` | 联系人详情弹窗 |
| `src/components/ContactMergeDialog.vue` | 人物身份合并预览、明确确认与过期版本处理 |
| `src/components/UserDialog.vue` | 用户绑定编辑：身份、头像参考与修改流水 |
| `src/components/HeartbeatStatus.vue` | 心跳计划时间与最近事件 |
| `src/styles/theme.css` | 主题层：设计令牌、导航、控件与卡片皮肤 |
| `src/styles/dashboard.css` | 基础布局与组件类 |
| `src/styles/workflow.css` | 工作流页专用样式 |
| `src/styles/contacts.css` | 联系人分类、详情分区与窄窗口布局 |
| `src/styles/base.css` | 基础样式与相对导入入口 |

改 `src/` 或样式后必须 `cd web && npm run build` 并提交 `dist/`，否则 `/app/` 仍是旧产物。
新增页面：在 `src/views/` 加组件 → 在 `App.vue` 的 `VIEWS` 注册 → 在 `router.js` 的 `TABS` 加导航项，
并补 `scripts/smoke.mjs` 的断言。
<!-- end-migrated-part: doc-5c0dd8694810ec -->

<a id="doc-ac630fe13429c5"></a>

### wxbot / Butler / 接口与协议 / 管理台 HTTP

来源：`README.md:582`。

##### 管理台 HTTP

- 查询一律 `GET /api/...`，只读，不初始化／恢复／迁移队列，不创建运行锁。
- 写操作一律要求 JSON、专用动作头（如 `X-Wxbot-Queue-Action: 1`、`X-Wxbot-Config-Action: 1`）、
  明确 `acknowledge`，并校验可信 Host 与同源。
- 主要 GET：`/api/workflow`、`/api/workflow-content`、`/api/workflow-stream`、`/api/flow`、
  `/api/wxbot`、`/api/queue`、`/api/configuration`、`/api/contacts`、`/api/users`、`/api/jobs`、
  `/api/groups`、`/api/heartbeat-config`、`/api/heartbeat-status`、`/api/skills`、
  `/api/runtime`、`/api/connection`、`/api/telegram-relay`、`/api/news-config`、`/api/health`、
  `/api/knowledge`、`/api/knowledge/facts`、`/api/knowledge/extract`、`/api/knowledge/template`。
- 主要写：`/api/configuration`、`/api/queue-action`、`/api/queue-delete-unsent`、
  `/api/workflow-delete`、`/api/jobs/delete`、`/api/contacts`、`/api/users`、`/api/groups`、
  `/api/heartbeat-config`、`/api/heartbeat-trigger`、`/api/telegram-relay`、`/api/news-config`、
  `/api/knowledge/extract`、`/api/knowledge/facts/delete`、`/api/knowledge/template`（校验／保存／恢复内置）。
<!-- end-migrated-part: doc-ac630fe13429c5 -->

<a id="doc-e6175b44a5c084"></a>

### wxbot / Butler / 管理台

来源：`README.md:657`。

#### 管理台

入口 `http://127.0.0.1:8788/app/`，根路径 `/` 会 302 到 `/app/` 并保留查询参数。
默认进入 `?tab=workflow` 实时工作流；旧 `?tab=runtime/users/heartbeat/groups` 链接转到「联系人」对应区域。

| 页面 | 内容 |
|---|---|
| 实时工作流 | 每条消息的当前位置、动态连线、工具进度、失败倒计时；点选看正文与完整回复 |
| 收发队列 | 待处理／异常待核对／历史分区，逐类分页；异常旁有重试、确认已发、立即丢弃 |
| 联系人 | 默认会话列表按“私聊 / 群聊”分区并分别计数；另有“私聊 / 群聊 / 待确认”分类，私聊只列有私聊窗口的人，纯群成员从群详情打开资料并可返回原群；状态与问题类型单独筛选，详情分概览、基本资料、AI 设置、主动消息、群身份和身份管理（唯一来源 `data/business.sqlite3`） |
| 定时任务 | 按归属分组的卡片；Butler 提醒可逐条删除 |
| 对话记录 | 每条消息的用户原文、机器人回复与失败标注，按人与会话筛选（只读） |
| 知识库 | vault 里提炼出的长期事实、来源、支撑原话与置信度；可逐条确认删除，也可「立即提炼」一批 |
| 知识模板 | 展示当前生效的模板全文与解析摘要；校验后保存覆盖层，或恢复插件内置；保存前提示只影响后续写入 |
| 配置管理 | 七个分类的可编辑配置：中文名称、用途、来源、生效方式；保留注释、备份与 409 版本冲突 |
| Telegram 转发 | 转发设置与人工核对 |

- 页面只保存排序与列表收起偏好；配置草稿留在内存，刷新整个浏览器会丢失。
- 密钥原值不回传，可显式保持／替换／清空；`***` 占位不能写回配置文件。
- 模型字段按页面的生效提示供后续请求使用，其余文件值不代表运行进程已加载的值；页面不会自动重启服务。
<!-- end-migrated-part: doc-e6175b44a5c084 -->

## 技术资料

- [GET /api/workflow](#doc-0d1f17e6436714) · `llm wiki/wxbot/apis/dashboard-workflow.md`
- [管理台 HTTP 与投影](#doc-bb47c9474691fe) · `llm wiki/wxbot/modules/dashboard.md`
- [Vue 管理台](#doc-aeec90dfe23cd3) · `llm wiki/wxbot/modules/web.md`

<a id="doc-0d1f17e6436714"></a>

### GET /api/workflow

来源：`llm wiki/wxbot/apis/dashboard-workflow.md:1`。

```yaml
type: api
module: dashboard
summary: 队列与 Telegram 工作流只读聚合及前端消费
coverage: core
last_verified: '2026-11-06'
sources:
- path: src/dashboard/routes.py
  line: 44
  anchor: ("GET", "/api/workflow", workflow.read)
- path: src/dashboard/api/workflow.py
  line: 10
  anchor: 'def read(ctx):'
- path: src/dashboard/workflow_view.py
  line: 52
  anchor: 'def read(self, *, now=None):'
- path: web/src/views/WorkflowView.vue
  line: 356
  anchor: fetch('/api/workflow',
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-diary-web
```
### GET /api/workflow

#### 方法、输入与实现

GET `/api/workflow`，本接口没有业务查询 DTO；走 [modules/dashboard](dashboard.md#doc-bb47c9474691fe) HTTP 的访问控制。routes → api.workflow.read → WorkflowView.read，并合入 TelegramView.workflow，最后脱敏。此端点不初始化或修复数据库。

#### 响应摘要

顶层 `status/error`、`sources`、`nodes`、`messages`、`counts`、`backend/model` 以及 active_more/history_more 标识；counts 来自真实队列与 Telegram 聚合，不是合成指标。messages 的具体结构由 WorkflowView._message 和 Telegram 投影决定，两类消息不能视为同一 DTO。读取失败用 status/error 表明，处理器配置异常返回 500。

#### 消费与字段血缘

[modules/web](dashboard.md#doc-aeec90dfe23cd3) 的 `WorkflowView.vue` 刷新函数 fetch 本接口，列表筛选和选中消息使用消息 id/request_id；队列 batch id 来自 [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)，推送项以 `push:` 前缀区分。正文/实时输出分别通过 `/api/workflow-content?id=...`、`/api/workflow-stream?id=...&after=...` 读取，本页未逐字段建档这些端点。

#### 表、测试与风险

只读 [tables/queue-inbox](inbox.md#doc-6529d9966e604a) / [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a) / [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf) 及结构流转事件。相关本地 tests/dashboard/test_workflow_view.py、test_workflow_content.py、tests/unit/model_stream/test_model_stream_view.py 和 web/scripts/smoke.mjs。改状态/聚合时对照 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)，不要将模型完成投影为微信发送成功。

2026-11-01 的 L1 沉淀没有接入本投影：[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20) 与拆库后新增的 [tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e) 都不进工作流图，[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6) 的六条端点（`/api/knowledge`、`/api/knowledge/facts`、`/api/knowledge/extract`、`/api/knowledge/template` 四条 GET 与两条 POST）是另一页的独立只读/触发/配置端点，本接口的 nodes/messages 结构未变。路由表后插入的知识行都在 `/api/workflow` 之后，本接口仍在 `:39`，处理器与响应字段仍未变。

#### 代码依据

- `src/dashboard/routes.py:39` — `("GET", "/api/workflow", workflow.read)`
- `src/dashboard/api/workflow.py:10` — `def read(ctx):`
- `src/dashboard/workflow_view.py:52` — `def read(self, *, now=None):`
- `web/src/views/WorkflowView.vue:356` — `fetch('/api/workflow',`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。

#### 本次核对

新增知识事实写端点，工作流查询与动作保持原契约。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 小潮日记接入核对

复核共享路由表，工作流读接口、详情和流仍使用原处理器。 来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。
<!-- end-migrated-part: doc-0d1f17e6436714 -->

<a id="doc-bb47c9474691fe"></a>

### 管理台 HTTP 与投影

来源：`llm wiki/wxbot/modules/dashboard.md:1`。

```yaml
type: module
module: dashboard
summary: 聚合运行事实，读取队列不初始化或迁移数据库
coverage: overview
last_verified: '2026-11-06'
sources:
- path: src/dashboard/api/tts_presets.py
  line: 6
  anchor: 'def _known_contact(ctx, contact):'
- path: src/dashboard/routes.py
  line: 60
  anchor: ("GET", "/api/voice-assets", voice_assets.list_assets),
- path: src/dashboard/api/voice_assets.py
  line: 15
  anchor: 'def list_assets(ctx):'
- path: src/dashboard/routes.py
  line: 33
  anchor: ROUTES = (
- path: src/dashboard/queue_view.py
  line: 15
  anchor: 'class QueueView:'
- path: src/dashboard/workflow_view.py
  line: 41
  anchor: 'class WorkflowView:'
- path: src/dashboard/config_view.py
  line: 95
  anchor: 'class ConfigView:'
- path: src/dashboard/config_editor.py
  line: 153
  anchor: def _access_changes(
- path: src/dashboard/api/knowledge.py
  line: 67
  anchor: 'def extract_status(ctx):'
- path: src/dashboard/knowledge_template_view.py
  line: 27
  anchor: 'class KnowledgeTemplateView:'
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-model-access-switch
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-policy-save
- raw/changes/2026-11-05-knowledge-group-sources
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-diary-web
depends_on:
- modules/common
```
### 管理台 HTTP 与投影

联系人表单的 IndexTTS 授权仍复用 /api/skills、/api/contacts 与语音绑定接口；网页预设列表/默认选择现由新增 GET/POST /api/tts-presets 适配 Butler 业务服务。角色与技能仍由 ContactAdmin._policy 的服务端目录验证，UI 勾选不是执行能力；多源保存边界与前端消费者见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。新接口需使用者手动重启管理台加载，无新表或迁移。

#### 范围与入口

`src/dashboard/`：server 组装 HTTP 服务，http 负责传输、鉴权/同源和静态文件；routes.ROUTES 是单张路由表；api 只做胶水，view/action 承担投影与明确动作。

#### 对外接口及消费方

[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714) 被 [modules/web](dashboard.md#doc-aeec90dfe23cd3) 的 WorkflowView 消费；[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f) 被 QueueView 消费。数据库是 [modules/wxbot](wxbot.md#doc-8508032cbe5131) 的队列，视图使用 SQLite `mode=ro`；GET 不允许初始化、迁移或恢复。

[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6) 同属只读投影，但读的是 Butler 侧的 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)（L1 原文）与 [tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)（L2 事实），枚举靠 [tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)。`KnowledgeView` 先读索引库列人；索引库缺失或损坏时退回扫目录，从各库内的 `distinct owner` 反推。每个库都用 `mode=ro` 打开，**不建库不建表**：默认就没有历史，空态不是错误。

同一词条里还有自动提炼两条：`GET /api/knowledge/extract`（`src/dashboard/routes.py:45`）把 Butler 的调度器状态包一层 `available` 转发给页面，Butler 不可达只是 `available: false`；`POST /api/knowledge/extract`（`:67`）只做参数收拢再转给 Butler（`api/support.py:172`），**管理台自己不跑模型、不写库**。两条都受 `BUSINESS_GET` / `BUSINESS_POST` 门禁（`routes.py:18`、`:25`），非本机部署返回 503。

知识模板两条：`GET /api/knowledge/template`（`:46`）只读返回生效模板、覆盖层内容与逐行错误；`POST /api/knowledge/template`（`:68`）交 `KnowledgeTemplateView`（`knowledge_template_view.py:27`）处理 `validate` / `save` / `reset`。写路径不指定路径，固定落在 `data/knowledge/template.md`，复用 `config_lock`、sha256 版本比对、写前备份与原子替换；同样受 `BUSINESS_GET` / `BUSINESS_POST` 门禁，非本机 503。

两个视图都不写库：事实上游是 Butler 的调度器（[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) → [symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)），管理台只负责展示，外加把「立即提炼」转发给 Butler 一次。

#### 边界与缺口

写操作需专用动作头、JSON、明确 acknowledge、可信 Host 和同源；队列写操作和联系人写操作不在本批接口词条范围。身份管理归 [modules/identity](identity-tools.md#doc-5e308350a1ba25)，不是页面自行授予。配置与业务操作细节仍见 README 和实际处理器。

配置投影的 `model_access` 是页面唯一的接入方式来源：`current` 由 `config_schema.access_provider()` 推导（`[model].provider` 优先，否则按 `[agent].provider` 回退），`fields` 与 `notes` 覆盖全部接入方式。保存时 `config_editor._access_changes()` 把接入方式展开成 `[agent].provider` 和 `[model].backend` 再落盘，Codex 用 `op:default` 删掉多余协议字段，因此三个字段不会各行其是。

#### 代码依据

- `src/dashboard/routes.py:28` — `ROUTES = (`
- `src/dashboard/queue_view.py:15` — `class QueueView:`
- `src/dashboard/workflow_view.py:41` — `class WorkflowView:`
- `src/dashboard/config_view.py:95` — `class ConfigView:`
- `src/dashboard/config_editor.py:153` — `def _access_changes(`
- `src/dashboard/api/knowledge.py:54` — `def extract_status(ctx):`
- `src/dashboard/knowledge_template_view.py:27` — `class KnowledgeTemplateView:`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[raw/changes/2026-10-31-model-access-switch](model-backends.md#doc-954a7ea1e7487b)

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)

[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)

#### 音色资产 API

- [apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)：资产 CRUD、参考音预览、会话绑定写 config.wxbot.toml。



#### 联系人语音配置核对

[raw/changes/2026-11-04-contact-index-tts](index-tts.md#doc-cdb6f65d88730c)：新增会话授权控件与原接口消费，源码位置已核对；后端契约保持。


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。


#### 策略保存复核（2026-11-05）

联系人策略保存的事务外目录校验、事务内版本复查及未安装技能的显式取消入口见 [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)。保留原角色与工具权限规则，无数据库迁移，不自动删除已有技能引用。来源 [raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)。

#### 本次核对

知识库事实投影支持跨成员群筛选与只读来源标签，契约见 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)。 来源 [raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)。

#### 本次核对

新增本机同源确认的事实删除转发，由 Butler 持有写权，见 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 小潮日记接入核对

本机管理台新增 [apis/dashboard-resident-diary](resident.md#doc-38ef2f5a72288d)，用 Butler 的配置定位只读日记目录，按页返回已有条目。 来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。
<!-- end-migrated-part: doc-bb47c9474691fe -->

<a id="doc-aeec90dfe23cd3"></a>

### Vue 管理台

来源：`llm wiki/wxbot/modules/web.md:1`。

```yaml
type: module
module: web
summary: 共享导航壳和现有请求封装的管理界面
coverage: overview
last_verified: '2026-11-06'
sources:
- path: web/src/styles/voice-assets.css
  line: 7
  anchor: .workspace main:has(> .voice-assets)
- path: web/src/router.js
  line: 11
  anchor: '{ id: ''voice-assets'', title: ''音色'', group: ''用户与任务'' },'
- path: web/src/views/VoiceAssetsView.vue
  line: 229
  anchor: <section id="pane" class="voice-assets"
- path: web/src/components/ContactDialog.vue
  line: 387
  anchor: 自动回复音色
- path: web/src/router.js
  line: 4
  anchor: 'export '
- path: web/src/api.js
  line: 23
  anchor: 'export '
- path: web/src/views/WorkflowView.vue
  line: 356
  anchor: fetch('/api/workflow',
- path: web/src/views/QueueView.vue
  line: 248
  anchor: apiGet('/api/queue?'
- path: web/src/views/ConfigurationView.vue
  line: 37
  anchor: const backendName =
- path: web/src/views/FactsView.vue
  line: 127
  anchor: async function loadExtract() {
- path: web/src/views/FactsView.vue
  line: 44
  anchor: const kinds = computed(
- path: web/src/views/KnowledgeTemplateView.vue
  line: 43
  anchor: async function load(force = false) {
- path: web/src/views/ConfigurationView.vue
  line: 14
  anchor: '[''contacts'', ''联系人与策略''], [''knowledge'', ''知识库''], [''logging'', ''日志''], [''advanced'', ''高级配置'']'
changes:
- raw/changes/2026-11-03-voice-assets-polish
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-02-web-global-search-clear
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-policy-save
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-05-enable-group-binding
- raw/changes/2026-11-05-knowledge-group-sources
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-diary-web
depends_on:
- modules/dashboard
```
### Vue 管理台

#### 联系人和语音设置

私聊、群聊列表消费 GET /api/contacts 返回的 conversations，缺失窗口由 [modules/identity](identity-tools.md#doc-5e308350a1ba25) 在处理新消息时补建。会话弹窗不再提供独立 IndexTTS 授权和预设入口，技能由 AI 设置保存。会话弹窗仍管理语音发送模式和本地音色资产，保留部分保存的重试和按稳定会话 ID 确定目标的规则。见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)、[raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

群成员和个人群身份页面的「启用」使用 [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc) 的 `binding_enable`，只针对停用的绑定，等待期间禁用按钮并显示进度。来源 [raw/changes/2026-11-05-enable-group-binding](identity-tools.md#doc-6f2fac571f1610)。

#### 范围与依赖

`web/` 是 Vue 3/Vite 管理台；源码 `web/src/`，构建目录 `web/dist/` 由管理台提供 `/app/`。入口/页面注册步骤在根 README。导航由 router.js 和 App.vue 共同登记；请求封装见 api.js。顶栏 `#view-search` 按 tab 保存关键词；有内容时旁显示 `#view-search-clear`（「清空」），只清当前页并回焦；`configuration` / `telegram-relay` 等 `searchHidden` 页两者都不显示。

#### API 消费映射

- FactsView 用事实行编号确认并调用 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6) 的删除动作，显示进度、错误或成功，保留当前筛选刷新。来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

- FactsView 的群筛选消费 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6) 的 `groups`、`group_only` 和 `source_group/source_name`，按群汇总并在表格中标来源。来源 [raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)。

- WorkflowView.vue 的刷新请求消费 [apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)，全文和实时事件分别读 workflow-content / workflow-stream；不是直接调用 Butler handle API。
- QueueView.vue 消费 [apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)；重试/确认已发/丢弃是另外的显式动作，不能把只读投影当成发送成功证据。
- KnowledgeView.vue 消费 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6) 的 `/api/knowledge`；纯只读，不提供删除、编辑、导出。左栏渲染接口返回的 `owners`（会话摘要、原文数、事实数），点人写入 `owner` 筛选；选定的人有多个会话时，标题下出现会话 chips（全部会话 / 私聊 X / 群聊 Y），点击再写 `contact` 与 `channel_type`；换人清空会话筛选。关键词走顶部分类共享的搜索框，防抖 250ms。
- FactsView.vue 消费同一词条的 `/api/knowledge/facts`；六列表格（时间/联系人/类型/事实/原话/置信），`kind` 映射中文、置信度显示百分比，低于 50% 的行降权并在页脚计数。类型表由接口下发：`kinds`（`FactsView.vue:39`）用响应里的 `kinds[{key, label}]` 建映射，后端新增 kind 不需要改前端；`LEGACY_KINDS`（`:11`）只在旧服务缺字段时兜底，`kindOf`（`:210`）优先用接口标签、再查兜底表。会话 chips 同样只写 `contact`，因为事实没有 `channel_type` 列。两页共用 `web/src/styles/knowledge.css`（含 `.session-bar` 一节）。
- FactsView.vue 顶上还有一条自动提炼状态（`FactsView.vue:264`）：`loadExtract()`（`:116`）读 `/api/knowledge/extract`，一句话说清开关、上次写入条数、下次时间或失败原因；`available: false` 时降成 warn 色并隐藏按钮。`runExtract()`（`:126`）把当前左栏选中的人作为 `owner` 发给 `POST /api/knowledge/extract`，触发后 4s 刷状态、15s 连表格一起刷、60s 清掉反馈，不做轮询。

KnowledgeTemplateView.vue 消费 `/api/knowledge/template`：`load()`（`:43`）读生效模板、摘要与逐行错误；`submit()`（`:72`）发 `validate` / `save` / `reset`，请求带 `version` 与确认头；`save()`（`:107`）/ `reset()`（`:113`）各自先确认。没有修改时保存禁用，没有覆盖层时恢复禁用。见 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)。

知识库相关页面都不提供事实的原地编辑：事实的写路径在 Butler（[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) 定时 + 页面转发一次手动触发），管理台只展示与转发；知识模板页只改模板，不读写具体事实。非本机安装模式下 `contacts` / `jobs` / `knowledge` / `facts` / `knowledge-template` / `telegram-relay` 六个标签一起从导航隐藏（`App.vue:47` 的 `hidden` 集合），模板页也不显示全局搜索框（`:67`）。

#### 维护约束

UI 修改按根 AGENTS 的 Hallmark 流程，保留现有设计系统；构建和 smoke 后一起交付 dist。配置管理页现在按模型草稿显示适用字段，保存反馈区分模型热生效和需要重启的字段。见 [modules/models](model-backends.md#doc-69928b2a06b8f9)；其它页面字段契约仍待建档。

配置页的「模型后端」分类只有一个接入方式下拉（`[model].provider`）。选项中文名与说明来自接口的 `model_access`，页面不维护第二份映射表：`model_access.fields` 决定哪些连接字段显示，`model_access.notes` 显示当前接入方式的说明。`butler.agent.provider` 已移入「高级配置」，避免同一件事出现两个下拉；`model.provider` 行不受兼容降级影响，否则选过 Codex 就无法切回。

配置页左栏分类是页面自己的枚举（`ConfigurationView.vue:12`）；「知识库」是本次新增的一类（`:14`，`categoryOf` 在 `:134` 把 `butler.knowledge` 归进去），用来放 `auto_extract` / `extract_batch` 等 11 个字段。字段行本身仍由后端 `ConfigView.read()` 枚举，中文名与说明来自 `config_schema.LABELS`，页面不另存一份。改动这些字段要重启 Butler 才生效（调度器在 `serve()` 里构造）。

#### 代码依据

- `web/src/router.js:4` — `export `
- `web/src/api.js:23` — `export `
- `web/src/views/WorkflowView.vue:356` — `fetch('/api/workflow',`
- `web/src/views/QueueView.vue:248` — `apiGet('/api/queue?'`
- `web/src/views/ConfigurationView.vue:37` — `const backendName =`
- `web/src/views/FactsView.vue:116` — `async function loadExtract() {`
- `web/src/views/FactsView.vue:39` — `const kinds = computed(`（映射来自接口 `kinds`）
- `web/src/views/KnowledgeTemplateView.vue:43` — `async function load(force = false) {`
- `web/src/views/ConfigurationView.vue:14` — `['contacts', '联系人与策略'], ['knowledge', '知识库'], …`

#### 入库来源

[raw/changes/2026-11-02-web-global-search-clear](dashboard.md#doc-5c4b4348a3410a)

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-10-31-model-access-switch](model-backends.md#doc-954a7ea1e7487b)

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)


[raw/changes/2026-11-01-knowledge-sessions](knowledge-vault.md#doc-ba214c308af8ff)

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)

[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)

[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)

#### 音色 Tab 与会话绑定 UI

- 导航「音色」→ VoiceAssetsView（注册/列表/改名/删除/试听参考 WAV）。
- ContactDialog「回复音色」与回复模式同区；文案禁止「训练」「微调」。


#### 音色页展示约束（2026-11-03 核对）

- `web/src/views/VoiceAssetsView.vue:229` 的音色页是单内容区，不含联系人侧栏；`web/src/styles/voice-assets.css:7` 通过限定到 `.voice-assets` 的选择器覆盖共享双栏布局，并兼容 `list-open` / `list-collapsed` 偏好。保持说明、上传表单、资产清单顺序，未修改共享导航。
- 专用样式复用 `theme.css` 中 `--fg2` / `--fg3` / `--line` / `--line-strong` / `--wx`，不再引用未定义的 muted/border/accent。页内 header 取消共享 header 的定位、底色与边框；文件控件与操作保持原生键盘行为。
- `load()` 并行读取 assets/bindings，成功后调用 shell 的 `markRefreshed()`；加载首屏显示静态骨架，读取失败不显示“还没有音色”，表单成功/失败仍由既有服务结果驱动。窄屏保留表格 DOM 与表头，用 `data-label` 展示字段标签。
- 接口不变：`GET /api/voice-assets` 的 `assets[].id/name/created_at/duration_seconds` 与 `limits.max_bytes` 来自 VoiceAdmin.list_assets / VoiceAsset.as_dict；绑定列仍从 `GET /api/voice-bindings` 的 `contact_refs[contact].asset_id` 反查。POST register/rename/delete 的请求体、确认流程及 `X-Wxbot-Voice-Action` 请求头不变；preview 仍只读取参考 WAV。
- 仅 UI 与现有状态投影变更，不涉及数据库、迁移、音色文件内容、配置写入或新异步任务。参考 [raw/changes/2026-11-03-voice-assets-polish](delivery-voice.md#doc-5f445f7abfb4d8)。


#### 联系人语音配置核对

[raw/changes/2026-11-04-contact-index-tts](index-tts.md#doc-cdb6f65d88730c)：新增会话授权控件与原接口消费，源码位置已核对；后端契约保持。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。


#### 策略保存复核（2026-11-05）

联系人策略保存的事务外目录校验、事务内版本复查及未安装技能的显式取消入口见 [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)。保留原角色与工具权限规则，无数据库迁移，不自动删除已有技能引用。来源 [raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)。

#### 小潮日记接入核对

「用户与任务 → 小潮日记」由 ResidentDiaryView 展示，复用工具栏刷新，地址栏保存页码。数据契约见 [apis/dashboard-resident-diary](resident.md#doc-38ef2f5a72288d)。 来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。
<!-- end-migrated-part: doc-aeec90dfe23cd3 -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [管理台全局搜索增加清空按钮](#doc-5c4b4348a3410a) · `llm wiki/wxbot/raw/changes/2026-11-02-web-global-search-clear.md`

<a id="doc-5c4b4348a3410a"></a>

### 管理台全局搜索增加清空按钮

来源：`llm wiki/wxbot/raw/changes/2026-11-02-web-global-search-clear.md:1`。

```yaml
type: change
title: 管理台全局搜索增加清空按钮
pages:
- modules/web
```
### 管理台全局搜索增加清空按钮

#### 目标与背景

管理台顶栏 `#view-search` 按页保存关键词，但有内容时缺少显式清空入口，只能手工删字。WEB-001 要求在搜索框旁增加「清空」，只清当前页搜索词并回焦，配置页/转发页等原本隐藏全局搜索的页面也不显示该按钮。

#### 文件与代码位置

- `web/src/App.vue`：新增 `searchValue` / `clearSearch`；工具栏用 `.global-search` 包裹 `#view-search` 与 `#view-search-clear`（`aria-label="清空搜索"`），随 `searchHidden` 与是否有内容显示。
- `web/src/styles/theme.css`：补充 `.global-search` 行内布局，窄屏不抢占其他工具栏控件。
- `web/scripts/smoke.mjs`：补定时任务/工作流/对话记录的清空交互与跨页保留断言；配置页断言无全局清空按钮。
- `web/dist/`：随本次 `npm run build` 更新。

#### 接口与字段

不涉及后端接口或写请求。搜索仍只写 `provide('logWebCtx').search` 的按 tab 键值。

#### 数据库与迁移

不涉及。

#### 前端消费点

各业务页继续通过注入的 `search[activeTab]` 做原有筛选/加载；清空只把当前 tab 的值置空，不改其他筛选控件状态。

#### 测试与异步任务

`npm.cmd --prefix web run build` 与 `npm.cmd --prefix web run smoke`（假数据）。Hallmark 对改动源码做静态/scope 检查。

#### 风险与回滚

风险低：仅壳层工具栏交互。回滚删除本记录对应提交中的 App.vue / theme.css / smoke / dist 改动即可。
<!-- end-migrated-part: doc-5c4b4348a3410a -->
