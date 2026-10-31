# wxbot / Butler

Windows 上的个人微信机器人：wxbot 负责微信窗口收发与持久队列，Butler 负责用户身份、权限、
记忆、提醒、心跳和消息接口，管理台负责展示与配置；模型可以是本机 Codex，也可以是已有的
智能体或 OpenAI 兼容 API。

| 进程 | 入口 | 端口 | 职责 |
|---|---|---|---|
| wxbot | `python -m wxbot.main` | 8765（外发 HTTP） | 微信主窗口监听、群聊 @ 判定、收发队列、分批输入与发送 |
| Butler | `python -m butler.server --config config.butler.toml` | 8770 | 用户、权限、记忆、提醒、心跳、消息接口、插件 MCP |
| 管理台 | `python -m dashboard.server` | 8788 | 只读运行事实 + 写配置文件；页面在 `/app/` |

`python -m butler start` 按 `config.wxbot.toml` 的 `[installation].mode` 一次性拉起：
`local` 启动三个进程，`external` 只启动管理台与 wxbot。旧 `direct` 模式先显式迁移。端口被占用时保留已有进程，
绝不自动重启。

## 安装

要求 Windows、Python 3.14+、Git 和已登录的微信；选本机 Codex 时用安装者自己的账户。
插件与项目是同一个仓库。

```powershell
codex plugin marketplace add <仓库地址>
codex plugin add butler-wechat@butler-wechat-plugins
git clone <仓库地址> butler-wxbot
cd butler-wxbot
.\scripts\setup.ps1
.\.venv\Scripts\python.exe -m butler doctor
```

`setup.ps1` 优先用 uv 同步依赖，没有 uv 时回退 `pip install -e . --no-deps`，
然后进入交互向导 `python -m butler setup`：收集接入方式、机器人昵称、服务地址／端口和凭据，
显示脱敏摘要后写入本机配置。取消不留半成品，已有配置保留。

| 向导选择 | 模式 | 说明 |
|---|---|---|
| Codex | local | 可填 API Key，或 `python -m butler login` 登录本人账户（登录存在机器人自己的目录） |
| 已有 Butler | external | 填现有 Butler 地址和 Token，本机不跑 Butler |
| Hermes | local | Butler 调用已运行的兼容 API，填地址、模型与凭据 |
| OpenClaw | local | Butler 调用网关 HTTP 对话端点，填地址、凭据和 agent |
| Cursor | local | Butler 调用本人已授权的无头 CLI；专属目录、只读 `--mode ask` 与沙箱 |
| DeepSeek | local | Butler 通过兼容 API 调用，填凭据和实际模型名 |
| 自定义 API | local | Butler 调用 Chat Completions 或 Responses，填地址、模型和凭据 |

`local/external` 写进 `config.wxbot.toml` 的 `[installation].mode`，wxbot 的 `[model].backend` 固定为 `butler`。
本机模型选择在 `config.butler.toml` 的 `[agent].provider`，Codex 参数在 `[codex]`，其它后端参数在 `[model]`。
兼容老 Hermes 配置的 `[hermes]`。非 Codex 接入不要求本机 Codex 登录。
统一链路是 **wxbot → Butler → 所选模型/智能体**；联系人、身份、记忆和提醒由 Butler 持有，模型切换不迁移这些业务数据。
其它智能体使用已有的兼容协议接入，不假设任意 CLI 都支持 Cursor 协议。
外部 Butler 能力由远端管理，本机管理台会关闭对应的远端账户／记忆／心跳入口。
向导只写配置，不验证真实模型连接，也不启动服务。

在管理台「配置管理 → 模型后端」切换 provider，页面按草稿选择显示地址、模型名、密钥或 Cursor 目录等适用字段。
保存模型设置后由后续请求使用；在途请求继续使用原后端，切换不会重放请求。运行监听、认证和数据目录仍需由使用者自行重启加载。
旧版 Hermes（没有 `[model]`）启动方式首次换模型需要手动重启 Butler；进入本地模型运行方式后适用热切换。加载本次新版代码也需使用者自行重启 Butler、管理台和 wxbot，前端刷新页面加载新 dist。
各后端保留各自会话范围，切换不承诺移植远端推理会话；支持的工具能力取决于实际后端协议，API Key 不是 Butler 工具授权。

旧 direct 安装先由使用者停掉本机服务，再执行 `python -m butler migrate --directory <安装目录>`。
迁移会把本安装的模型参数移到 Butler、将 wxbot 指向本机 Butler，并保留原配置的 `.model-backup-*` 备份。
备份同样含密钥，只留本机；不会自动启动服务或验证真实连接。

## 运行

```powershell
.\.venv\Scripts\python.exe -m butler start
```

也可以按模式分别启动：

```powershell
.\.venv\Scripts\python.exe -m butler.server --config config.butler.toml   # 8770
.\.venv\Scripts\python.exe -m dashboard.server                           # 8788，页面在 /app/
.\.venv\Scripts\python.exe -m wxbot.main                                 # 8765
```

`python -m butler <命令>` 的全部子命令：

| 命令 | 作用 |
|---|---|
| `init` | 非交互、幂等的本机初始化（可用 `--directory`） |
| `setup` | 交互安装向导 |
| `doctor` | 只读自检：端口、依赖、插件协议、微信窗口／控件（`--no-wechat` 跳过微信） |
| `login` | 仅 local + Codex 模式，登录本人 Codex 账户 |
| `serve` | 只跑 Butler 服务（local 模式） |
| `start` | 按模式拉起进程组，Ctrl+C 只结束本次启动的子进程 |
| `migrate` | 旧目录升级、路径整理、过期编辑锁清理 |
| `contacts-preview` | 只读预览统一联系人迁移结果 |
| `contacts-migrate` | 显式切换统一联系人，需 `--acknowledge-stopped` |

服务一律由使用者手动启动与重启，不要去停止或重启别人的进程。
统一联系人迁移、备份和回退步骤见 `python -m butler contacts-preview --help` 与
`contact_migration` 的输出报告；迁移前必须自行停掉 Butler、管理台、wxbot，
以及旧心跳、提醒、看门狗等所有可能写入联系人数据的程序。

## 目录

```
src/butler/     编排层：agent/ identity/ delivery/ runtime/ channels/telegram/ news/ backends/
src/wxbot/      UI 收发层：主窗口监听、收件箱、队列、发件、后端适配、wechat/ 控件层
src/dashboard/  管理台 HTTP 服务：server/http/routes/api + 各 *_view / *_action
src/common/     跨包共用：仓库根、配置锁、流转事件、模型观察、图文 schema、新闻配置
web/            Vue 3 + Vite 管理台源码，构建产物 web/dist 由管理台在 /app/ 提供
scripts/        启动与运维脚本（栈启停、投递、提醒、安装）
tools/          本机调试与打包（用法见 tools/README.md）
plugins/butler-wechat/  Codex 插件：安装引导、角色、功能 Skill、MCP 连接
tests/          离线回归测试（仅本地，不入库）：support/ unit/ butler/ dashboard/ integration/
llm wiki/wxbot/  Obsidian 知识图谱：模块/接口/表/符号、影响报告、追加修改记录与本地检查
data/           本机认证和运行数据，禁止提交 Git
config.*.toml   本机配置（默认路径硬编码在 src/butler/config.py，不要改名）
```

包都在 `src/` 下，靠 `pyproject.toml` 的可编辑安装导入：`python -m butler`、
`python -m dashboard.server`、`python -m wxbot.main` 在仓库外也能跑。
仓库根统一从 `common.paths.REPO_ROOT` 取，不要再写 `Path(__file__).resolve().parents[N]`。

## 模块与文件职责

以下按目录列出每个模块的职责。`__init__.py` 只做包说明，不再单列。

### src/butler —— 编排层

#### 根目录（高频导入，留在根）

| 文件 | 职责 |
|---|---|
| `butler/__main__.py` | `python -m butler` 命令行入口：init/setup/migrate/contacts-*/doctor/login/serve/start |
| `butler/config.py` | 配置：一个 TOML 读进来，其余模块只认 `Config` 对象；默认配置路径硬编码在这里 |
| `butler/defaults.py` | 不含凭据的安装默认值，每次调用返回独立对象 |
| `butler/runtime_config.py` | 把结构化覆盖编码成 TOML，不做 shell 插值 |
| `butler/business.py` | 与模型后端无关的业务状态；一个事务一条连接 |
| `butler/server.py` | Butler HTTP 接口（stdlib，无第三方依赖）：鉴权、路由、状态码 |

#### agent/ —— 决策与执行

| 文件 | 职责 |
|---|---|
| `agent/core.py` | 主流程：认领补发 → 调模型 → 解析行动 → 组装回复 → 出站推送 |
| `agent/router.py` | 决策前半：进入模型之前的规则，和出来之后的行动标记解析 |
| `agent/skills.py` | 决策后半：模型能调哪些 skill 的白名单与执行器；`HERMES_HINT` 是行动协议提示 |
| `agent/hermes.py` | Hermes 客户端：管家与 Hermes（模型 + skill 运行时）之间唯一的一层 |
| `agent/hermes_stream.py` | 读 Hermes 进度事件，同时缓存一份完整回复交给 wxbot |
| `agent/reply.py` | 把最终回复切成句：不切断 URL、代码块和受保护的 token |
| `agent/skill_policy.py` | 可按联系人热加载的角色／skill／心跳策略 |
| `agent/catalogue.py` | 可移植、纯数据的 skill 目录；skill 不能自己选择权限 |
| `agent/tools.py` | 服务端签发的身份能力与唯一的业务工具边界 |

#### identity/ —— 联系人身份

| 文件 | 职责 |
|---|---|
| `identity/contacts.py` | 联系人映射：微信聊天窗口标题 → Hermes Profile / uid / 会话键 |
| `identity/contact_store.py` | 权威的本地会话与联系人设置，归 Butler 所有 |
| `identity/contact_identity.py` | 事务内的「同一个人」匹配，成员关系证据留在绑定上 |
| `identity/contact_admin.py` | 面向业务的统一联系人管理；路径只从服务端配置来 |
| `identity/contact_migration.py` | 从旧联系人来源到单一业务库的显式离线切换（预览 + 迁移） |
| `identity/user_registry.py` | 管理员持有的身份与记忆范围；头像哈希是证据不是 ID |
| `identity/user_api.py` | 带类型的运维操作，调用方必须先通过服务 token |
| `identity/directory.py` | Butler 自己的本地通道目录；不授予身份或工具权限 |
| `identity/groups.py` | 用户分组（订阅字典）：`messageType` → 绑定的联系人 |
| `identity/group_context.py` | 公开群观察、有界的请求快照和按线程的游标 |

#### delivery/ —— 投递

| 文件 | 职责 |
|---|---|
| `delivery/push.py` | Butler → wxbot 外发：把主动推送交给 8765 代发 |
| `delivery/push_client.py` | 按既有 Butler 契约提交新闻；结果未知绝不重试 |
| `delivery/pending.py` | 补发队列：先标记认领再拼装，一条只吐一次 |
| `delivery/media.py` | Butler 持有的图片字节；调用方只能引用服务端签发的不透明 ID |
| `delivery/message_forwarding.py` | 校验后的单向 HTTP 消息投递（按联系人） |
| `delivery/reminders.py` | Butler 自己的提醒调度，不依赖模型是否可用 |

#### runtime/ —— 运行支撑

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

#### channels/telegram/ —— 外部通道

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

#### news/ 与 backends/

| 文件 | 职责 |
|---|---|
| `news/__main__.py` | `python -m butler.news [--preview]`，不启动任何服务 |
| `news/collector.py` | 有界 RSS 抓取、确定性挑选、标注来源的摘要 |
| `news/delivery.py` | 日报持久化与逐收件人／分段回执 |
| `backends/codex.py` | 隔离的、有界的官方 SDK worker；绝不返回未完成的模型输出 |
| `backends/codex_runtime.py` | 给 SDK 的阻塞启动和模型流都加时限 |
| `backends/compatible.py` | 通用模型会话隔离、完整结果和 HTTP/CLI 传输适配 |
| `backends/models.py` | OpenAI/Responses 原生函数工具循环，权限由 Butler 服务签发 |

### src/common —— 跨包共用

不含微信 UI，也不依赖 Butler 业务。

| 文件 | 职责 |
|---|---|
| `common/paths.py` | `REPO_ROOT`：从 `pyproject.toml` 向上定位，可用 `WXBOT_ROOT` 覆盖 |
| `common/config_lock.py` | 配置写入的跨进程锁（管理台与 Butler 共用） |
| `common/flow_trace.py` | 只追加、不含消息正文的流转事件与字段白名单 |
| `common/media_bundle.py` | 两个服务之间严格、精简的图文 wire schema |
| `common/model_stream.py` | 公开、有界的模型观察，作用域是单个同步请求 |
| `common/avatar_identity.py` | 共享的带版本头像归一化；不访问桌面与剪贴板 |
| `common/news_config.py` | 管理台与日报共用的新闻目录与设置 |

### src/dashboard —— 管理台

#### 组装与传输

| 文件 | 职责 |
|---|---|
| `dashboard/server.py` | 进程入口（组装层）：`build_server()` + `main()` |
| `dashboard/http.py` | HTTP 传输层：请求解析、鉴权、静态文件、`/app/assets/` 路径校验、异常包装 |
| `dashboard/routes.py` | 单张路由表：方法 + 路径 → api 处理器 |
| `dashboard/services.py` | 服务函数的延迟绑定 |
| `dashboard/settings.py` | 持久化 log 设置；命令行参数与环境变量仍然优先 |

#### api/ —— 只做 HTTP 胶水

统一形态：解析参数 → 调 view／数据源 → 返回 `(status, body)`。

| 文件 | 职责 |
|---|---|
| `api/config.py` | 配置总览与保存：wxbot／Butler 配置、新闻分组设置 |
| `api/contacts.py` | 联系人档案：读取、记忆与审计流水、保存（需本机页面确认） |
| `api/users.py` | Butler 用户目录代理；凭证只留服务端，浏览器只看脱敏结果 |
| `api/groups.py` | 用户分组字典：读取与 bind／unbind |
| `api/heartbeat.py` | 角色心跳：策略读写、执行状态、技能目录、立即触发 |
| `api/jobs.py` | 定时任务：按归属分组的总览 + 显式确认后的删除 |
| `api/queue.py` | 收发队列：只读总览 + 显式确认后的重试／确认已发／丢弃 |
| `api/workflow.py` | 消息工作流：总览、单条全文、模型实时输出、记录删除 |
| `api/flow.py` | 消息流转与 wxbot 通道流水（只读日志／库） |
| `api/runtime.py` | Butler 运行时状态（经 loopback 代理，凭证不出服务端） |
| `api/relay.py` | Telegram 转发：只读写本机配置，核对动作走 Butler |
| `api/support.py` | Butler 配置、联系人、技能目录与心跳策略的读写（非 HTTP 层） |
| `api/system.py` | 连接方式与进程自查 |

#### 视图、数据源与动作

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
| `dashboard/job_admin.py` | 管理台 → Butler 的提醒删除代理 |
| `dashboard/telegram_view.py` | 只读 Telegram 入库／新闻投影；绝不迁移或恢复数据库 |
| `dashboard/telegram_relay_admin.py` | 本机转发配置编辑；不做生命周期或投递操作 |

### src/wxbot —— 微信 UI 收发层

#### 根目录

| 文件 | 职责 |
|---|---|
| `wxbot/main.py` | 启动收发服务：默认监听微信主窗口，兼容按绑定列表轮询独立聊天窗口 |
| `wxbot/config.py` | 读 `config.wxbot.toml`，其他模块只从这里取配置 |
| `wxbot/dpi.py` | 开启 DPI 感知，保证控件坐标与截图坐标一致；必须最先调用 |
| `wxbot/log.py` | 统一日志格式，并压低 comtypes/uiautomation 的 COM 缓存噪音 |
| `wxbot/state.py` | 新消息检测：对比上一次和这一次读到的列表，找出末尾新增部分 |
| `wxbot/inbox.py` | 主窗口持续收件；模型与发件通过 SQLite 队列和 UI 主线程衔接 |
| `wxbot/outbound.py` | 外发 HTTP 服务（8765）：接收主动推送，交给主循环线程代发 |
| `wxbot/queue_store.py` | SQLite 收件箱、合并批次、发件箱；事务短小，模型／UI 操作不持数据库锁 |
| `wxbot/queue_schema.py` | 队列建表与原子式旧库迁移；不访问服务与 UI |
| `wxbot/queue_worker.py` | 有界模型请求线程：只接触普通消息数据，绝不操作微信 UI |
| `wxbot/queue_admin.py` | 队列查看与异常恢复 CLI：`python -m wxbot.queue_admin --help` |
| `wxbot/queue_cleanup.py` | 带备份地删除未成功的队列记录；不访问 UI |
| `wxbot/queue_history.py` | 关闭已完成的工作流记录，不改投递与回执 |
| `wxbot/delivery.py` | UI 发件执行器：逐步输入、核对新增自己的气泡，保存确定／不确定结果 |
| `wxbot/delivery_policy.py` | 事务化的回复生命周期；无 UI、网络与启动副作用 |
| `wxbot/reply.py` | 与后端无关的完整回复对象，可安全跨线程传递 |
| `wxbot/streaming.py` | 增量最终答复的句子边界，不切开受保护的 token |
| `wxbot/stream_queue.py` | 仅运行期的辅助流存储，不参与旧库迁移 |
| `wxbot/model_recovery.py` | 只读的模型失败策略，运行期与看板投影共用 |
| `wxbot/relay_authorization.py` | 短时中继权限快照；UI 调用方不自己做 HTTP |
| `wxbot/telegram_desktop.py` | Telegram Desktop 状态机，只在 wxbot 的 UI 线程里跑 |

#### wechat/ —— 控件层

| 文件 | 职责 |
|---|---|
| `wechat/main_window.py` | 微信主窗口：功能栏、会话列表、右侧当前聊天面板 |
| `wechat/chat_window.py` | 一个绑定联系人或群聊的独立聊天窗口：读消息、发消息（适配微信 4.x mmui） |
| `wechat/locator.py` | 按配置条件查找控件，条件来自 `config.wxbot.toml` 的 `[wechat.*]` |
| `wechat/typing.py` | UI 线程分批粘贴；`step` 每次最多输入一批，不 sleep 等下一批 |
| `wechat/clipboard.py` | 短时剪贴板租约，保证粘贴可校验；保留原剪贴板全部格式 |
| `wechat/mentions.py` | UI 线程的 @ 选择器，带校验过的纯文本回退 |
| `wechat/emoji.py` | 微信表情面板：打开面板，随机点一张表情／贴图发送 |
| `wechat/image.py` | 有界、仅 UI 线程的图片粘贴／预览／发送事务 |

#### processor/ —— 消息处理器

| 文件 | 职责 |
|---|---|
| `processor/base.py` | 处理器接口：收到一条消息返回要回复的文字（`None` 表示不回） |
| `processor/router.py` | 命令路由：`/` 开头的走命令，其余交给模型；新命令在 `COMMANDS` 里加一项 |
| `processor/butler.py` | Butler 处理器：把消息转给本地 Butler（`POST /v1/handle`） |
| `processor/openai_compat.py` | 非流式、只接受完整结果的 OpenAI 兼容对话传输 |
| `processor/responses.py` | OpenAI Responses JSON 协议，严格校验终止状态 |
| `processor/cursor.py` | Cursor 无头适配器；聊天输入始终是数据，不当命令行选项 |
| `processor/ollama.py` | 本机 Ollama 处理器，按联系人保存在内存里的上下文 |

### web/ —— 管理台前端

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
| `src/views/ContactsView.vue` | 联系人：监听、群昵称、角色／心跳、订阅与记忆 |
| `src/views/JobsView.vue` | 定时任务：按归属分组，支持逐条删除 |
| `src/views/ConfigurationView.vue` | 配置管理：分类、搜索、草稿、保存与版本冲突提示 |
| `src/views/TelegramRelayView.vue` | Telegram 转发设置与核对 |
| `src/components/WorkflowNode.vue` | 工作流节点卡片 |
| `src/components/WorkflowTrace.vue` | 单条消息的流转详情与阶段耗时 |
| `src/components/WorkflowWires.vue` | 服务之间的动态连线 |
| `src/components/ConfigField.vue` | 单个配置项的输入控件 |
| `src/components/StructuredEditor.vue` | 复杂结构的 JSON 编辑器 |
| `src/components/ContactDialog.vue` | 联系人详情弹窗 |
| `src/components/ContactMergeDialog.vue` | 人物身份合并预览、明确确认与过期版本处理 |
| `src/components/UserDialog.vue` | 用户／记忆管理弹窗 |
| `src/components/HeartbeatStatus.vue` | 心跳计划时间与最近事件 |
| `src/styles/theme.css` | 主题层：设计令牌、导航、控件与卡片皮肤 |
| `src/styles/dashboard.css` | 基础布局与组件类 |
| `src/styles/workflow.css` | 工作流页专用样式 |
| `src/styles/contacts.css` | 联系人分类、详情分区与窄窗口布局 |
| `src/styles/base.css` | 基础样式与相对导入入口 |

改 `src/` 或样式后必须 `cd web && npm run build` 并提交 `dist/`，否则 `/app/` 仍是旧产物。
新增页面：在 `src/views/` 加组件 → 在 `App.vue` 的 `VIEWS` 注册 → 在 `router.js` 的 `TABS` 加导航项，
并补 `scripts/smoke.mjs` 的断言。

### scripts/ —— 启动与运维

| 文件 | 职责 |
|---|---|
| `scripts/setup.ps1` | 安装：uv 同步依赖（回退 pip 可编辑安装），再进安装向导 |
| `scripts/dashboard.bat` | 启动管理台（读取 `config.log.toml`，成功后开浏览器） |
| `scripts/dashboard_startup.bat` | 开机／计划任务用的管理台启动器 |
| `scripts/wechat_stack_start.bat` | 启动微信栈 |
| `scripts/wechat_stack_stop.bat` | 停止微信栈 |
| `scripts/wechat_stack_ctl.py` | 栈一键启停状态机（wxbot + 管理台） |
| `scripts/wxbot_run.py` | 以脱离当前会话的方式拉起 wxbot 主循环（进程组独立） |
| `scripts/wxbot_startup.bat` | 开机／计划任务用的 wxbot 启动器 |
| `scripts/launchers/*.vbs` | 无窗口自启动包装（wxbot、管理台） |
| `scripts/restart_dashboard.py` | 重启管理台：杀掉监听端口的进程，交给看门狗拉起 |
| `scripts/wxbot_send.py` | 经 wxbot 往微信发一条消息（走 UI 自动化） |
| `scripts/wxbot_deliver.py` | 经 wxbot 投递提醒／推送；wxbot 不可用时转入补发队列，不丢消息 |
| `scripts/butler_push.py` | cron → Butler 投递：记外发日志并转 wxbot 代发 |
| `scripts/butler_reminder_create.py` | 一条命令创建一条微信定时提醒 |
| `scripts/butler_reminder_push.py` | 提醒投递（`no_agent` cron 专用） |
| `scripts/butler_habit_nudge.py` | 工作日随机时间提醒喝水、活动颈椎腰椎 |
| `scripts/wxbot_channel.json` | 通道描述（供看板与归属推断使用） |

### tools/ —— 探活与打包

| 文件 | 职责 |
|---|---|
| `tools/probe.py` | 打印微信窗口控件树，确认控件能否读到、怎么定位 |
| `tools/debug_read.py` | 检查窗口、消息列表、输入框，以及每条消息被判成谁发的 |
| `tools/probe_codex.py` | 可选的真实 Codex 探针：临时服务与状态，绝不发微信 |
| `tools/release.py` | 按显式白名单打两个可移植包，不依赖 Git 状态；内含凭据形状审计 |

参数、脱敏规则与打包白名单明细见 `tools/README.md`。

### plugins/butler-wechat —— Codex 插件

| 位置 | 职责 |
|---|---|
| `skills/roles/butler-companion/SKILL.md` | 角色：日常陪伴对话 |
| `skills/roles/paimon/SKILL.md` 与同目录 md | 角色：派蒙（人物设定、关系、记忆、冲突处理） |
| `skills/roles/tong-jincheng-perspective/` | 角色：童锦程视角及研究参考材料 |
| `skills/tools/butler-memory/SKILL.md` | 工具：记忆读写边界 |
| `skills/tools/create-cron-job/SKILL.md` | 工具：创建定时任务 |
| `skills/tools/telegram-relay/SKILL.md` | 工具：Telegram 频道窗口转发 |
| `skills/tools/setup/SKILL.md` | 工具：安装引导（仅安装时使用，不进入业务工具白名单） |
| `THIRD_PARTY.md` | 第三方素材来源与许可 |

插件的 `.md` 是运行时资产，改动会影响模型行为，不当普通文档处理。
角色放在 `skills/roles/`，工具放在 `skills/tools/`；插件清单分别声明这两个加载目录。
Butler 递归读取统一的 `skills/` 根目录，按 `roles/` 和 `tools/` 子目录识别类型；角色不需要声明 `metadata.butler.tags`，旧平铺目录仍兼容标签识别。
工具权限声明保留，并由服务端结合当前会话授权校验；目录分类本身不授予工具执行权限。

### tests/ —— 离线测试（仅本地，不入 Git）

`tests/` 写在 `.gitignore` 里，不随仓库提交、也不进发布包，只存在于开发机上。
全离线：用临时配置、临时数据库、假 UI 和假投递，不发真实微信消息。

| 目录 | 覆盖 |
|---|---|
| `tests/conftest.py` | 注入 `src/`、仓库根与所有测试子目录到 `sys.path`；假 Hermes、临时配置、测试服务器、禁止真实剪贴板 |
| `tests/support/` | `paths.py`（`REPO_ROOT`）、`telegram_fakes.py`、`dashboard_preview.py`（独立临时预览） |
| `tests/unit/queue/` | 队列存储、迁移、并发、分句、失败策略、自动重试 |
| `tests/unit/codex/` | Codex 后端、API Key、时限、集成 |
| `tests/unit/model_stream/` | 模型流管线、传输与投影 |
| `tests/unit/text/` | 分句、剪贴板、分批输入、@ 提及 |
| `tests/unit/media/` | 图片投递与媒体外发 |
| `tests/unit/wxbot/` | 主窗口、收件轮询、群成员身份、运行时设置 |
| `tests/butler/` | 主流程、传输、并发、推送、转发、身份、Telegram、任务、心跳 |
| `tests/dashboard/` | 管理台视图、HTTP 胶水、配置编辑、队列动作、工作流 |
| `tests/integration/` | 跨包流转、安装向导、可移植安装、打包与 Telegram 发布 |

测试之间按文件名互相 import（如 `from test_typing import make_chat`），
所以 `conftest.py` 会把所有测试子目录加进 `sys.path`，不依赖收集顺序。
定位仓库根统一用 `from support.paths import REPO_ROOT`。

## 数据流与职责边界

主链路：微信主窗口 → `wxbot` SQLite 收件／合并 → `POST /v1/handle`（Butler 8770）→ 模型
（本机 Codex 或外部 Hermes／OpenAI 兼容服务）→ Butler → SQLite 发件 → wxbot UI 主线程回复。

主动推送：脚本或外部调度 → Butler `/v1/push` → wxbot 外发服务（8765）→ 发件队列 → 微信窗口。

- 窗口定位、轮询、消息差分、发送、`/ping` 等通道命令属于 wxbot。
- 联系人身份、模型 Profile/uid、会话 id、补发、静默、skill 决策属于 Butler。
- 管理台只读运行事实、写配置文件；不启动业务进程，不替业务发消息。
- 群聊由 wxbot 按右侧人数标签识别；`[bot].mention_names` 决定机器人昵称。微信 UIA
  不暴露群昵称，wxbot 用左侧头像感知哈希生成 `member_id`，真实昵称在
  `[wechat.group_sender.member_names]` 配；每批消息携 speaker/member_id 标签进入该成员的独立群会话。

## 接口与协议

### Butler HTTP

全部要求 `Authorization: Bearer <token>`，默认只绑 loopback。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 探活 |
| GET | `/v1/catalogue` | 行动 skill 目录 |
| POST | `/v1/handle` | 处理一条消息，返回完整回复与 `reply_parts` |
| POST | `/v1/handle-stream` | 同上，附带流式增量 |
| POST | `/v1/reset` | 轮换会话 id（`/new`、`/重置`） |
| POST | `/v1/push` | 主动推送（不调模型、不改会话） |
| POST | `/v1/push/bundle` | 图文组合投递 |
| POST/GET | `/v1/media`、`/v1/media/<id>` | 媒体登记与取回（只认服务端签发的不透明 ID） |
| GET | `/v1/runtime` | 运行时状态 |
| GET/POST | `/v1/users`、`/v1/users/observe`、`/v1/users/memory`、`/v1/users/audit` | 用户目录、身份观测、记忆与审计 |
| GET | `/v1/skills` | 技能目录（服务端读 Hermes） |
| POST | `/v1/jobs/delete` | 删除提醒任务 |
| POST | `/v1/group/archive` | 群归档 |
| POST | `/v1/heartbeat/trigger` | 立即触发心跳 |
| POST | `/v1/telegram/inbox` | Telegram 入库 |
| POST | `/v1/telegram-relay/authorize`、`/v1/telegram-relay/resolve` | 中继授权快照与核对 |
| POST | `/mcp` | 插件用 MCP 网关（无状态 Streamable HTTP） |

- 调用 Hermes 时同时传 `X-Hermes-Session-Key`（长期身份／记忆归属）与
  `X-Hermes-Session-Id`（同一段对话连续性）；只传前者会每轮派生新会话。
- 模型行动标记 `<<butler:action {"skill":"...","args":{...}}>>` 由 `agent/router.py`
  去掉并交 `agent/skills.py` 白名单执行；未知 skill 失败留痕。`<<butler:silent>>` 表示不回复。
- 每条消息开始先认领补发队列再调模型；模型失败或静默时仍要送出已认领的内容。
- 主动推送不改会话：`type=1` 指定联系人；`type=2` 按 `messageType` 从分组 JSON 逐人发送，
  每次推送重新读取。

### 管理台 HTTP

- 查询一律 `GET /api/...`，只读，不初始化／恢复／迁移队列，不创建运行锁。
- 写操作一律要求 JSON、专用动作头（如 `X-Wxbot-Queue-Action: 1`、`X-Wxbot-Config-Action: 1`）、
  明确 `acknowledge`，并校验可信 Host 与同源。
- 主要 GET：`/api/workflow`、`/api/workflow-content`、`/api/workflow-stream`、`/api/flow`、
  `/api/wxbot`、`/api/queue`、`/api/configuration`、`/api/contacts`、`/api/users`、`/api/jobs`、
  `/api/groups`、`/api/heartbeat-config`、`/api/heartbeat-status`、`/api/skills`、
  `/api/runtime`、`/api/connection`、`/api/telegram-relay`、`/api/news-config`、`/api/health`。
- 主要写：`/api/configuration`、`/api/queue-action`、`/api/queue-delete-unsent`、
  `/api/workflow-delete`、`/api/jobs/delete`、`/api/contacts`、`/api/users`、`/api/groups`、
  `/api/heartbeat-config`、`/api/heartbeat-trigger`、`/api/telegram-relay`、`/api/news-config`。

## 配置

- 单一 `pyproject.toml` / `requirements.txt` / `.venv`，声明 Python 3.14+；
  核心依赖 `uiautomation`、`requests`、`pillow`、`tomlkit`，锁文件 `uv.lock`。
- 从 `config.butler.example.toml`、`config.wxbot.example.toml`、`config.log.example.toml`
  生成本地配置，或直接跑 `python -m butler setup` 由向导写入。含 token/key 的本地配置不要提交。
- 相对运行路径以对应配置文件所在目录为基准，切换工作目录不会改变数据库或队列位置。
- 管理台自身配置是 `config.log.toml`（`LOG_CONFIG` 可覆盖）；命令行与环境变量优先于文件。
- 队列默认 `cache/wxbot_queue.sqlite3`；业务数据在 `data/business.sqlite3`；
  Codex 登录与会话在 `data/codex/`。这些目录与所有实际配置均不提交。

## 管理台

入口 `http://127.0.0.1:8788/app/`，根路径 `/` 会 302 到 `/app/` 并保留查询参数。
默认进入 `?tab=workflow` 实时工作流；旧 `?tab=runtime/users/heartbeat/groups` 链接转到「联系人」对应区域。

| 页面 | 内容 |
|---|---|
| 实时工作流 | 每条消息的当前位置、动态连线、工具进度、失败倒计时；点选看正文与完整回复 |
| 收发队列 | 待处理／异常待核对／历史分区，逐类分页；异常旁有重试、确认已发、立即丢弃 |
| 联系人 | 默认会话列表按“私聊 / 群聊”分区并分别计数；另有“私聊 / 群聊 / 待确认”分类，私聊只列有私聊窗口的人，纯群成员从群详情打开资料并可返回原群；状态与问题类型单独筛选，详情分概览、基本资料、AI 设置、主动消息、群身份、个人记忆和身份管理（唯一来源 `data/business.sqlite3`） |
| 定时任务 | 按归属分组的卡片；Butler 提醒可逐条删除 |
| 配置管理 | 六个分类的可编辑配置：中文名称、用途、来源、生效方式；保留注释、备份与 409 版本冲突 |
| Telegram 转发 | 转发设置与人工核对 |

- 页面只保存排序与列表收起偏好；配置草稿留在内存，刷新整个浏览器会丢失。
- 密钥原值不回传，可显式保持／替换／清空；`***` 占位不能写回配置文件。
- 模型字段按页面的生效提示供后续请求使用，其余文件值不代表运行进程已加载的值；页面不会自动重启服务。

### 联系人管理规则

- 人物显示名、微信窗口名称、群成员昵称分别维护。“微信窗口名称”用于在微信主窗口定位聊天，不是真实微信账号。
- 修改人物姓名或群昵称不会合并人物；不同人物在同一群可以重名，管理页面保留各自入口。仅有群身份无需创建私聊。
- 角色与允许功能显示最终配置及来源；会话单独设置优先于联系人默认设置，明确取消继承的会话不会误显示默认角色。
- 主动消息按窗口维护订阅和自动问候，显示发送目标与运行记录；手动触发会先明确确认可能发送消息。
- 移除一条成员身份只清除该绑定及识别证据，最后一条被移除后也保留人物、窗口和个人记忆。“删除联系人”会清理该人物的全部身份、私聊窗口、头像和个人记忆，操作不可撤销。
- 联系人详情头部直接提供“删除联系人”，群聊详情提供“移除群聊”，所有详情分区均可使用，执行前保留原有确认提示。
- 身份关联和合并统一先读取 `GET /api/contacts/merge-preview?source_id=...&target_id=...`。返回双方身份、窗口、默认策略、记忆冲突、`version` 和 `preview_version`；联系人写动作 `merge`（以及兼容的 `link_binding`）必须提交对应的 `preview_version`。提交前事务内重算版本摘要；记忆、绑定或配置变化返回 409，需重新预览。
- 同名和相似头像仅作为管理候选；新增窗口/群身份不会隐式合并现有人物。旧管理员用户接口的 `create` 不复用同名人物，统一模式下旧 `link` 请改用上述合并预览流程。微信自动观察识别算法不在本轮重构范围内。
- 未命名空档案清理移至身份管理下的全局维护工具，展示服务端 `can_cleanup` 候选；`person_cleanup` 必须带明确的 `ids` 列表（最多 1000）。服务器在事务中再次排除带窗口、已确认身份、个人记忆、记忆来源或身份重定向的档案。
- 本轮无数据库迁移。后端改动由使用者手动重启 Butler 和管理台后加载；前端 `web/dist` 已构建，刷新页面加载。无需为本轮改动重启 wxbot。

前端纯规则回归可运行 `cd web` 后的 `node --test scripts/contactPresentation.test.mjs`；页面交互仍通过 `npm run build` 与 `npm run smoke` 校验，全部使用假数据。

## 微信 UI 与队列

- 默认 `[wechat].mode = "main"`：从 `mmui::MainWindow` 的 `session_list` 读会话行，
  行 `AutomationId` 形如 `session_item_<会话名>`；`[N条]` 是未读数，`[有人@我]` 是群提及提示。
- 群聊按右侧人数标签识别，`[bot].mention_names` 配机器人昵称；
  `[bot].group_reply_chance`（默认 0.1）与 `[bot].emoji_chance`（默认 0.2）决定非 @ 消息
  是否回复、发文字还是发表情。所有群消息都会进模型上下文。
- 队列：`quiet_seconds` 默认 3、`max_wait_seconds` 10、`confirm_timeout` 5，模型并发由
  `[queue].max_model_requests` 控制（默认 2）。同会话同成员连续文本合并，命令与其他成员发言形成边界。
- 发送：每批字符数 `wechat.typing.chunk_size`（默认 5）、间隔 `chunk_interval`（默认 0.5 秒）；
  支持 `full` / `chunked` / `streaming` 三种模式，缺省 `chunked`。
- 发件失败（`blocked`/`uncertain`）从首次失败起按 `retry_delay_seconds`（默认 20）自动重试，
  最多 `max_delivery_retries`（默认 2）次；满 `failure_discard_seconds`（默认 180）丢弃并留审计。
  同一个参数也是模型失败批次的放行时限：`retry_safe` 为否时不重试，到点后丢弃并继续后续消息。
- 回车后出现新增的「自己」气泡才算 `sent`；不确定不自动重放。输入框内容读不回来视为 blocked，不清草稿。
- 剪贴板备份失败时降级为清空写入并在发送后不恢复，但「序号为 0 且已有内容」这类风险仍拒绝。
- `[wechat.emoji]` 未校准（button/item 为空）时自动改发文字，校准后自动恢复发图。
- UI 自动化要求窗口可见、不遮挡、机器不锁屏；控件随微信版本变化，用 `tools/probe.py` 重新校准。

## Telegram 通道

三个互相独立的入口，都不启动其它服务：

| 入口 | 用途 |
|---|---|
| `python -m butler.channels.telegram` | 本地 Telethon 登录，收指定频道文字，按配置转发到微信分组（只收不回） |
| `python -m butler.channels.telegram.bot` | Bot API 长轮询入库，可把消息转成新闻投递；`init\|run\|status\|retry-media` |
| `python -m butler.news [--preview]` | 汇总 RSS 生成日报，经 Butler 推送接口投递 |

转发配置在管理台「Telegram 转发」页维护；`relay/settings.py` 是带版本的设置，
`relay/store.py` 存持久化观察与逐频道任务。Telegram Desktop 的界面状态机只在 wxbot 的 UI 线程跑。

## 测试、校验与发布

```powershell
.\.venv\Scripts\python.exe -m pytest                        # 全离线
.\.venv\Scripts\python.exe -m compileall -q src            # 抓漏改的导入
cd web; npm.cmd run build; npm.cmd run smoke                 # 前端构建与冒烟
.\.venv\Scripts\python.exe tools\release.py                # 打两个包
```

`tools/release.py` 按显式白名单打包：根文件 + `src`/`web`/`plugins` 三个目录 +
若干特例文件；排除 `.venv`、`node_modules`、`data`、`cache`、`dist`、`__pycache__`、
`*.session`、`auth.json`、`config.*.toml` 与备份。打包前会扫描凭据形状的字面量，命中直接拒绝。

真实外部连接、Telegram 转发和微信发送必须另行授权验证，离线测试不能代表这些结果。

## 维护约定

### 项目知识图谱

用 Obsidian 打开 [`llm wiki/wxbot/`](<llm wiki/wxbot/>)，从
[`index.md`](<llm wiki/wxbot/index.md>) 进入；覆盖范围与步骤见
[`coverage.md`](<llm wiki/wxbot/coverage.md>) 和 [`guide.md`](<llm wiki/wxbot/guide.md>)。
改前先查图、核对源码并说明影响面；改后先写 `raw/changes/`，模型整合词条后入库、巡检。

```powershell
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" query /v1/handle reply_complete
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" change topic --title "变更目标"
# 填完记录、核对代码并更新词条及其来源后：
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" ingest YYYY-MM-DD-topic
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" lint
```

脚本只检索与登记证据，不调用模型或运行服务；语义更新由开发模型完成。
首批覆盖消息处理核心，其余模块逐步扩展。图谱不加入应用发布白名单。

### 开发边界

- Butler、wxbot 和管理台都由使用者在 IDE 里手动启停；改代码后明确告知需要重启哪个进程，
  不要代为停止或重启，也不要在未授权时给真人发微信。
- UI 自动化是非官方方式，存在账号风险；发送走剪贴板分批粘贴，仍依赖窗口焦点。
- `config.*.example.toml` 是安全的示例来源；运行时配置可能含真实密钥，不要在日志、
  提交或回复里复制秘密。
- `src/butler/agent/skills.py` 的 `HERMES_HINT` 只是本地行动协议，实际提示词仍需由
  Hermes Profile 的 SOUL/skill 引导模型发标记。
- `reminder.create/list/cancel` 是本地实现，其余 catalog 项再委派模型；
  `reminder.cancel` 会先改 `reminders.json` 再原子替换 cron `jobs.json`，两者要保持一致。
- 新增模块按分层归位：决策进 `agent/`，身份进 `identity/`，投递进 `delivery/`，
  安装／迁移／运行支撑进 `runtime/`，外部通道进 `channels/`。
- 不要加 `sys.path` 花招：仓库根用 `common.paths.REPO_ROOT`，包靠可编辑安装导入。

