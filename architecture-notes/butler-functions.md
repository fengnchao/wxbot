# Butler 功能

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### Butler 功能

图中从 Butler 接出的业务功能，包括定时提醒和聊天记录提炼。

## 使用说明

- [wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / delivery/ —— 投递](#doc-81e20b159a9237) · `README.md`
- [wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / runtime/ —— 运行支撑](#doc-500bcb6cafa01f) · `README.md`
- [wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / channels/telegram/ —— 外部通道](#doc-d1c54564902dd5) · `README.md`
- [wxbot / Butler / Telegram 通道](#doc-e225117d9b77d4) · `README.md`

<a id="doc-81e20b159a9237"></a>

### wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / delivery/ —— 投递

来源：`README.md:205`。

###### delivery/ —— 投递

| 文件 | 职责 |
|---|---|
| `delivery/push.py` | Butler → wxbot 外发：把主动推送交给 8765 代发 |
| `delivery/push_client.py` | 按既有 Butler 契约提交新闻；结果未知绝不重试 |
| `delivery/pending.py` | 补发队列：先标记认领再拼装，一条只吐一次 |
| `delivery/media.py` | Butler 持有的图片字节；调用方只能引用服务端签发的不透明 ID |
| `delivery/gradio_tts.py` | 复用本机 IndexTTS WebUI，同会话队列、动态预设和网页默认参数 |
| `delivery/tts.py` | 授权语音生成、operations 幂等和按身份分区的 WAV 存储 |
| `delivery/tts_presets.py` | 网页预设列表与当前会话默认音色，原子保存和版本冲突检查 |
| `delivery/message_forwarding.py` | 校验后的单向 HTTP 消息投递（按联系人） |
| `delivery/reminders.py` | Butler 自己的提醒调度，不依赖模型是否可用 |
<!-- end-migrated-part: doc-81e20b159a9237 -->

<a id="doc-500bcb6cafa01f"></a>

### wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / runtime/ —— 运行支撑

来源：`README.md:219`。

###### runtime/ —— 运行支撑

| 文件 | 职责 |
|---|---|
| `runtime/concurrency.py` | 进程内锁：稳定会话与共享 profile 文件 |
| `runtime/flowlog.py` | 管家流水日志：把每轮「收到／回复／调用失败」写成看板能解析的格式 |
| `runtime/heartbeat.py` | 进程内随机心跳：向 Hermes 要一条建议，再私聊给本人 |
| `runtime/job_admin.py` | 运维删除提醒；只在服务 token 校验通过后调用 |
| `runtime/mcp_gateway.py` | 需要鉴权的无状态 Streamable HTTP MCP（JSON 响应，不开 SSE 会话） |
| `runtime/setup.py` | 可移植初始化与只读环境自检 |
| `runtime/install_wizard.py` | 交互式首次安装；不调模型、不复制登录、不启动服务 |
| `runtime/migration.py` | 旧本地目录字段的显式、可重入导入 |
| `runtime/upgrade.py` | 显式本地升级，保留连接与认证 |
| `runtime/model_switch.py` | 请求固定模型代际，后续请求重载模型参数，旧后端在在途完成后关闭 |
| `runtime/model_migration.py` | 旧 direct 安装显式改为 wxbot → Butler，保留本机私有配置备份 |
| `runtime/plugin.py` | 可移植插件包与应用之间的版本化契约 |
| `runtime/knowledge_template.py` | 知识图谱模板：目录、分类、索引分区与提炼规则来自一份 Markdown；覆盖层优先于插件内置 |
| `runtime/knowledge_store.py` | 知识图谱存储：一人一个 Obsidian vault，节点是 Markdown，关联靠 `[[双链]]` |
| `runtime/knowledge_extract.py` | 用模型把原文提炼成节点事实；独立会话作用域，不占用聊天上下文 |
| `runtime/knowledge_auto.py` | 自动提炼的单线程调度：空闲窗口、批量上限、指数退避与进程内单飞 |
<!-- end-migrated-part: doc-500bcb6cafa01f -->

<a id="doc-d1c54564902dd5"></a>

### wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / channels/telegram/ —— 外部通道

来源：`README.md:240`。

###### channels/telegram/ —— 外部通道

| 文件 | 职责 |
|---|---|
| `channels/telegram/__main__.py` | 本地 Telegram 登录、只收不回的转发、只读状态 |
| `channels/telegram/client.py` | 小号只接收 Telethon 适配器；导入这个模块不会登录 |
| `channels/telegram/config.py` | 严格、无副作用的配置；凭据不会出现在 repr |
| `channels/telegram/formatting.py` | 纯文本转发消息，不调模型、不下媒体 |
| `channels/telegram/service.py` | 独立的接收与转发循环；wxbot 仍是 UI 拥有者 |
| `channels/telegram/store.py` | 持久化接收游标与保守的逐收件人回执 |

| bot/ 文件 | 职责 |
|---|---|
| `bot/__main__.py` | `python -m butler.channels.telegram.bot init\|run\|status\|retry-media` |
| `bot/config.py` | 机器人凭据与个人 Telegram API 凭据分开保存 |
| `bot/inbox.py` | Butler 自己的、已鉴权入库存储；确认即提交 |
| `bot/queue.py` | 一次事务持久化 update 与轮询游标 |
| `bot/service.py` | 长轮询 + 独立、幂等地投给 Butler |
| `bot/media.py` | Bot API 图片下载 + 带鉴权的 Butler 登记（在 UI 之外） |
| `bot/news.py` | 把已保存的 bot 消息转成新闻投递 |
| `bot/cleanup.py` | 删除失败的 Telegram 工作，不创建也不迁移队列 |

| relay/ 文件 | 职责 |
|---|---|
| `relay/settings.py` | 校验过、带版本的转发设置；配置里不含凭据 |
| `relay/store.py` | 持久化桌面观察与逐频道转发任务；不碰原生 UI |
<!-- end-migrated-part: doc-d1c54564902dd5 -->

<a id="doc-e225117d9b77d4"></a>

### wxbot / Butler / Telegram 通道

来源：`README.md:757`。

#### Telegram 通道

三个互相独立的入口，都不启动其它服务：

| 入口 | 用途 |
|---|---|
| `python -m butler.channels.telegram` | 本地 Telethon 登录，收指定频道文字，按配置转发到微信分组（只收不回） |
| `python -m butler.channels.telegram.bot` | Bot API 长轮询入库，可把消息转成新闻投递；`init\|run\|status\|retry-media` |
| `python -m butler.news [--preview]` | 汇总 RSS 生成日报，经 Butler 推送接口投递 |

转发配置在管理台「Telegram 转发」页维护；`relay/settings.py` 是带版本的设置，
`relay/store.py` 存持久化观察与逐频道任务。Telegram Desktop 的界面状态机只在 wxbot 的 UI 线程跑。
<!-- end-migrated-part: doc-e225117d9b77d4 -->

## 技术资料

- [Butler 投递业务](#doc-f61f55fe09c5e9) · `llm wiki/wxbot/modules/delivery.md`
- [Butler 运行支撑](#doc-241e7c8bdd1c05) · `llm wiki/wxbot/modules/runtime.md`
- [Telegram 外部通道](#doc-8b0e2206d40805) · `llm wiki/wxbot/modules/telegram.md`

<a id="doc-f61f55fe09c5e9"></a>

### Butler 投递业务

来源：`llm wiki/wxbot/modules/delivery.md:1`。

```yaml
type: module
module: delivery
summary: 主动推送、补发、媒体与提醒归业务服务所有
coverage: overview
last_verified: '2026-11-05'
sources:
- path: src/butler/delivery/tts_presets.py
  line: 12
  anchor: 'class PresetBindings:'
- path: src/butler/delivery/push.py
  line: 19
  anchor: def push_to_wxbot(
- path: src/butler/delivery/reminders.py
  line: 5
  anchor: 'class ReminderScheduler:'
- path: src/butler/delivery/automatic_tts.py
  line: 33
  anchor: 'class AutomaticReplyTts:'
changes:
- raw/changes/2026-11-03-feat-voice-001-virtual-mic
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-group-auto-voice
```
### Butler 投递业务

#### 范围与边界

`src/butler/delivery/` 负责主动推送、补发、媒体和提醒。push_to_wxbot 将主动推送交给 wxbot 外发 HTTP 服务；最终 UI 发件由 [modules/wxbot](wxbot.md#doc-8508032cbe5131) 拥有，Butler 不操作窗口。

#### 关系与缺口

`tts_presets.PresetBindings` 将网页动态列表和会话默认选择连接到生成服务，配置保存在 Butler data_dir 中并以内容修订保护原子修改。显式音色优先；省略音色仅可使用当前会话默认。管理台适配与状态、幂等默认快照见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，不会把本地自动回复资产当作网页预设列表。

网页预设语音由 `gradio_tts.GradioTtsClient` 复用已加载的本机模型，`tts.TTSService` 在事务外生成、最后复核能力，`AudioStore` 按身份散列分区保存标准 WAV；只向 wxbot 提交媒体编号。`queue_voice_to_wxbot` 等待持久化入队，不等待全部播放，协议见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)；该路径不使用新闻订阅授权。

属于 [modules/butler](butler.md#doc-38393df7a7b4da)；消息处理先认领补发再调用模型，见 [symbols/butler-handle](butler.md#doc-eba67ca6f97d80)。wxbot 出站持久化见 [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)。主动推送/媒体端点、提醒业务表和调度字段仍待完整建档；本概览不代表这些接口已完成契约巡检。

#### 代码依据

- `src/butler/delivery/push.py:19` — `def push_to_wxbot(`
- `src/butler/delivery/reminders.py:5` — `class ReminderScheduler:`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

#### 变更

- 2026-11-03: FEAT-VOICE-001 P1 outbox kind=voice（虚拟麦+RALT）；见 [raw/changes/2026-11-03-feat-voice-001-virtual-mic](delivery-voice.md#doc-3b7c8dcbc01ec2)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。


#### 群聊采集与自动语音复核（2026-11-05）

自动回复的 webui 默认推导、实时语音策略、流式缓冲、daemon 合成及录音前准确预设复核见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)；旧媒体包/离线提供者合同保留。自动 webui 的录音前失败终结并仅回退一次文字，不让 blocked 重试重复投递，无数据库迁移。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。
<!-- end-migrated-part: doc-f61f55fe09c5e9 -->

<a id="doc-241e7c8bdd1c05"></a>

### Butler 运行支撑

来源：`llm wiki/wxbot/modules/runtime.md:1`。

```yaml
type: module
module: runtime
summary: 安装、迁移、并发、MCP 与知识库提炼调度等运行基础设施
coverage: overview
last_verified: '2026-11-05'
sources:
- path: src/butler/runtime/setup.py
  line: 28
  anchor: def initialize(
- path: src/butler/runtime/setup.py
  line: 34
  anchor: def doctor(
- path: src/butler/runtime/mcp_gateway.py
  line: 5
  anchor: 'def '
- path: src/butler/runtime/model_migration.py
  line: 13
  anchor: def migrate_model_connection(
- path: src/butler/runtime/knowledge_auto.py
  line: 71
  anchor: 'class ExtractScheduler:'
- path: src/butler/runtime/knowledge_template.py
  line: 83
  anchor: 'class GraphTemplate:'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-05-resident-xiaochao
```
### Butler 运行支撑

#### 范围和入口

`src/butler/runtime/` 承载安装、迁移、并发、MCP、心跳与插件验证。initialize 复用初始化实现；doctor 是环境自检入口。命令行来自 `butler/__main__.py`，详细操作见 README。

#### 关系与约束

属于 [modules/butler](butler.md#doc-38393df7a7b4da)；运行时读取 [modules/plugin](resident-skills.md#doc-709338d3e083eb) 的插件契约。必须使用安装者本人的登录，不能复制其他安装的认证/数据；服务由用户启动和重启。MCP 权限见 [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。

#### 覆盖缺口

配置字段/迁移兼容和全部 MCP method 尚未逐项建档。

#### 知识库与提炼

`knowledge_store.py` 定义一人一库的读写入口：[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)（索引）、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)（L1 原文）、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)（L2 事实），并提供 `migrate_legacy` 拆分旧单库。`knowledge_extract.py` 是提炼链路 [symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)。

`knowledge_template.py` 是骨架与口径来源 [symbols/knowledge-template](knowledge-vault.md#doc-4656beba355895)：`GraphTemplate`（`:83`）决定节点目录、事实分类、索引分区和提炼规则；`KnowledgeStore` 构造时读覆盖层 `data/knowledge/template.md`，没有则用插件内置模板，再没有才回退代码默认值。模板只影响新写入与下一轮拼 prompt，不迁移历史 vault。

`knowledge_auto.py` 是常驻调度器 [symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)（`ExtractScheduler`，`:71`）：`serve()` 构造后随 serving 启停（`src/butler/server.py:477`、`:488`、`:496`），按间隔挑有积压的人喂模型，并把 prune 并入同一轮。`knowledge.enabled` 或 `knowledge.auto_extract` 为假时 `start()` 只记一条日志、不起线程。人工入口（`python -m butler knowledge-extract`、`knowledge-prune`、`knowledge-migrate`）仍在，但不再是唯一入口；CLI 提炼前要先拿同一把锁（`src/butler/__main__.py:74`）。

#### 代码依据

- `src/butler/runtime/setup.py:28` — `def initialize(`
- `src/butler/runtime/setup.py:34` — `def doctor(`
- `src/butler/runtime/mcp_gateway.py:5` — `def `
- `src/butler/runtime/model_migration.py:13` — `def migrate_model_connection(`
- `src/butler/runtime/knowledge_auto.py:71` — `class ExtractScheduler:`
- `src/butler/runtime/knowledge_template.py:83` — `class GraphTemplate:`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

#### 模型运行支撑

[symbols/reloadable-backend](model-backends.md#doc-85aba8d0cc88bd) 固定请求代际；model_migration.py 将旧 direct 配置显式迁移为 wxbot→Butler，保留本机私有备份且不启动服务。见 [modules/models](model-backends.md#doc-69928b2a06b8f9)。


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)

[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)

#### 常驻角色接入核对

小潮的调度、空闲与浏览状态由 [symbols/resident-role](resident.md#doc-81303bd5af31f1) 管理，服务退出时结束独立活动。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。
<!-- end-migrated-part: doc-241e7c8bdd1c05 -->

<a id="doc-8b0e2206d40805"></a>

### Telegram 外部通道

来源：`llm wiki/wxbot/modules/telegram.md:1`。

```yaml
type: module
module: telegram
summary: Telethon、Bot API 和桌面中继三个不同边界
coverage: overview
last_verified: '2026-11-01'
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
- raw/changes/2026-11-01-mention-fallback-unread-retry
```
### Telegram 外部通道

#### 范围

Butler 的 `channels/telegram/` 包括 Telethon 接收、bot/ 入库和 relay/ 配置/持久任务；桌面自动化仅在 wxbot 的 telegram_desktop 中执行。三者不能混为一个队列或共享认证。

#### 关系与缺口

通道属于 [modules/butler](butler.md#doc-38393df7a7b4da)，桌面 UI 属于 [modules/wxbot](wxbot.md#doc-8508032cbe5131)；聚合展示由 [modules/dashboard](dashboard.md#doc-bb47c9474691fe) 承担。完整队列表、消息去重和媒体重试协议尚待建档。禁止为图谱收集真实频道消息或 session 文件。

桌面中继清理搜索框只能用 uiautomation 声明的 `{Back}`；`{Backspace}` 不在键表里，会被交给 Unicode 输入并抛 TypeError，使搜索框保留上一次查询词。同一次的键名错误也出现在微信侧，见 [symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7)。

#### 代码依据

- `src/butler/channels/telegram/bot/queue.py:9` — `class Queue:`
- `src/butler/channels/telegram/relay/store.py:12` — `def `
- `src/wxbot/telegram_desktop.py:41` — `class `

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)
<!-- end-migrated-part: doc-8b0e2206d40805 -->
