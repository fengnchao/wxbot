# wxbot 进程

项目入口。wxbot 管微信 UI 与持久队列，Butler 管身份、权限、模型编排与业务任务，管理台负责观察与显式管理。安装、运行、发布、开发维护和全部节点索引集中在这里。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 项目文档维护

### 2026-11-07 更正：旧架构图退役

按项目所有者要求移除根目录 ARCHITECTURE.html，唯一维护入口为
[Archify 项目架构图](../.archify/architecture-wxbot-20261107-201947/wxbot.html)。
此决定替代前次“旧图仍可保留作展示入口”的安排。AGENTS 与发布清单均指向新版 HTML；
发布包只收录该新图，不收录旧图或 .archify 中的其他临时文件。

33 份节点文档全部保留。architecture-notes/index.json 的 diagram 字段指向新图，
每份文档的 diagram_nodes 字段记录其对应的新图概览节点；细分处理器、常驻角色等资料按责任归属到概览节点。
节点校验不再读取旧 HTML，而是核对新图节点 ID、文档目录及直接按钮映射。

旧图原文保存在 .archify/document-migration-20261107-204541/retired-architecture.zip，
文件摘要记录 retired-architecture.json。下方历史段落中的旧图链接指向这个原文归档。
本次不涉及业务 API/DTO、数据库迁移、前端管理台或后台任务；无需重启业务服务。

### 2026-11-07 更正：Archify 目录校验使用新版 HTML

新图节点详情中的「文档」按钮，选择项目根目录后逐级读取
`.archify/architecture-wxbot-20261107-201947/wxbot.html`，以当前 Archify HTML 的存在校验项目目录。
不会再读取根目录 `ARCHITECTURE.html` 做这一步校验。只有旧图的目录或直接选择 Archify 子目录都会被拒绝。
节点文件仍位于项目根目录的 `architecture-notes/`，本次不移动文档或修改绑定关系。

此更正替代下方历史资料中“选择包含根目录 ARCHITECTURE.html 的目录进行校验”的旧说明；
旧图仍可保留作展示入口，且不再是新版文档按钮的校验依赖。
实现为新图同目录的 `node-notes.extension.html`，重新生成后用 `apply-node-notes.py` 应用。
浏览器回归使用内存文件句柄，覆盖仅有旧图、选错目录、按新路径校验，以及已有读写、冲突、草稿、焦点和键盘交互。
本次不涉及业务 API/DTO、数据库迁移、前端管理台、后台任务或业务服务重启。

开发说明仅维护在 architecture-notes/ 的节点文档中。先读本文件及对应节点，核对源码和调用方，再同步节点说明与相关链接。记录 API/字段、数据血缘、前后端消费者、异步任务、测试和回滚，不涉及项写明原因。

旧 llm wiki/wxbot/ 的 Markdown 已迁入节点；其旧 CLI、JSON 快照和 Obsidian 配置属于退役工具资料，不再执行 change/ingest/lint 工作流。保留的源码仅供追溯。运行时的用户知识 vault、角色和 Skill 与开发文档互不混用。

发布包包含 architecture-notes/ 与当前 Archify HTML，原 README.md 已归入节点。入口为 python -m butler start；进程仍由使用者手动启停。节点文档通过 Archify 的“文档”按钮访问。

## 文档归并实施与验收计划

目标：将项目说明和旧开发知识图谱按节点归并，保留 AGENTS.md、运行用 Skill/角色/模板和许可归属文件。

- [x] 冻结清单与文件摘要，备份原文及既有节点文档。
- [x] 按模块责任拆分 README，归并 API/表/符号、设计与历史记录，并重定向内部链接。
- [x] 核对每份来源的全部行有归属，生成节点索引和迁移清单。
- [x] 同步 AGENTS 入口、发布白名单与源码文档指针，验证后删除来源 Markdown。
- [x] 核对节点绑定、文档链接、保留文件摘要与临时发布包；记录结果。

回滚：本次原文 ZIP、来源摘要与迁移映射保存在 .archify/document-migration-20261107-204541/；恢复前先比较当前节点文件，保留迁移后的用户编辑。

## 本次文档迁移结果（2026-11-07）

- 160 份旧说明/知识图谱 Markdown 的全部行拆分为 204 段，归入 33 份实际节点绑定文档。原文、原节点说明和原 AGENTS 已存 ZIP，来源、行范围和摘要保存在迁移 manifest.json。
- 清理前逐一核对路径、文件摘要及原文归档，随后删除 160 份旧 Markdown；没有递归删除项目目录。
- 33 份节点绑定、2,072 个本地链接和来源锚点通过检查；22 份运行用插件 Skill/角色/模板/许可说明保持原始字节，AGENTS 保留并更新入口。
- 发布回归使用临时目录和假数据通过；tools/release.py 的临时应用包包含全部节点资料、索引与根架构图，插件包保留原功能文件，凭据形状审计无命中。
- 仅修改发布文档白名单、AGENTS 文档工作流和处理器的文档指针；不涉及运行时 API/DTO、业务字段、数据库迁移或后台任务。未启动/重启业务服务，未发送微信，未访问真实运行配置、数据库或剪贴板。
- 测试脚本在 tests/unit/test_release_node_documents.py（仅本地，不入库），本次原文归档与校验工具位于 .archify/document-migration-20261107-204541/；旧知识图谱的原 change/ingest 记录作为历史内容迁入节点，不继续运行旧图谱工作流。

## 全部节点索引

| 节点文档 | 迁入资料段数 |
|---|---|
| [业务存储](business-storage.md) | 0 |
| [Butler](butler.md) | 10 |
| [Butler 功能](butler-functions.md) | 7 |
| [Codex](codex.md) | 0 |
| [配置管理](configuration.md) | 1 |
| [聊天记录提炼](conversation-extraction.md) | 3 |
| [管理台](dashboard.md) | 11 |
| [表情处理器](delivery-emoji.md) | 0 |
| [图片处理器](delivery-image.md) | 0 |
| [统一发件调度](delivery-pump.md) | 10 |
| [文字处理器](delivery-text.md) | 0 |
| [语音处理器](delivery-voice.md) | 12 |
| [刷抖音](douyin.md) | 0 |
| [联系人身份与业务工具](identity-tools.md) | 15 |
| [收件队列](inbox.md) | 1 |
| [文件队列](inbox-file.md) | 0 |
| [图片队列](inbox-image.md) | 0 |
| [链接队列](inbox-link.md) | 0 |
| [文字队列](inbox-text.md) | 0 |
| [IndexTTS](index-tts.md) | 12 |
| [用户知识 vault](knowledge-vault.md) | 24 |
| [可切换模型后端](model-backends.md) | 12 |
| [文件发件队列](outbox-file.md) | 0 |
| [文字发件队列](outbox-text.md) | 1 |
| [语音发件队列](outbox-voice.md) | 0 |
| [收发队列存储](queue-storage.md) | 3 |
| [队列工作器](queue-worker.md) | 5 |
| [定时提醒](reminders.md) | 0 |
| [冯草草](resident.md) | 12 |
| [Skill](resident-skills.md) | 2 |
| [微信客户端](wechat-client.md) | 0 |
| [界面线程](wechat-ui.md) | 9 |
| [wxbot 进程](wxbot.md) | 54 |

## 原图节点说明

### wxbot 进程

负责监听微信窗口、将消息写入收件队列，并通过界面线程投递发件队列中的回复。

## 使用说明

- [wxbot / Butler](#doc-444746a8f4ae45) · `README.md`
- [wxbot / Butler / 安装](#doc-7a2b649bf980a1) · `README.md`
- [wxbot / Butler / 运行](#doc-2e0fdb7ecca3dc) · `README.md`
- [wxbot / Butler / 目录](#doc-e178651dba2d68) · `README.md`
- [wxbot / Butler / 开发基线与历史布局](#doc-6b478247a17ac2) · `README.md`
- [wxbot / Butler / 模块与文件职责](#doc-39647c7dcd78d9) · `README.md`
- [wxbot / Butler / 模块与文件职责 / src/common —— 跨包共用](#doc-97a684c459b114) · `README.md`
- [wxbot / Butler / 模块与文件职责 / src/wxbot —— 微信 UI 收发层](#doc-26722cd944ac40) · `README.md`
- [wxbot / Butler / 模块与文件职责 / src/wxbot —— 微信 UI 收发层 / 根目录](#doc-51827c911fad45) · `README.md`
- [wxbot / Butler / 模块与文件职责 / scripts/ —— 启动与运维](#doc-d785adba6e08ef) · `README.md`
- [wxbot / Butler / 模块与文件职责 / tools/ —— 探活与打包](#doc-6b3ce096bc6d11) · `README.md`
- [wxbot / Butler / 模块与文件职责 / tests/ —— 离线测试（仅本地，不入 Git）](#doc-8d1b6a58a9ba38) · `README.md`
- [wxbot / Butler / 数据流与职责边界](#doc-f6cee738b73093) · `README.md`
- [wxbot / Butler / 测试、校验与发布](#doc-afc7f2edb359cb) · `README.md`
- [wxbot / Butler / 维护约定](#doc-fe89b8634639ba) · `README.md`
- [wxbot / Butler / 维护约定 / 项目知识图谱](#doc-f149deca286e0e) · `README.md`
- [wxbot / Butler / 维护约定 / 开发边界](#doc-cd58dad2028698) · `README.md`
- [wxbot / Butler / 架构图节点文档](#doc-af40558e48160a) · `README.md`

<a id="doc-444746a8f4ae45"></a>

### wxbot / Butler

来源：`README.md:1`。

### wxbot / Butler

Windows 上的个人微信机器人：wxbot 负责微信窗口收发与持久队列，Butler 负责用户身份、权限、
提醒、心跳、知识库和消息接口，管理台负责展示与配置；模型可以是本机 Codex，也可以是已有的
智能体或 OpenAI 兼容 API。
正文通过剪贴板粘贴到微信输入框；默认分批粘贴并读回核对，再按回车、检查发送回执。

| 进程 | 入口 | 端口 | 职责 |
|---|---|---|---|
| wxbot | `python -m wxbot.main` | 8765（外发 HTTP） | 微信主窗口监听、群聊 @ 判定、收发队列、分批输入与发送 |
| Butler | `python -m butler.server --config config.butler.toml` | 8770 | 用户、权限、提醒、心跳、知识库、消息接口、插件 MCP |
| 管理台 | `python -m dashboard.server` | 8788 | 只读运行事实 + 写配置文件；页面在 `/app/` |

`python -m butler start` 按 `config.wxbot.toml` 的 `[installation].mode` 一次性拉起：
`local` 启动三个进程，`external` 只启动管理台与 wxbot。旧 `direct` 模式先显式迁移。端口被占用时保留已有进程，
绝不自动重启。
<!-- end-migrated-part: doc-444746a8f4ae45 -->

<a id="doc-7a2b649bf980a1"></a>

### wxbot / Butler / 安装

来源：`README.md:18`。

#### 安装

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
统一链路是 **wxbot → Butler → 所选模型/智能体**；联系人、身份、知识库和提醒由 Butler 持有，模型切换不迁移这些业务数据。
其它智能体使用已有的兼容协议接入，不假设任意 CLI 都支持 Cursor 协议。
外部 Butler 能力由远端管理，本机管理台会关闭对应的远端账户／心跳入口。
向导只写配置，不验证真实模型连接，也不启动服务。

生产默认链路固定为 `wxbot → Butler → 模型后端`。Hermes、OpenAI 兼容 API、Ollama 等作为
**Butler 后端**时属于正常接入方式；`src/wxbot/processor/` 中直接调用这些服务的适配器仅供
旁路调试和旧配置兼容，不作为生产默认。含 `[installation]` 的配置会拒绝非 `butler` 的
`[model].backend`；旧 direct 安装按下面的迁移步骤处理。

在管理台「配置管理 → 模型后端」切换 provider，页面按草稿选择显示地址、模型名、密钥或 Cursor 目录等适用字段。
保存模型设置后由后续请求使用；在途请求继续使用原后端，切换不会重放请求。运行监听、认证和数据目录仍需由使用者自行重启加载。
旧版 Hermes（没有 `[model]`）启动方式首次换模型需要手动重启 Butler；进入本地模型运行方式后适用热切换。加载本次新版代码也需使用者自行重启 Butler、管理台和 wxbot，前端刷新页面加载新 dist。
各后端保留各自会话范围，切换不承诺移植远端推理会话；支持的工具能力取决于实际后端协议，API Key 不是 Butler 工具授权。

旧 direct 安装先由使用者停掉本机服务，再执行 `python -m butler migrate --directory <安装目录>`。
迁移会把本安装的模型参数移到 Butler、将 wxbot 指向本机 Butler，并保留原配置的 `.model-backup-*` 备份。
备份同样含密钥，只留本机；不会自动启动服务或验证真实连接。
<!-- end-migrated-part: doc-7a2b649bf980a1 -->

<a id="doc-2e0fdb7ecca3dc"></a>

### wxbot / Butler / 运行

来源：`README.md:68`。

#### 运行

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
| `knowledge-extract` | 手动提炼一批事实（`--owner`、`--batch`、`--dry-run`），与自动提炼共用一把锁 |
| `knowledge-migrate` | 把 SQLite 时代的 `kb_*` 库与遗留 memory 表搬进 Obsidian vault，原文件改名留底 |
| `knowledge-prune` | 按 `retention_days` 删除过期原文，事实节点不动 |

服务一律由使用者手动启动与重启，不要去停止或重启别人的进程。
统一联系人迁移、备份和回退步骤见 `python -m butler contacts-preview --help` 与
`contact_migration` 的输出报告；迁移前必须自行停掉 Butler、管理台、wxbot，
以及旧心跳、提醒、看门狗等所有可能写入联系人数据的程序。
<!-- end-migrated-part: doc-2e0fdb7ecca3dc -->

<a id="doc-e178651dba2d68"></a>

### wxbot / Butler / 目录

来源：`README.md:104`。

#### 目录

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
data/           本机认证和运行数据（含知识图谱 vault），禁止提交 Git
config.*.toml   本机配置（默认路径硬编码在 src/butler/config.py，不要改名）
```

包都在 `src/` 下，靠 `pyproject.toml` 的可编辑安装导入：`python -m butler`、
`python -m dashboard.server`、`python -m wxbot.main` 在仓库外也能跑。
仓库根统一从 `common.paths.REPO_ROOT` 取，不要再写 `Path(__file__).resolve().parents[N]`。
<!-- end-migrated-part: doc-e178651dba2d68 -->

<a id="doc-6b478247a17ac2"></a>

### wxbot / Butler / 开发基线与历史布局

来源：`README.md:125`。

#### 开发基线与历史布局

每张工单先记录实际工作目录、分支、HEAD SHA 和未提交修改，再决定开发基线。分支名不是
运行版本证明；`main`、正式运行目录和开发 worktree 可能处于不同进度，不能跨版本拼接文档与代码。

```powershell
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git worktree list
```

再用当前目录的解释器核对实际代码根目录，避免可编辑安装误指向另一个 worktree：

```powershell
.\.venv\Scripts\python.exe -c "import sys; from common.paths import REPO_ROOT; print(sys.executable); print(REPO_ROOT)"
```

解释器路径和 `REPO_ROOT` 都应属于本次任务的工作树；不一致时先处理环境绑定，不能用另一份
代码的检查结果作为当前基线证据。图谱 CLI 可用 `--repo-root <当前项目根目录>` 显式限定读写范围，
但这不能替代修正业务运行时的可编辑安装。

比较正式目录与开发目录时，分别执行上述检查，再核对提交关系及差异；不要假定
`codex-butler-distribution` 和 `codex/grok-setup` 永远是当前分支或指向同一个 SHA。
已提交代码、未提交修改和进程已加载的版本分别核对，不自动切分支、合并或重启服务。
开发事实以任务指定工作树的代码、根 README 与依赖锁文件为准，结构导航见 `llm wiki/wxbot/`。

旧资料中的 `butler/README.md`、`PROJECT_MEMORY.md`、`kmg/`、`hermes_butler` 与 `D:\bot`
属于历史布局或安装示例；当前工作分支已无这些文档／包入口，不作为配置或导入依据。
Python 包只认 `src/butler/`、`src/wxbot/`、`src/dashboard/` 和 `src/common/`；旧目录里即使
残留 `__pycache__`，也不代表存在可维护的嵌套包。现存 `heartbeat/` 是受版本控制的辅助
看门狗脚本，不是 Butler 的心跳实现（`src/butler/runtime/heartbeat.py`），不整目录忽略或自动删除。
<!-- end-migrated-part: doc-6b478247a17ac2 -->

<a id="doc-39647c7dcd78d9"></a>

### wxbot / Butler / 模块与文件职责

来源：`README.md:159`。

#### 模块与文件职责

以下按目录列出每个模块的职责。`__init__.py` 只做包说明，不再单列。
<!-- end-migrated-part: doc-39647c7dcd78d9 -->

<a id="doc-97a684c459b114"></a>

### wxbot / Butler / 模块与文件职责 / src/common —— 跨包共用

来源：`README.md:279`。

##### src/common —— 跨包共用

不含微信 UI，也不依赖 Butler 业务。

| 文件 | 职责 |
|---|---|
| `common/paths.py` | `REPO_ROOT`：从 `pyproject.toml` 向上定位，可用 `WXBOT_ROOT` 覆盖 |
| `common/config_lock.py` | 配置写入的跨进程锁（管理台与 Butler 共用） |
| `common/flow_trace.py` | 只追加、不含消息正文的流转事件与字段白名单 |
| `common/media_bundle.py` | 两个服务之间严格、精简的图文 wire schema |
| `common/voice_audio.py` | PCM16 单声道重采样、按句拆文字与按静音分段音频 |
| `common/model_stream.py` | 公开、有界的模型观察，作用域是单个同步请求 |
| `common/avatar_identity.py` | 共享的带版本头像归一化；不访问桌面与剪贴板 |
| `common/news_config.py` | 管理台与日报共用的新闻目录与设置 |
<!-- end-migrated-part: doc-97a684c459b114 -->

<a id="doc-26722cd944ac40"></a>

### wxbot / Butler / 模块与文件职责 / src/wxbot —— 微信 UI 收发层

来源：`README.md:353`。

##### src/wxbot —— 微信 UI 收发层
<!-- end-migrated-part: doc-26722cd944ac40 -->

<a id="doc-51827c911fad45"></a>

### wxbot / Butler / 模块与文件职责 / src/wxbot —— 微信 UI 收发层 / 根目录

来源：`README.md:355`。

###### 根目录

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
| `wxbot/delivery.py` | 统一发件调度：认领 outbox、协调 UI、保存状态、回执及恢复核对 |
| `wxbot/delivery_handlers/` | text/voice/image/emoji 独立处理器；文字与图片共用目标、草稿与气泡保护，语音持有后台准备状态 |
| `wxbot/delivery_policy.py` | 事务化的回复生命周期；无 UI、网络与启动副作用 |
| `wxbot/reply.py` | 与后端无关的完整回复对象，可安全跨线程传递 |
| `wxbot/streaming.py` | 增量最终答复的句子边界，不切开受保护的 token |
| `wxbot/stream_queue.py` | 仅运行期的辅助流存储，不参与旧库迁移 |
| `wxbot/model_recovery.py` | 只读的模型失败策略，运行期与看板投影共用 |
| `wxbot/relay_authorization.py` | 短时中继权限快照；UI 调用方不自己做 HTTP |
| `wxbot/telegram_desktop.py` | Telegram Desktop 状态机，只在 wxbot 的 UI 线程里跑 |
<!-- end-migrated-part: doc-51827c911fad45 -->

<a id="doc-d785adba6e08ef"></a>

### wxbot / Butler / 模块与文件职责 / scripts/ —— 启动与运维

来源：`README.md:457`。

##### scripts/ —— 启动与运维

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
<!-- end-migrated-part: doc-d785adba6e08ef -->

<a id="doc-6b3ce096bc6d11"></a>

### wxbot / Butler / 模块与文件职责 / tools/ —— 探活与打包

来源：`README.md:479`。

##### tools/ —— 探活与打包

| 文件 | 职责 |
|---|---|
| `tools/probe.py` | 打印微信窗口控件树，确认控件能否读到、怎么定位 |
| `tools/debug_read.py` | 检查窗口、消息列表、输入框，以及每条消息被判成谁发的 |
| `tools/probe_codex.py` | 可选的真实 Codex 探针：临时服务与状态，绝不发微信 |
| `tools/release.py` | 按显式白名单打两个可移植包，不依赖 Git 状态；内含凭据形状审计 |

参数、脱敏规则与打包白名单明细见 `tools/README.md`。
<!-- end-migrated-part: doc-6b3ce096bc6d11 -->

<a id="doc-8d1b6a58a9ba38"></a>

### wxbot / Butler / 模块与文件职责 / tests/ —— 离线测试（仅本地，不入 Git）

来源：`README.md:509`。

##### tests/ —— 离线测试（仅本地，不入 Git）

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
<!-- end-migrated-part: doc-8d1b6a58a9ba38 -->

<a id="doc-f6cee738b73093"></a>

### wxbot / Butler / 数据流与职责边界

来源：`README.md:532`。

#### 数据流与职责边界

主链路：微信主窗口 → `wxbot` SQLite 收件／合并 → `POST /v1/handle`（Butler 8770）→ 模型
（本机 Codex 或外部 Hermes／OpenAI 兼容服务）→ Butler → SQLite 发件 → wxbot UI 主线程回复。

主动推送：脚本或外部调度 → Butler `/v1/push` → wxbot 外发服务（8765）→ 发件队列 → 微信窗口。

- 窗口定位、轮询、消息差分、发送、`/ping` 等通道命令属于 wxbot。
- 联系人身份、模型 Profile/uid、会话 id、补发、静默、skill 决策属于 Butler。
- 管理台只读运行事实、写配置文件；不启动业务进程，不替业务发消息。
- 群聊由 wxbot 按右侧人数标签识别；`[bot].mention_names` 决定机器人昵称。微信 UIA
  不暴露群昵称，wxbot 用左侧头像感知哈希生成 `member_id`，真实昵称在
  `[wechat.group_sender.member_names]` 配；每批消息携 speaker/member_id 标签进入该成员的独立群会话。
<!-- end-migrated-part: doc-f6cee738b73093 -->

<a id="doc-afc7f2edb359cb"></a>

### wxbot / Butler / 测试、校验与发布

来源：`README.md:770`。

#### 测试、校验与发布

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
<!-- end-migrated-part: doc-afc7f2edb359cb -->

<a id="doc-fe89b8634639ba"></a>

### wxbot / Butler / 维护约定

来源：`README.md:785`。

#### 维护约定
<!-- end-migrated-part: doc-fe89b8634639ba -->

<a id="doc-f149deca286e0e"></a>

### wxbot / Butler / 维护约定 / 项目知识图谱

来源：`README.md:787`。

##### 项目知识图谱

用 Obsidian 打开 [`llm wiki/wxbot/`](wxbot.md)，从
[`index.md`](wxbot.md#doc-6e5a10e80a7955) 进入；覆盖范围与步骤见
[`coverage.md`](wxbot.md#doc-3d945de7c38143) 和 [`guide.md`](wxbot.md#doc-9cf47fd939c877)。
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
<!-- end-migrated-part: doc-f149deca286e0e -->

<a id="doc-cd58dad2028698"></a>

### wxbot / Butler / 维护约定 / 开发边界

来源：`README.md:805`。

##### 开发边界

- Butler、wxbot 和管理台都由使用者在 IDE 里手动启停；改代码后明确告知需要重启哪个进程，
  不要代为停止或重启，也不要在未授权时给真人发微信。
- UI 自动化是非官方方式，存在账号风险；发送走剪贴板分批粘贴，仍依赖窗口焦点。
- 公开配置参考 `src/butler/defaults.py`；新增 `config.*.example.toml` 时必须保持无凭据。
  运行时配置可能含真实密钥，不要在日志、提交或回复里复制秘密。
- `src/butler/agent/skills.py` 的 `HERMES_HINT` 只是本地行动协议，实际提示词仍需由
  Hermes Profile 的 SOUL/skill 引导模型发标记。
- `reminder.create/list/cancel` 是本地实现，其余 catalog 项再委派模型；
  `reminder.cancel` 会先改 `reminders.json` 再原子替换 cron `jobs.json`，两者要保持一致。
- 新增模块按分层归位：决策进 `agent/`，身份进 `identity/`，投递进 `delivery/`，
  安装／迁移／运行支撑进 `runtime/`，外部通道进 `channels/`。
- 不要加 `sys.path` 花招：仓库根用 `common.paths.REPO_ROOT`，包靠可编辑安装导入。
<!-- end-migrated-part: doc-cd58dad2028698 -->

<a id="doc-af40558e48160a"></a>

### wxbot / Butler / 架构图节点文档

来源：`README.md:849`。

#### 架构图节点文档

发件重构第一步已实现：一张 `outbox` 按 `kind=text/voice/image/emoji` 分派到独立处理器，
仍由 `DeliveryPump` 统一调度，同会话跨类型顺序由原认领 SQL 保证。数据库、HTTP 与配置字段不变。
图中 `reply_type` 分流、合成后入语音队列及文件队列仍是后续规划；当前自动语音在认领后准备音频。

用 Edge 或 Chrome 打开根目录的 [ARCHITECTURE.html 原文归档](../.archify/document-migration-20261107-204541/retired-architecture.zip)。点击节点后选「选择项目目录」，
选择包含该 HTML 的项目根目录并允许读写。节点可查看和编辑 Markdown 源文，首次保存会创建
`architecture-notes/<节点键>.md`。同一组件在图中重复出现时共用一份文件。

Archify 版 [项目架构图](../.archify/architecture-wxbot-20261107-201947/wxbot.html) 沿用同一套节点文档：
点击节点，在详情浮层点「文档」，再选择包含根目录 `ARCHITECTURE.html` 的项目目录。
已有组件复用原文件；模型后端、身份与工具、知识 vault、配置分别使用
`model-backends.md`、`identity-tools.md`、`knowledge-vault.md`、`configuration.md`，首次保存才创建。
只读 Markdown 源文，不执行其中的 HTML；保存前复查磁盘内容，检测到外部改动时保留草稿并拒绝覆盖。
如果重新生成 Archify HTML，再运行同目录的 `apply-node-notes.py` 恢复按钮和编辑器。
该按钮是本地定制扩展，原 Archify 生成回执只对应扩展前版本；定制后的浏览器验证见同目录
`node-notes-verification.json`，使用内存文件句柄，不读写真实笔记。
<!-- end-migrated-part: doc-af40558e48160a -->

## 技术资料

- [[2026-10-31] change | 项目知识图谱首批建档与维护闭环](#doc-2359f8bc64950b) · `llm wiki/wxbot/changelog.md`
- [架构图节点文档](#doc-6372a6d15b637a) · `llm wiki/wxbot/concepts/architecture-node-notes.md`
- [开发基线与历史布局](#doc-f0b302749d6eb3) · `llm wiki/wxbot/concepts/development-baseline.md`
- [消息主链路与字段传递](#doc-6cbfc97cc45d15) · `llm wiki/wxbot/concepts/message-pipeline.md`
- [建档覆盖范围](#doc-3d945de7c38143) · `llm wiki/wxbot/coverage.md`
- [项目知识图谱实施方案](#doc-ba7d4d46f1c73f) · `llm wiki/wxbot/design.md`
- [查图与维护](#doc-9cf47fd939c877) · `llm wiki/wxbot/guide.md`
- [项目知识图谱](#doc-6e5a10e80a7955) · `llm wiki/wxbot/index.md`
- [共享基础能力](#doc-dd2bd595b3d8f8) · `llm wiki/wxbot/modules/common.md`
- [项目知识图谱工具](#doc-ed5d88ddcd1b47) · `llm wiki/wxbot/modules/wiki.md`
- [wxbot UI 与持久队列](#doc-8508032cbe5131) · `llm wiki/wxbot/modules/wxbot.md`
- [项目知识图谱 Implementation Plan](#doc-f68e362b618ab8) · `llm wiki/wxbot/plan.md`
- [标题](#doc-9be513138ee5dc) · `llm wiki/wxbot/templates/api.md`
- [修改记录](#doc-876e1a0156045c) · `llm wiki/wxbot/templates/change.md`
- [标题](#doc-66a8899f322d51) · `llm wiki/wxbot/templates/concept.md`
- [改前影响分析](#doc-2595bebb318aaa) · `llm wiki/wxbot/templates/impact.md`
- [标题](#doc-6a76d4ecff85eb) · `llm wiki/wxbot/templates/module.md`
- [标题](#doc-b7b71e230e267e) · `llm wiki/wxbot/templates/symbol.md`
- [标题](#doc-b29fabcf0318a0) · `llm wiki/wxbot/templates/table.md`
- [本次验证记录](#doc-951820f4d5f621) · `llm wiki/wxbot/verification.md`
- [tools](#doc-aa2bc4bbdc2544) · `tools/README.md`

<a id="doc-2359f8bc64950b"></a>

### [2026-10-31] change | 项目知识图谱首批建档与维护闭环

来源：`llm wiki/wxbot/changelog.md:1`。


#### [2026-10-31] change | 项目知识图谱首批建档与维护闭环

来源：[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

#### [2026-10-31] ingest | 项目知识图谱首批建档与维护闭环

来源：[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/common](wxbot.md#doc-dd2bd595b3d8f8)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/delivery](butler-functions.md#doc-f61f55fe09c5e9)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/plugin](resident-skills.md#doc-709338d3e083eb)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[modules/telegram](butler-functions.md#doc-8b0e2206d40805)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)、[symbols/model-worker](queue-worker.md#doc-0183b6974519f0)、[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-inbox](inbox.md#doc-6529d9966e604a)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)

#### [2026-10-31] query | 首批真实关键词查询

关键词 `/v1/handle`、`reply_complete`，沿双向链接展开一跳，返回处理接口、队列和管理台消费候选。实施影响报告：[impacts/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-0c3db1f926d782)。

#### [2026-10-31] lint | 首批一致性巡检与交付验证

27 个词条通过机械巡检，待入库记录 0；专项回归 20 passed / 1 skipped。整库回归未通过和语义覆盖边界见 [verification](wxbot.md#doc-951820f4d5f621)、[coverage](wxbot.md#doc-3d945de7c38143)。来源：[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)。

#### [2026-10-31] change | 保留 batches 词条后续表格排版

巡检检出入库后的词条排版变化，保留当前编辑并核对事实。来源：[raw/changes/2026-10-31-queue-batches-format](queue-worker.md#doc-33b232c2a9cf1f)。

#### [2026-10-31] ingest | 保留 batches 词条后续表格排版

来源：[raw/changes/2026-10-31-queue-batches-format](queue-worker.md#doc-33b232c2a9cf1f)

[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)

#### [2026-10-31] ingest | 统一 Butler 模型链路与随时切换

来源：[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/models](model-backends.md#doc-69928b2a06b8f9)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)、[symbols/local-model-backend](model-backends.md#doc-058aec74f1727e)、[symbols/reloadable-backend](model-backends.md#doc-85aba8d0cc88bd)

#### [2026-10-31] ingest | 配置页接入方式下拉与模型字段随选择变化

来源：[raw/changes/2026-10-31-model-access-switch](model-backends.md#doc-954a7ea1e7487b)

[modules/models](model-backends.md#doc-69928b2a06b8f9)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/butler](butler.md#doc-38393df7a7b4da)、[symbols/local-model-backend](model-backends.md#doc-058aec74f1727e)

#### [2026-10-31] ingest | 模型来源上报改用接入方式（core.py 相关词条更正）

来源：[raw/changes/2026-10-31-model-access-switch-core-emit](model-backends.md#doc-6510cadeadeb37)

[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)

#### [2026-10-31] ingest | 群成员身份改用昵称优先，头像只作证据

来源：[raw/changes/2026-10-31-group-identity-nickname](identity-tools.md#doc-f39c15a6fe0885)

[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[modules/common](wxbot.md#doc-dd2bd595b3d8f8)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-inbox](inbox.md#doc-6529d9966e604a)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)

#### [2026-10-31] ingest | 截图占位名不再当作群昵称重放

来源：[raw/changes/2026-10-31-identity-placeholder-names](identity-tools.md#doc-f3232d3cef51df)

[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)

#### [2026-11-01] change | model request failure keeps redacted status

来源：[raw/changes/2026-11-01-model-request-error-visibility](model-backends.md#doc-507fd880895f6c)

#### [2026-11-01] ingest | 模型请求失败保留脱敏状态码

来源：[raw/changes/2026-11-01-model-request-error-visibility](model-backends.md#doc-507fd880895f6c)

[symbols/local-model-backend](model-backends.md#doc-058aec74f1727e)、[modules/models](model-backends.md#doc-69928b2a06b8f9)

#### [2026-11-01] change | model failure contract archived as concept

来源：[raw/changes/2026-11-01-model-error-contract](model-backends.md#doc-60c1969bb5f6f6)

#### [2026-11-01] ingest | 模型失败契约补齐为概念词条

来源：[raw/changes/2026-11-01-model-error-contract](model-backends.md#doc-60c1969bb5f6f6)

[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[modules/models](model-backends.md#doc-69928b2a06b8f9)

#### [2026-11-01] ingest | L1 聊天原文落库与只读看板

来源：[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)

#### [2026-11-01] change | 知识库拆分为一人一库并新增提炼事实库

来源：[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

#### [2026-11-01] ingest | 知识库拆分为一人一库并新增提炼事实库

来源：[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)、[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)

#### [2026-11-01] change | 会话维度：左栏按人、右栏按私聊/群聊再筛

来源：[raw/changes/2026-11-01-knowledge-sessions](knowledge-vault.md#doc-ba214c308af8ff)

#### [2026-11-01] ingest | 会话维度：左栏按人、右栏按私聊/群聊再筛

来源：[raw/changes/2026-11-01-knowledge-sessions](knowledge-vault.md#doc-ba214c308af8ff)

[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)

#### [2026-11-01] change | 自动提炼：进程内调度器、跨进程单飞与管理台状态

来源：[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)

#### [2026-11-01] ingest | 自动提炼：进程内调度器、跨进程单飞与管理台状态

来源：[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)

[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/models](model-backends.md#doc-69928b2a06b8f9)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)、[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)

#### [2026-11-01] change | 群聊提及回退清理与不可读未读的退避放弃

来源：[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

#### [2026-11-01] ingest | 群聊提及回退清理与不可读未读的退避放弃

来源：[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)、[modules/telegram](butler-functions.md#doc-8b0e2206d40805)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7)、[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-inbox](inbox.md#doc-6529d9966e604a)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)

#### [2026-11-01] change | 词条代码引用行号复核

来源：[raw/changes/2026-11-01-citation-sweep](wxbot.md#doc-4d0e5fc0ed39d9)

#### [2026-11-01] ingest | 词条代码引用行号复核

来源：[raw/changes/2026-11-01-citation-sweep](wxbot.md#doc-4d0e5fc0ed39d9)

[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)

#### [2026-11-01] change | README 补不可采集未读的说明与图谱来源修正

来源：[raw/changes/2026-11-01-readme-unread-note](wechat-ui.md#doc-0dfa536a596503)

#### [2026-11-01] ingest | README 补不可采集未读的说明与图谱来源修正

来源：[raw/changes/2026-11-01-readme-unread-note](wechat-ui.md#doc-0dfa536a596503)

[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)

#### [2026-11-01] change | 用户知识库改为一人一个 Obsidian vault 并删除 memory 链路

来源：[raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)

#### [2026-11-01] ingest | 用户知识库改为一人一个 Obsidian vault 并删除 memory 链路

来源：[raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)

[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)、[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/plugin](resident-skills.md#doc-709338d3e083eb)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[modules/common](wxbot.md#doc-dd2bd595b3d8f8)、[modules/models](model-backends.md#doc-69928b2a06b8f9)、[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)、[symbols/local-model-backend](model-backends.md#doc-058aec74f1727e)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)、[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)

#### [2026-11-01] change | 知识库 vault 词条与实现对齐

来源：[raw/changes/2026-11-01-knowledge-vault-alignment](knowledge-vault.md#doc-3f269e1ad8b05e)

#### [2026-11-01] ingest | 知识库 vault 词条与实现对齐

来源：[raw/changes/2026-11-01-knowledge-vault-alignment](knowledge-vault.md#doc-3f269e1ad8b05e)

[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)

#### [2026-11-01] change | 知识库迁移改名留底前先合并 WAL

来源：[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)

#### [2026-11-01] ingest | 知识库迁移改名留底前先合并 WAL

来源：[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)

[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)

#### [2026-11-01] change | 迁移改动后复核知识库词条来源

来源：[raw/changes/2026-11-01-knowledge-migrate-source-recheck](knowledge-vault.md#doc-97b2533a5ffcf7)

#### [2026-11-01] ingest | 迁移改动后复核知识库词条来源

来源：[raw/changes/2026-11-01-knowledge-migrate-source-recheck](knowledge-vault.md#doc-97b2533a5ffcf7)

[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)

#### [2026-11-01] change | 知识库加中心索引页与七类事实分组

来源：[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)

#### [2026-11-01] ingest | 知识库加中心索引页与七类事实分组

来源：[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)

[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)

#### [2026-11-01] change | 知识库写入在文件被占用时退避重试

来源：[raw/changes/2026-11-01-knowledge-atomic-retry](knowledge-vault.md#doc-8614fbc4e2f39c)

#### [2026-11-01] ingest | 知识库写入在文件被占用时退避重试

来源：[raw/changes/2026-11-01-knowledge-atomic-retry](knowledge-vault.md#doc-8614fbc4e2f39c)

[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)

#### [2026-11-02] ingest | 知识图谱模板外部化为 Markdown 并支持管理台在线编辑

来源：[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)

[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)、[symbols/knowledge-template](knowledge-vault.md#doc-4656beba355895)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/plugin](resident-skills.md#doc-709338d3e083eb)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)

#### [2026-11-02] ingest | UI 快照引用、发送确认证据与稳定失败码

来源：[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)

#### [2026-11-02] ingest | 投递细节白名单扩展的词条复核

来源：[raw/changes/2026-11-02-details-whitelist-reverify](delivery-pump.md#doc-ae7b71a2b37518)

[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-inbox](inbox.md#doc-6529d9966e604a)

#### [2026-11-02] ingest | 群聊提及先等候选面板，失败残留登记为可清理草稿

来源：[raw/changes/2026-11-02-mention-picker-gating-residue](wechat-ui.md#doc-980ea358badbe6)

[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)

#### [2026-11-02] ingest | 提及残留登记引发的来源复核

来源：[raw/changes/2026-11-02-mention-residue-reverify](wechat-ui.md#doc-989f2003dec3a1)

[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)、[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-inbox](inbox.md#doc-6529d9966e604a)
#### [2026-11-02] ingest | 管理台全局搜索增加清空按钮

来源：[raw/changes/2026-11-02-web-global-search-clear](dashboard.md#doc-5c4b4348a3410a)

[modules/web](dashboard.md#doc-aeec90dfe23cd3)

#### [2026-11-03] change | FEAT-VOICE-001 P1 虚拟麦语音条（可插 TTS / Right Alt）

来源：[raw/changes/2026-11-03-feat-voice-001-virtual-mic](delivery-voice.md#doc-3b7c8dcbc01ec2)

#### [2026-11-03] ingest | FEAT-VOICE-001 P1 虚拟麦语音条（可插 TTS / Right Alt）

来源：[raw/changes/2026-11-03-feat-voice-001-virtual-mic](delivery-voice.md#doc-3b7c8dcbc01ec2)

[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[modules/delivery](butler-functions.md#doc-f61f55fe09c5e9)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)

#### [2026-11-03] change | FEAT-VOICE-001 连带锚点刷新

来源：[raw/changes/2026-11-03-feat-voice-001-anchor-refresh](delivery-voice.md#doc-d313df34d8cc8b)

#### [2026-11-03] ingest | FEAT-VOICE-001 连带锚点刷新

来源：[raw/changes/2026-11-03-feat-voice-001-anchor-refresh](delivery-voice.md#doc-d313df34d8cc8b)

[symbols/model-worker](queue-worker.md#doc-0183b6974519f0)、[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)、[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-inbox](inbox.md#doc-6529d9966e604a)、[symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7)

#### [2026-11-03] change | FEAT-VOICE-003 音色资产与会话绑定

来源：[raw/changes/2026-11-03-feat-voice-003-voice-assets](delivery-voice.md#doc-a855357d83ac5d)

#### [2026-11-03] ingest | FEAT-VOICE-003 音色资产与会话绑定

来源：[raw/changes/2026-11-03-feat-voice-003-voice-assets](delivery-voice.md#doc-a855357d83ac5d)

[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)、[concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0)、[symbols/voice-asset-store](delivery-voice.md#doc-a41b10d5400ad9)

#### [2026-11-03] ingest | FEAT-VOICE-003 连带复核 model-worker 锚点

来源：[raw/changes/2026-11-03-feat-voice-003-model-worker-drift](delivery-voice.md#doc-2f6dcdc8d592e1)

[symbols/model-worker](queue-worker.md#doc-0183b6974519f0)

#### [2026-11-03] ingest | 音色资产页布局与状态打磨

来源：[raw/changes/2026-11-03-voice-assets-polish](delivery-voice.md#doc-5f445f7abfb4d8)

[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)

#### [2026-11-03] change | 统一当前开发基线、配置来源与发送实现文档

来源：[raw/changes/2026-11-03-development-doc-baseline](wxbot.md#doc-f9d149494a6267)

#### [2026-11-03] ingest | 统一当前开发基线、配置来源与发送实现文档

来源：[raw/changes/2026-11-03-development-doc-baseline](wxbot.md#doc-f9d149494a6267)

[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)

#### [2026-11-04] change | 统一主目录 main 与可编辑安装绑定

来源：[raw/changes/2026-11-04-root-workspace-unification](wxbot.md#doc-b44eb256c557c6)

#### [2026-11-04] ingest | 统一主目录 main 与可编辑安装绑定

来源：[raw/changes/2026-11-04-root-workspace-unification](wxbot.md#doc-b44eb256c557c6)

[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)

#### [2026-11-04] ingest | 网页预设文字转语音 Skill 与分段虚拟麦投递

来源：[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)

[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/common](wxbot.md#doc-dd2bd595b3d8f8)、[modules/delivery](butler-functions.md#doc-f61f55fe09c5e9)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/plugin](resident-skills.md#doc-709338d3e083eb)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)、[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-inbox](inbox.md#doc-6529d9966e604a)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)、[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)、[symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7)、[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)、[concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0)

#### [2026-11-04] change | 网页预设语音工具与一次授权实机验证

来源：[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)

手工创建记录补登记；28 个关联词条已完成源码/契约核对与入库。局部 22 项通过，较大范围回归保留 2 项既有失败；一次真实发送的个人运行数据不入图谱。


#### [2026-11-04] change | 联系人配置加入 IndexTTS 授权与语音设置

来源：[raw/changes/2026-11-04-contact-index-tts](index-tts.md#doc-cdb6f65d88730c)

#### [2026-11-04] ingest | 联系人配置加入 IndexTTS 授权与语音设置联动

来源：[raw/changes/2026-11-04-contact-index-tts](index-tts.md#doc-cdb6f65d88730c)

[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)


#### [2026-11-04] change | 网页音色预设列表与联系人默认绑定

来源：[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)

#### [2026-11-04] ingest | 网页音色预设列表与联系人默认绑定

来源：[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)

[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/delivery](butler-functions.md#doc-f61f55fe09c5e9)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/plugin](resident-skills.md#doc-709338d3e083eb)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)


#### [2026-11-04] change | 网页预设图谱契约说明补充

来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)

#### [2026-11-04] ingest | 网页预设图谱契约说明补充

来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)

[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/delivery](butler-functions.md#doc-f61f55fe09c5e9)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/plugin](resident-skills.md#doc-709338d3e083eb)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)

#### [2026-11-05] change | 修复联系人策略保存锁等待与不可见旧技能

来源：[raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)

#### [2026-11-05] ingest | 修复联系人策略保存锁等待与不可见旧技能

来源：[raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)

[apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)

#### [2026-11-05] change | 修复群聊越屏采集与自动语音回复链路

来源：[raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)

#### [2026-11-05] ingest | 修复群聊越屏采集与自动语音回复链路

来源：[raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)

[modules/delivery](butler-functions.md#doc-f61f55fe09c5e9)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7)、[symbols/model-worker](queue-worker.md#doc-0183b6974519f0)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)、[concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)、[concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)、[concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0)

#### [2026-11-05] ingest | 新消息补建联系人窗口与移除会话 IndexTTS 专区

来源：[raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)

[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)、[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)

#### [2026-11-05] ingest | 为停用的群成员身份增加启用按钮

来源：[raw/changes/2026-11-05-enable-group-binding](identity-tools.md#doc-6f2fac571f1610)

[apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)

#### [2026-11-05] ingest | 知识库按群汇总并标记来源

来源：[raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)

[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)

#### [2026-11-05] ingest | 知识库逐条删除事实

来源：[raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)

[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/butler](butler.md#doc-38393df7a7b4da)、[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)

#### [2026-11-05] change | 小潮常驻角色与空闲刷抖音

来源：[raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)

#### [2026-11-05] ingest | 小潮常驻角色与空闲刷抖音

来源：[raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)

[symbols/resident-role](resident.md#doc-81303bd5af31f1)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[modules/plugin](resident-skills.md#doc-709338d3e083eb)、[modules/butler](butler.md#doc-38393df7a7b4da)、[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)、[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)

#### [2026-11-05] change | 复核常驻角色的 README 来源

来源：[raw/changes/2026-11-05-resident-xiaochao-readme](resident.md#doc-3b5de0b90aca6b)

#### [2026-11-05] ingest | 复核常驻角色的 README 来源

来源：[raw/changes/2026-11-05-resident-xiaochao-readme](resident.md#doc-3b5de0b90aca6b)

[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)

#### [2026-11-05] change | 管理台查看小潮日记

来源：[raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)

#### [2026-11-06] ingest | 管理台查看小潮日记

来源：[raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)

[apis/dashboard-resident-diary](resident.md#doc-38ef2f5a72288d)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[symbols/resident-role](resident.md#doc-81303bd5af31f1)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)

#### [2026-11-06] change | 小潮有窗口模式与同页验证恢复

来源：[raw/changes/2026-11-06-resident-visible-edge](resident.md#doc-eb3bb4d27e3f68)

#### [2026-11-06] ingest | 小潮有窗口模式与同页验证恢复

来源：[raw/changes/2026-11-06-resident-visible-edge](resident.md#doc-eb3bb4d27e3f68)

[symbols/resident-role](resident.md#doc-81303bd5af31f1)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)

#### [2026-11-06] change | 修复小潮推荐流跳转到精选

来源：[raw/changes/2026-11-06-resident-recommend-navigation](resident.md#doc-b2141987114c61)

#### [2026-11-06] ingest | 修复小潮推荐流跳转到精选

来源：[raw/changes/2026-11-06-resident-recommend-navigation](resident.md#doc-b2141987114c61)

[symbols/resident-role](resident.md#doc-81303bd5af31f1)

#### [2026-11-07] ingest | 架构图节点 Markdown 文档

来源：[raw/changes/2026-11-07-architecture-node-notes](wxbot.md#doc-8790acdf96d310)

[concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)

#### [2026-11-07] ingest | 架构图节点文档使用说明与开发基线复核

来源：[raw/changes/2026-11-07-architecture-node-notes-readme](wxbot.md#doc-65d1db0ccb5dda)

[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)

#### [2026-11-07] ingest | 精简架构图底部区块

来源：[raw/changes/2026-11-07-architecture-diagram-trim](wxbot.md#doc-7574510a1cf96f)

[concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a)

#### [2026-11-07] change | 发件处理器按类型拆分，保留统一队列与投递契约

来源：[raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)

#### [2026-11-07] ingest | 发件处理器按类型拆分，保留统一队列与投递契约

来源：[raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)

[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a)、[concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)、[symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca)、[symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c)

#### [2026-11-07] change | 修正四项过期回归预期并补边界对照

来源：[raw/changes/2026-11-07-stale-regression-tests](wxbot.md#doc-df3c99eaa835f8)

#### [2026-11-07] ingest | 修正四项过期回归预期并补边界对照

来源：[raw/changes/2026-11-07-stale-regression-tests](wxbot.md#doc-df3c99eaa835f8)

[modules/plugin](resident-skills.md#doc-709338d3e083eb)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)

#### [2026-11-07] change | Archify 节点详情加入 Markdown 文档按钮

来源：[raw/changes/2026-11-07-archify-node-documents](wxbot.md#doc-1968450e794d2a)

#### [2026-11-07] ingest | Archify 节点详情加入 Markdown 文档按钮

来源：[raw/changes/2026-11-07-archify-node-documents](wxbot.md#doc-1968450e794d2a)

[concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a)、[concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)
<!-- end-migrated-part: doc-2359f8bc64950b -->

<a id="doc-6372a6d15b637a"></a>

### 架构图节点文档

来源：`llm wiki/wxbot/concepts/architecture-node-notes.md:1`。

```yaml
type: concept
module: wiki
summary: 根目录与 Archify 架构图按节点标识读写同一套 Markdown 文档
coverage: overview
last_verified: '2026-11-07'
sources:
- path: README.md
  line: 849
  anchor: '## 架构图节点文档'
- path: README.md
  line: 859
  anchor: 'Archify 版 [项目架构图]'
changes:
- raw/changes/2026-11-07-archify-node-documents
- raw/changes/2026-11-07-architecture-node-notes
- raw/changes/2026-11-07-architecture-diagram-trim
- raw/changes/2026-11-07-delivery-handlers
```
### 架构图节点文档

根目录的 `ARCHITECTURE.html` 是独立的本地页面。节点的 `data-component`
提供显示名称，`data-note` 是文件名键。当前图有 29 个节点入口；保留节点沿用原有文档键。

节点通过点击、Enter 或空格打开对话框，显示和编辑 Markdown 源文。
首次打开文档时，用 Edge 或 Chrome 选择含 `ARCHITECTURE.html` 的项目目录。
同一个页面会话内复用目录授权；第一次保存时在项目内创建 `architecture-notes/<键>.md`。
读取或写入失败时显示原因，保存前复查文件内容，避免覆盖已检测到的外部改动。

该目录保存架构笔记，不属于运行时日记、知识库或 [modules/wiki](wxbot.md#doc-ed5d88ddcd1b47) 的图谱证据。
本页不调用管理台、Butler、wxbot 或数据库。

图谱工具的来源白名单未包含根目录 HTML，因此使用 `README.md:849` 做自动锚点。
已手工核对 `ARCHITECTURE.html:79` 的节点键、`ARCHITECTURE.html:294` 的对话框、
`ARCHITECTURE.html:362` 的读取入口、`ARCHITECTURE.html:431` 的目录选择和
`ARCHITECTURE.html:464` 的文件写入流。

来源 [raw/changes/2026-11-07-architecture-node-notes](wxbot.md#doc-8790acdf96d310)、[raw/changes/2026-11-07-architecture-diagram-trim](wxbot.md#doc-7574510a1cf96f)。


#### 发件处理器节点

本次新增 delivery-pump、delivery-text、delivery-voice、delivery-image、delivery-emoji 五个文档入口，文件已创建。保留所有旧键；编辑器脚本未变。主链路仍展示目标架构，kind 与已实现处理器有明确标注，reply_type、前置 TTS 和文件发件保留为规划。


#### 发件职责拆分（2026-11-07）

统一调度见 [symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca)，文字、图片、语音、表情的准备和确认见 [symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c)。outbox 字段、语音授权、重试及流式契约保持原状，无迁移。

来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。


#### Archify 节点详情入口

独立页面 `.archify/architecture-wxbot-20261107-201947/wxbot.html` 保留原生节点详情、源码链接、关系与导出，在详情右侧加「文档」小按钮。按钮仅在单个节点选中时出现；多节点选择和关系详情不关联文档。

| Archify 节点 ID | 项目 architecture-notes 下的文件 |
|---|---|
| wechat | wechat-client.md |
| wxui | wechat-ui.md |
| queue | queue-storage.md |
| worker | queue-worker.md |
| butler | butler.md |
| backends | model-backends.md |
| authority | identity-tools.md |
| business | business-storage.md |
| vault | knowledge-vault.md |
| web / dashboard | dashboard.md |
| config | configuration.md |

复用原图的目录选择、原文预览、编辑和独占写入流程。目录必须包含根目录 `ARCHITECTURE.html`，而不是选择 HTML 所在的 `.archify` 子目录。同一页面会话复用授权，新文件只在明确保存时创建；预览使用 textContent。保存前重新读磁盘，发现改动或删除时保留草稿并拒绝覆盖；关闭和 Escape 保留未保存修改的确认。

编辑器挂在 `#focus-chip` 内，防止原生查看器在捕获阶段把编辑器点击识别成节点详情外点击；键盘事件不冒泡到查看器快捷键。关闭编辑器回到文档按钮。深浅主题复用查看器变量，原生 dialog 显式居中。

扩展源为同目录 `node-notes.extension.html`，`apply-node-notes.py` 幂等注入按钮与扩展，第一次执行保留 `wxbot.before-node-notes.html`。扩展不改节点、连接或生产功能，且不访问业务服务或数据库。原 Archify 回执仅验证扩展前字节；定制版本由 `node-notes.test.cjs` 使用内存句柄进行真实无头 Edge 验证，并记录当前 HTML 摘要至 `node-notes-verification.json`。

HTML 不在图谱来源白名单内，自动锚点为 `README.md:859`；手工核对 HTML 的按钮 `:5673`、文件读取 `:15145`、映射/选中判断 `:15087` / `:15171`、弹窗挂载 `:15210`、保存 `:15249`。源码分片的映射、弹窗与保存分别在 `node-notes.extension.html:73`、`:196`、`:235`。

来源 [raw/changes/2026-11-07-archify-node-documents](wxbot.md#doc-1968450e794d2a)；项目图谱与浏览器笔记仍分开维护，见 [modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)。
<!-- end-migrated-part: doc-6372a6d15b637a -->

<a id="doc-f0b302749d6eb3"></a>

### 开发基线与历史布局

来源：`llm wiki/wxbot/concepts/development-baseline.md:1`。

```yaml
type: concept
module: wiki
summary: 按实际工作树与解释器确定开发基线，区分当前配置、生产模型链路与历史布局
coverage: overview
last_verified: '2026-11-07'
sources:
- path: README.md
  line: 125
  anchor: '## 开发基线与历史布局'
- path: README.md
  line: 597
  anchor: '## 配置'
- path: README.md
  line: 849
  anchor: '## 架构图节点文档'
- path: pyproject.toml
  line: 1
  anchor: '[project]'
- path: src/butler/defaults.py
  line: 4
  anchor: 'def butler_defaults():'
- path: src/butler/defaults.py
  line: 13
  anchor: 'def wxbot_defaults():'
- path: src/wxbot/config.py
  line: 110
  anchor: def load_config(
- path: src/wxbot/main.py
  line: 29
  anchor: def build_processor(
- path: src/wxbot/wechat/typing.py
  line: 178
  anchor: ClipboardLease(self.chunks[self.index])
- path: src/wxbot/wechat/typing.py
  line: 201
  anchor: auto.SendKeys('{Ctrl}v'
- path: src/dashboard/http.py
  line: 88
  anchor: WEBAPP_DIR = os.path.join(str(REPO_ROOT), 'web', 'dist')
- path: src/wxbot/config.py
  line: 43
  anchor: chunk_interval = typing.get(
changes:
- raw/changes/2026-11-07-archify-node-documents
- raw/changes/2026-11-03-development-doc-baseline
- raw/changes/2026-11-04-root-workspace-unification
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-policy-save
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
- raw/changes/2026-11-05-resident-diary-web
- raw/changes/2026-11-06-resident-visible-edge
- raw/changes/2026-11-07-architecture-node-notes-readme
- raw/changes/2026-11-07-delivery-handlers
- raw/changes/2026-11-07-stale-regression-tests
```
### 开发基线与历史布局

#### 术语与状态含义

基线由工作目录、Git 分支、HEAD SHA、未提交修改及解释器实际导入的代码共同确定。
`main`、正式运行目录和开发 worktree 可以处于不同进度；分支名或“曾经同 SHA”不能证明当前内容相同。
当前代码与运行进程已加载的版本也不是同一件事（`README.md:125` 开始的核对流程）。
若 `.venv` 的可编辑安装指向另一工作树，必须先识别差异，不能把另一份代码的通过结果当作本轮证据。

#### 业务规则与边界

- 配置来自 `src/butler/defaults.py:4` / `:13` 等无凭据默认值，经安装向导生成；当前仓库没有独立示例 TOML。
  实际名字是 `config.butler.toml`、`config.wxbot.toml`、`config.log.toml`（`README.md:597`）。
- Python 依赖以 `pyproject.toml:1` 的声明和 uv.lock 精确版本为准；requirements.txt 是兼容 pip 清单，不能据旧注释断言 Butler 无第三方依赖。
- 生产默认 wxbot→Butler→模型；Butler 自身的 Hermes、OpenAI 兼容 API 等 provider 是正常接入方式。
  wxbot 的直接适配器属于旁路调试／旧配置兼容；带 installation 配置时禁止非 butler backend（`src/wxbot/main.py:29`）。
- 正文发送使用 `ClipboardLease` 后执行 Ctrl+V，再读回校验；控制键仍由 UI 自动化执行（`src/wxbot/wechat/typing.py:178`、`:201`）。
  默认分批间隔为 0.25 秒；full/chunked/streaming 均使用粘贴，见 `README.md:597` 后的发送章节与 `src/butler/defaults.py:13`。

#### 跨层映射

[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05) 负责配置生成，[modules/models](model-backends.md#doc-69928b2a06b8f9) 定义 Butler 的模型后端，[modules/wxbot](wxbot.md#doc-8508032cbe5131) 持有正文粘贴与发送确认。
[modules/web](dashboard.md#doc-aeec90dfe23cd3) 的产物由 `src/dashboard/http.py:88` 的 WEBAPP_DIR 在 /app/ 提供，不由已退场的 log/server.py 提供。
[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47) 的 CLI 支持 `--repo-root` 显式限定开发图谱范围，不授予运行时身份或操作权限。
本次没有 API/DTO、数据库字段／迁移或异步任务变更。

#### 历史坑与冲突

旧 butler/README.md、PROJECT_MEMORY.md、kmg/、hermes_butler、固定安装路径和嵌套包名不再代表当前 src/ 布局。
它们在本轮工作分支中已不存在，不能重建旧入口来满足过期说明。根 heartbeat/ 仍含受版本控制的辅助看门狗脚本，
与 src/butler/runtime/heartbeat.py 的业务心跳分开；不把整个目录忽略或删除（`README.md:125`）。
2026-11-03 的文档核对仅用显式 --repo-root 限定图谱范围，当时没有修复可编辑安装。
2026-11-04 按用户要求由主目录接管最新 main，并在主目录自己的 .venv 中离线重装本项目；
随后从仓库外以隔离模式验证四个包及 REPO_ROOT 均来自主目录 src/。
这是开发环境绑定的核验，不证明现有进程已重新加载代码；本次未启动或重启服务。
另一个 worktree 及其独立配置、数据仍保留，不能把代码目录统一当成数据库或认证迁移。

#### 相关模块、接口、测试

关联 [modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[modules/models](model-backends.md#doc-69928b2a06b8f9)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)。
使用静态语义等价检查确认 Python 执行 AST、Vite 执行配置、依赖项和锁文件未变；前端构建写入临时目录并运行既有假数据冒烟。
没有新增测试；本次不改变 UI 行为、真实配置、凭据或运行数据，也不启动／重启服务。

#### 代码依据与修改来源

来源与锚点见本页 sources；完整核对范围、八项问题的实际处置和验证记录见
[impacts/2026-11-03-development-doc-baseline](wxbot.md#doc-6981deab6390ae) 与 [raw/changes/2026-11-03-development-doc-baseline](wxbot.md#doc-f9d149494a6267)。

环境绑定后续处理见 [impacts/2026-11-04-root-workspace-unification](wxbot.md#doc-1002b3869f9b4f) 与
[raw/changes/2026-11-04-root-workspace-unification](wxbot.md#doc-b44eb256c557c6)；历史 raw 保持原样。


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 联系人语音配置核对

[raw/changes/2026-11-04-contact-index-tts](index-tts.md#doc-cdb6f65d88730c)：新增会话授权控件与原接口消费，源码位置已核对；后端契约保持。


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。


#### 策略保存复核（2026-11-05）

本次 src/dashboard/http.py 仅细化未知技能校验错误；WEBAPP_DIR、/app/ 静态文件来源与安装基线规则未改。保存锁等待修复见 [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)。来源 [raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)。


#### 群聊采集与自动语音复核（2026-11-05）

README 追加自动语音真实 WebUI 默认、配置热读和窗口越屏恢复说明；安装路径、静态文件位置及图谱 CLI 合同不变。功能依据见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)、[concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66)。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。

#### 本次核对

README 补充联系人建档与 IndexTTS 界面路径，解释器、运行与配置基线沿用。 来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 本次核对

README 增补事实删除操作及接口，开发基线沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

`pyproject.toml` 的 `resident` 可选依赖为 Playwright，开启 [symbols/resident-role](resident.md#doc-81303bd5af31f1) 前按 README 安装。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。

#### 小潮日记接入核对

README 的小潮常驻角色章节补充了本机管理台入口，构建、安装和开发基线规则继续沿用。 来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。

README 补充了小潮的有窗口运行方式和验证等待步骤。来源 [raw/changes/2026-11-06-resident-visible-edge](resident.md#doc-eb3bb4d27e3f68)。

README 末尾补充了独立架构图的节点文档入口。原开发基线和配置章节的锚点仍分别位于第 125 和 596 行。
文档权限和文件映射见 [concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a)。来源 [raw/changes/2026-11-07-architecture-node-notes-readme](wxbot.md#doc-65d1db0ccb5dda)。


#### 发件拆分文档复核

README 的 wxbot 文件职责新增 delivery_handlers，架构章节记录第一步与后续规划的界限；配置、安装和图谱维护流程未变。

来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。


#### 输入时序回归基线

缺省 chunk_interval 为 0.25 秒；显式 0.5 秒仍受支持。本地输入回归分别使用缺省/显式配置，验证到期前不提前粘贴、到期后完整粘贴、仅一次回车及剪贴板恢复。本次不修改输入逻辑或默认配置。

来源 [raw/changes/2026-11-07-stale-regression-tests](wxbot.md#doc-df3c99eaa835f8)。


#### Archify 本地扩展的基线

README 仅在架构图节点文档章节追加 Archify 文档按钮用法，原配置、运行与开发基线段落及来源锚点保持原位。独立 Archify 图仍按提交 `20fc624bcf09e221079edd498fac85a5f2c1404f` 展示已提交核心结构，本次未更新业务架构；定制查看器的浏览器回执与原生成回执分别记录。来源 [raw/changes/2026-11-07-archify-node-documents](wxbot.md#doc-1968450e794d2a)；详情见 [concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a)。
<!-- end-migrated-part: doc-f0b302749d6eb3 -->

<a id="doc-6cbfc97cc45d15"></a>

### 消息主链路与字段传递

来源：`llm wiki/wxbot/concepts/message-pipeline.md:1`。

```yaml
type: concept
module: wxbot
summary: 窗口→收件→批次→Butler→分句→UI→只读投影
coverage: core
last_verified: '2026-11-07'
sources:
- path: src/wxbot/inbox.py
  line: 264
  anchor: def _capture(
- path: src/wxbot/queue_worker.py
  line: 152
  anchor: reply = self.router.handle_reply(
- path: src/wxbot/processor/butler.py
  line: 72
  anchor: body["msg_id"] = request_id
- path: src/butler/agent/core.py
  line: 312
  anchor: result.meta["msg_id"] = msg_id
- path: src/wxbot/wechat/chat_window.py
  line: 37
  anchor: 'ref: str = '''''
- path: src/wxbot/ui_contract.py
  line: 56
  anchor: def persisted_rows(
changes:
- raw/changes/2026-11-03-indextts-enqueue-media
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-03-feat-voice-001-virtual-mic
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch-core-emit
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-10-31-identity-placeholder-names
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-residue-reverify
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-07-delivery-handlers
```
### 消息主链路与字段传递

#### 路径

[modules/wxbot](wxbot.md#doc-8508032cbe5131) MainInbox → [tables/queue-inbox](inbox.md#doc-6529d9966e604a) → prepare 生成 [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a) → [symbols/model-worker](queue-worker.md#doc-0183b6974519f0) → Router → [symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24) → [apis/butler-handle](butler.md#doc-4f70359e7ae440) / [apis/butler-handle-stream](butler.md#doc-5135f5350303bc) → [symbols/butler-handle](butler.md#doc-eba67ca6f97d80) / [symbols/butler-result](butler.md#doc-a9181bbf2979fd) → [symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1) → [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf) → UI 发件器。

正常入站处理和群归档也会调用 [modules/identity](identity-tools.md#doc-5e308350a1ba25) 的窗口补建，先于模型生成；因此群聊静默归档也能登记窗口。历史快照登记仍只收集身份观测。详见 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 字段血缘与契约

- contact：UI 窗口标题 → inbox/batches → 请求 contact → 会话解析；不是微信账号/人物显示名。
- batches.id → worker.request_id → HTTP msg_id → Butler trace / meta.msg_id；decoder 可核对回包 ID，管理台按 request_id 关联。
- member_key/member_name/avatar：观察数据 → 批次/请求；服务端解析确认后返回 mention_name，第一分句才携带 @ 目标。见 [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。
- Result.reply / reply_parts → wxbot Reply → outbox.text/part_seq；reply_complete 与投递 state 不同，见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。
- 快照引用只在一次界面读取内有效：`Message.ref` 不落库，`observations.snapshot` 与 `outbox.baseline` 都保存去引用版本；重启后只能按正文对齐，不能当跨进程指针用。

#### 反向消费

[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714) 和 [apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f) 只读队列/事件，再由 [modules/web](dashboard.md#doc-aeec90dfe23cd3) 展示。浏览器不直接访问 Butler 处理端点。主动推送会绕过收件/模型链路并允许 outbox.batch_id=NULL，不应强行补造批次。

模型来源在流转日志里按接入方式展示（deepseek 而不是 openai），字段仍走既有 trace，不新增队列列。

另有旁路支线：[symbols/butler-handle](butler.md#doc-eba67ca6f97d80) 的 `_record_episode`（`src/butler/agent/core.py:326`）在请求返回前把本轮用户原文与回复写进 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)（`cfg.data_path()/'knowledge'` 下，一人一个 vault，落到 `p-<slug>/vault/对话/YYYY-MM-DD.md`，与队列库无关）。它只读不写队列状态，失败不影响主链路；写入同时还重画该 vault 的 `index.md` 中心索引页（同一轮多一次文件写）。管理台侧的只读消费见 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)。

#### 代码依据

- `src/butler/agent/core.py:326` — `def _record_episode(self, c, contact_name, channel_type, text, reply, outcome):`
- `src/butler/agent/core.py:332` — `self.knowledge.record(`
- `src/wxbot/inbox.py:264` — `def _capture(`
- `src/wxbot/queue_worker.py:152` — `reply = self.router.handle_reply(`
- `src/wxbot/processor/butler.py:72` — `body["msg_id"] = request_id`
- `src/butler/agent/core.py:312` — `result.meta["msg_id"] = msg_id`
- `src/wxbot/wechat/chat_window.py:37` — `ref: str = ''`
- `src/wxbot/ui_contract.py:56` — `def persisted_rows(`

`queue_worker.py` 的 `handle_reply` 锚点因同文件增加导入下移一行。入队语音路径见 [raw/changes/2026-11-03-indextts-enqueue-media](index-tts.md#doc-29fc2d893f2889)。

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-10-31-model-access-switch-core-emit](model-backends.md#doc-6510cadeadeb37)

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-mention-residue-reverify](wechat-ui.md#doc-989f2003dec3a1)

#### 变更

- 2026-11-03: FEAT-VOICE-001 P1 outbox kind=voice（虚拟麦+RALT）；见 [raw/changes/2026-11-03-feat-voice-001-virtual-mic](delivery-voice.md#doc-3b7c8dcbc01ec2)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 群聊采集与自动语音复核（2026-11-05）

采集前的越屏恢复和 row_offscreen 显式拒绝见 [concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66)；不放宽 gutter 阈值，不推进未知发送方快照。语音准备期间继续采集，恢复录音任务后本轮不再切换收件会话，见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。


#### 发件处理器拆分

[symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca) 保留统一 outbox 认领与 UI 所有权，按 kind 调用 [symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c)。同会话顺序仍由 claim_delivery 的 seq/未终结前项约束保证，数据字段和 HTTP 不变。

来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。
<!-- end-migrated-part: doc-6cbfc97cc45d15 -->

<a id="doc-3d945de7c38143"></a>

### 建档覆盖范围

来源：`llm wiki/wxbot/coverage.md:1`。

### 建档覆盖范围

首批建档日期：2026-10-31。基于当时**当前工作树**，其中包含用户已有未提交修改；这里只描述核对过的结构，不编造这些改动的历史验证结果。

#### 已建档

- Archify 节点详情中的「文档」按钮，复用根目录 Markdown 笔记、目录授权和安全保存，见 [concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a)。

- 统一发件调度及四类处理器，见 [symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca)、[symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c)；仍共用 outbox，无新队列表或 reply_type。

- 根目录架构图的可点击节点、Markdown 文件映射和浏览器目录授权，见 [concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a)。

- 小潮日记在管理台的只读文件投影、分页和文本安全边界，见 [apis/dashboard-resident-diary](resident.md#doc-38ef2f5a72288d)。

- 小潮常驻角色的聊天空闲信号、浏览器适配、额度和本机日记，见 [symbols/resident-role](resident.md#doc-81303bd5af31f1)。

- 知识库单条事实删除、鉴权和 Markdown 派生索引，见 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)。

- 知识库群聊汇总、分页前筛选与来源标识，见 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)。存量事实只有节点级会话归属。

- 网页预设后端列表与默认绑定、可选工具音色参数、修订冲突与原子 JSON 配置，见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。会话页面只管理语音模式与本地音色，AI 设置管理技能授权，见 [modules/web](dashboard.md#doc-aeec90dfe23cd3)。

- 新消息补建联系人窗口的入口、唯一窗口名、私聊绑定与已有停用状态，见 [modules/identity](identity-tools.md#doc-5e308350a1ba25)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)。

- 网页音色预设工具、同会话 Gradio 队列、分段标准 WAV、鉴权音频编号、语音包入队/发送状态及原自动音色绑定例外，见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。

- 音色页单内容区、加载/空/失败/有数据展示、字段血缘与响应式约束，见 [modules/web](dashboard.md#doc-aeec90dfe23cd3)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)；后端契约保持不变。

- 开发工作树与解释器基线、现行配置与依赖来源、生产后端与旁路的层级、历史布局边界，见 [concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)；不记录真实配置或运行进程状态。
- 主要模块职责、入口、依赖和边界，见 [index](wxbot.md#doc-6e5a10e80a7955) 的 modules。
- 消息处理：[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)，含请求/响应字段、wxbot 调用方。
- 最终队列结构：[tables/queue-inbox](inbox.md#doc-6529d9966e604a)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)，结合建表及补列阅读。
- 核心符号/显式调用关系、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。
- 管理台读队列接口及 Vue 消费点：[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)。
- 统一模型链路、请求代际热切换和原生工具边界：[modules/models](model-backends.md#doc-69928b2a06b8f9)、[symbols/reloadable-backend](model-backends.md#doc-85aba8d0cc88bd)、[symbols/local-model-backend](model-backends.md#doc-058aec74f1727e)。
- 模型失败的跨层契约（脱敏、`retry_safe` 来源、自动重试上限、超时放行）：[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)。
- 群提及的两段验证与回退清理链（含 uiautomation 特殊键名约束）：[symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7)。
- 未读采集的重试退避、放弃出口及与 `pending_sessions`／`prepare` 的关系：[concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)。
- 用户知识库的 vault 存储形态、文件格式、迁移路径：[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)；提炼链路 [symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、调度与游标 [symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)；管理台只读投影：[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)。三张 `kb_*` 平表已退场，留档页保留迁移说明。

#### 待扩展

- 联系人完整业务表、身份合并端点/血缘，目前只有 [modules/identity](identity-tools.md#doc-5e308350a1ba25) 概览。
- 提醒/心跳、媒体/新闻、Telegram Bot/桌面中继的详细表与端点。
- 安装配置与其余前端页面。
- 单个后端各自的失败细节（Codex 提交边界、Cursor 工作目录、Ollama 完整判据）尚未逐项建页，目前只在 [concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6) 里写了公共部分。
- 未为每个文件/函数建页；调用关系只声明已核对的关键边，不声称静态分析覆盖全部。
- `tests/` 仅在开发机存在且不入 Git；测试路径作导航，不作为跨安装可用的证据。巡检不读取真实数据。

改到缺口时按 [guide](wxbot.md#doc-9cf47fd939c877) 先查源码、扩展词条，再更新本清单。不能从模块概览推断字段，也不能把“未命中”当成“不存在”。
<!-- end-migrated-part: doc-3d945de7c38143 -->

<a id="doc-ba7d4d46f1c73f"></a>

### 项目知识图谱实施方案

来源：`llm wiki/wxbot/design.md:1`。

### 项目知识图谱实施方案

目标：落实用户提供的 Markdown 项目知识图谱方案，让开发模型改前查图、改后写修改记录并入库。

采用已有的 `llm wiki/wxbot/` Obsidian 库；图谱与代码一起由项目 Git 管理，不初始化嵌套 Git 仓库。保留已有 `.obsidian` 配置。README 继续承载项目操作说明，图谱承载可追溯的结构事实。

方案比较：纯 Markdown 容易开始但难以发现漂移；Markdown 加本地检查命令能校验台账和来源；独立图数据库或向量服务需要额外运维。这里采用第二种，使用项目已有 Python 和 PyYAML，不接模型 API、不增加运行服务。

#### 结构与边界

- `modules/ apis/ tables/ symbols/ concepts/ impacts/`：带 YAML 元信息、代码位置、双链与修改来源的词条。
- `raw/changes/`：只追加修改记录；更正写新记录并指向旧记录，不改历史事实源。
- `templates/`：各类词条、影响分析和修改记录模板。
- `index.md changelog.md ingest-state.json`：目录、追加日志和入库证据快照。
- `scripts/wiki.py`：query / change / ingest / lint / status；查询按关键词命中并展开双向一至两跳。只有显式保存查询时写影响报告和日志。

自动检查覆盖断链、元信息、来源路径/行号/锚点、来源内容漂移、词条未入库、raw 篡改或漏入库、调用关系反向声明、显式模块依赖环。工具不能证明语义正确，契约/字段血缘/业务冲突由模型逐项核对并写在报告中。

首版提供主要模块地图，完整建档消息处理链路：Butler handle/stream、队列 inbox/batches/outbox、核心处理符号、管理台消费点和投递状态概念。其余模块标为概览，不宣称全库已完整建档。事实只来自当前工作树源码，不读取认证、运行时配置、数据库或消息正文。

#### 验收与风险

临时目录测试命中及双向展开、路径边界、断链/漂移、未入库记录、raw 不可覆写、入库幂等及无副作用失败；在真实图谱执行查询与 lint。来源按完整文件内容摘要检测，文件中无关行变化也可能要求复核。行号加锚点用于发现移动；模型核对后通过新修改记录更新。

本次只落地开发知识流程，不修改业务协议，不重启服务，不发微信，不发布或提交。已有未提交源码按当前快照建档，不能据此推断历史改动作者和验证结果。
<!-- end-migrated-part: doc-ba7d4d46f1c73f -->

<a id="doc-9cf47fd939c877"></a>

### 查图与维护

来源：`llm wiki/wxbot/guide.md:1`。

### 查图与维护

用 Obsidian 打开本目录 `llm wiki/wxbot/`，从 [index](wxbot.md#doc-6e5a10e80a7955) 开始；关系图使用 `[[目录/词条]]` 双链。沿用已有 `.obsidian` 配置，与代码一起由项目 Git 管理，不初始化嵌套仓库。

代码是事实源，图谱保存经模型核对的结构知识，raw 修改记录保存每次入库的依据。项目操作说明仍以根 README.md 为准。

#### 改前查询

在项目根使用已有虚拟环境：

```powershell
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" status
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" query reply_complete /v1/handle --depth 1
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" query outbox --depth 2 --save outbox-review
```

`query` 对文件名、简介和正文做关键词匹配，多个关键词按任一命中排序；`--limit` 限制初始命中，随后展开双向关联。默认只读；`--save` 创建当天的 draft 影响报告、刷新索引并追加 query 日志，文件存在则拒绝覆写。它提供候选和提纲，**不会自动得出完整影响结论**。

读词条并核对当前代码，报告要改的位置、调用方、前后端字段契约、数据库血缘、测试/异步任务、风险和回滚。未覆盖部分先查源码并建档，明确记录缺口。跨模块或高风险报告保存在 `impacts/`。已明确授权的任务按范围继续；用户要求先确认或范围尚未授权时等待确认。

#### 改后记录与入库

```powershell
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" change handle-contract --title "调整消息处理契约"
# 填完新建的 raw/changes/YYYY-MM-DD-handle-contract.md，核对 diff/源码并更新词条
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" ingest YYYY-MM-DD-handle-contract
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" lint
```

1. 修改记录填写七项事实；不涉及的项目明确写“不涉及”和原因。
2. 在 raw 元信息的 `pages` 列出全部本次核对的词条 ID，如 `apis/butler-handle`，相对库根、不含扩展名。
3. **模型**读代码/diff，整合模块职责、API 字段、表结构/字段血缘、符号调用和副作用；修正行号/锚点，更新 `last_verified`、反向关系，在词条 `changes` 追加本条 raw ID，正文也链接该记录。
4. `ingest` 仅为记录所列词条登记来源快照，刷新 [index](wxbot.md#doc-6e5a10e80a7955)，追加 [changelog](wxbot.md#doc-2359f8bc64950b)；不调用模型生成内容、不改源码，不能替代第 3 步。
5. 执行全图 `lint`，评审代码、raw、词条、索引、日志、`ingest-state.json`。`ingest` 的 OK 不代表全图已通过巡检。

`change` 创建骨架时追加 change 日志；手写 raw 时由模型追加同格式日志。查询、巡检默认只读；需要归档巡检时由模型保存待办并追加 lint 日志。

#### 追加历史与冲突

raw 命名 `YYYY-MM-DD-短主题.md`；raw 与 changelog 只追加。已入库 raw 与代码冲突时，以代码为准，**新增更正记录**，在 `supersedes` 写旧记录 ID，正文列出旧结论、新结论和证据，再更新词条入库。这解决原方案“只追加”和“回写修正”的矛盾，禁止手改快照绕过 raw 保护。

新旧事实有冲突时在词条“冲突与待确认”中说明依据；不静默覆盖。多条 raw 按日期及依赖顺序逐条入库。重命名/删除词条须先修复引用，写迁移记录；当前工具报 `page-missing`，不会自动清除历史状态。

#### 巡检边界

机器检查元信息、断链、来源文件/行号/锚点、完整文件摘要漂移、词条未入库、raw 改写/丢失/漏入库、显式 `calls/called_by` 对称、`depends_on` 依赖环及孤立词条。只允许公开源码、示例配置和开发文档，不读取认证、运行时配置、数据库、data/cache。

来源摘要统一 CRLF/LF，按完整文件计算，因此文件中无关改动也会触发 `source-drift`。模型须复核后写新记录，不能直接更新摘要消除提示。`anchor` 必须是来源指定行的非空原文片段，用于发现移动。

语义巡检由模型检查：接口与前端契约、迁移后的最终表结构、字段跨层含义、调用方遗漏、重要符号缺页、重复字段/逻辑、业务规则过时及测试覆盖。**机械 lint 不能证明这些结论。**

#### 格式

同一时间只由一个开发者/模型写入图谱。入库必须保留词条的历史 `changes`；来源与词条路径均拒绝符号链接/目录联接重定向，防止从源码名或 Markdown 别名读到私有文件。

用小写英文短名和稳定目录 ID；中文写标题/正文。模板见 `templates/`。YAML 的 `sources` 为 `{path, line, anchor}` 列表，path 相对项目根；`changes` 为相对库根的 raw ID 列表。概览标 `coverage: overview`，核心链路标 `coverage: core`。新增词条与所属模块互相链接。

代码位置显示为 `src/.../file.py:123`，编辑器按位置打开；Obsidian 代码跳转可另配插件。禁止 Token、真实联系人、聊天正文、生产数据入库。个人 Obsidian 工作区/缓存不入 Git。
<!-- end-migrated-part: doc-9cf47fd939c877 -->

<a id="doc-6e5a10e80a7955"></a>

### 项目知识图谱

来源：`llm wiki/wxbot/index.md:1`。

### 项目知识图谱

先读 [guide](wxbot.md#doc-9cf47fd939c877)；覆盖范围见 [coverage](wxbot.md#doc-3d945de7c38143)。代码是事实源，词条是经过核对的导航。

#### modules / module

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [modules/butler](butler.md#doc-38393df7a7b4da) | 身份、权限、模型编排和业务工具的服务边界 | `src/butler/server.py:52` | 2026-11-05 |
| [modules/common](wxbot.md#doc-dd2bd595b3d8f8) | 仓库根、事件追踪、流和 wire schema 的跨包纯基础层 | `src/common/paths.py:29` | 2026-11-04 |
| [modules/dashboard](dashboard.md#doc-bb47c9474691fe) | 聚合运行事实，读取队列不初始化或迁移数据库 | `src/dashboard/api/tts_presets.py:6` | 2026-11-06 |
| [modules/delivery](butler-functions.md#doc-f61f55fe09c5e9) | 主动推送、补发、媒体与提醒归业务服务所有 | `src/butler/delivery/tts_presets.py:12` | 2026-11-05 |
| [modules/identity](identity-tools.md#doc-5e308350a1ba25) | 统一人物、窗口和成员绑定，身份能力由服务端签发 | `src/butler/identity/user_registry.py:350` | 2026-11-05 |
| [modules/models](model-backends.md#doc-69928b2a06b8f9) | Butler 管理可切换模型与服务授权工具，wxbot 只调用 Butler | `src/butler/backends/__init__.py:12` | 2026-11-01 |
| [modules/plugin](resident-skills.md#doc-709338d3e083eb) | 角色和工具 Skill 分类，权限仍由业务服务验证 | `src/butler/agent/tools.py:24` | 2026-11-07 |
| [modules/runtime](butler-functions.md#doc-241e7c8bdd1c05) | 安装、迁移、并发、MCP 与知识库提炼调度等运行基础设施 | `src/butler/runtime/setup.py:28` | 2026-11-05 |
| [modules/telegram](butler-functions.md#doc-8b0e2206d40805) | Telethon、Bot API 和桌面中继三个不同边界 | `src/butler/channels/telegram/bot/queue.py:9` | 2026-11-01 |
| [modules/web](dashboard.md#doc-aeec90dfe23cd3) | 共享导航壳和现有请求封装的管理界面 | `web/src/styles/voice-assets.css:7` | 2026-11-06 |
| [modules/wiki](wxbot.md#doc-ed5d88ddcd1b47) | 本地关键词检索、证据入库和一致性巡检 | `AGENTS.md:36` | 2026-11-07 |
| [modules/wxbot](wxbot.md#doc-8508032cbe5131) | 微信 UI 主线程与不接触 UI 的模型队列线程 | `src/wxbot/voice/assets.py:80` | 2026-11-07 |

#### apis / api

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [apis/butler-handle](butler.md#doc-4f70359e7ae440) | 同步消息处理契约，从 wxbot 批次到完整 Butler 回复 | `src/butler/server.py:392` | 2026-11-05 |
| [apis/butler-handle-stream](butler.md#doc-5135f5350303bc) | SSE 增量观察与最终 result，断流不能当完整结果 | `src/butler/server.py:413` | 2026-11-05 |
| [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc) | 联系人策略事务外校验、并发版本复查及未安装技能显式取消 | `src/butler/identity/contact_admin.py:345` | 2026-11-05 |
| [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6) | 对话原文与知识图谱事实的只读查询、自动提炼的状态与手动触发转发，以及知识模板的读取与校验保存；vault 不存在时返回空态而不是错误 | `src/dashboard/routes.py:48` | 2026-11-06 |
| [apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f) | 队列分页诊断，展示状态和可用动作而不执行恢复 | `src/dashboard/routes.py:47` | 2026-11-06 |
| [apis/dashboard-resident-diary](resident.md#doc-38ef2f5a72288d) | 从 Butler 数据目录只读分页展示小潮日记和已核对的作品链接 | `src/dashboard/api/resident_diary.py:38` | 2026-11-06 |
| [apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521) | 音色资产 CRUD、参考音预览与会话 contact_refs 绑定 | `web/src/styles/voice-assets.css:7` | 2026-11-06 |
| [apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714) | 队列与 Telegram 工作流只读聚合及前端消费 | `src/dashboard/routes.py:44` | 2026-11-06 |
| [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) | 授权文字与网页音色预设生成分段语音，经虚拟麦和 RALT 投递当前会话 | `src/butler/delivery/tts_presets.py:12` | 2026-11-07 |

#### tables / table

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20) | 已退场——SQLite 时代的 L1 原文表，现由 vault 里的「对话/YYYY-MM-DD.md」承担，只保留迁移读入口 | `src/butler/runtime/knowledge_store.py:48` | 2026-11-05 |
| [tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e) | 已退场——L2 事实表被 vault 里的「人物/组织/话题」节点 Markdown 取代，只保留迁移读入口 | `src/butler/runtime/knowledge_store.py:50` | 2026-11-05 |
| [tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb) | 已退场——owner 目录与提炼游标改为可重建的 index.json，SQLite 索引库只在迁移时被改名留底 | `src/butler/runtime/knowledge_store.py:331` | 2026-11-05 |
| [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) | 用户知识图谱的存储形态——一人一个 Obsidian vault，目录骨架、事实分类与索引分区由 Markdown 模板决定 | `src/butler/runtime/knowledge_store.py:1` | 2026-11-06 |
| [tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a) | 模型请求批次与最终回复完整性，非发送回执 | `src/wxbot/queue_schema.py:34` | 2026-11-04 |
| [tables/queue-inbox](inbox.md#doc-6529d9966e604a) | 原始收件与群成员证据，batch_id 指向合并批次 | `src/wxbot/queue_schema.py:34` | 2026-11-04 |
| [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf) | 逐分句发件与不确定结果审计，包含迁移新增字段 | `src/wxbot/queue_schema.py:34` | 2026-11-07 |

#### symbols / symbol

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [symbols/butler-handle](butler.md#doc-eba67ca6f97d80) | 单轮身份解析、会话互斥、补发优先与最终合成 | `src/butler/agent/core.py:219` | 2026-11-05 |
| [symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24) | wxbot 的 Butler HTTP 适配及完整结果校验 | `src/wxbot/processor/butler.py:60` | 2026-10-31 |
| [symbols/butler-result](butler.md#doc-a9181bbf2979fd) | 生成 reply/actions/reply_parts/meta 的公开边界 | `src/butler/agent/core.py:68` | 2026-11-05 |
| [symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c) | 文字、语音、图片、表情独立发送处理器及共用气泡保护 | `src/wxbot/delivery_handlers/__init__.py:8` | 2026-11-07 |
| [symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca) | 一张 outbox 的统一 UI 调度、类型分派、状态与回执 | `src/wxbot/delivery.py:15` | 2026-11-07 |
| [symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) | Butler 进程内的定时提炼调度器，一轮只喂模型一批，并与 CLI 共用跨进程单飞锁 | `src/butler/runtime/knowledge_auto.py:29` | 2026-11-05 |
| [symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774) | 从对话原文提炼知识图谱节点的链路，模板决定分类、节点类型与追加规则，CLI 与进程内调度器共用，游标只在整批成功后前移 | `src/butler/runtime/knowledge_extract.py:25` | 2026-11-05 |
| [symbols/knowledge-template](knowledge-vault.md#doc-4656beba355895) | 知识图谱模板的解析与加载——一份 Markdown 决定节点目录、事实分类、索引分区与提炼规则，覆盖层优先，坏模板回退内置 | `src/butler/runtime/knowledge_template.py:28` | 2026-11-02 |
| [symbols/local-model-backend](model-backends.md#doc-058aec74f1727e) | 原生函数工具走服务签发身份，完整结果才进入历史 | `src/butler/backends/models.py:16` | 2026-11-01 |
| [symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7) | UI 线程内的 @ 提及选择器，先等候选面板再输入昵称，失败时只清理并登记自己输入的字面前缀 | `src/wxbot/wechat/mentions.py:67` | 2026-11-05 |
| [symbols/model-worker](queue-worker.md#doc-0183b6974519f0) | 领取批次、调用模型并保存回复，绝不访问 UI | `src/wxbot/queue_worker.py:46` | 2026-11-05 |
| [symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1) | 完整分句入 outbox，模型完成和发送完成分开 | `src/wxbot/queue_store.py:339` | 2026-11-04 |
| [symbols/queue-store](queue-storage.md#doc-37f6245b143a25) | 短事务管理收件、合批、模型状态与 UI 发件状态 | `src/wxbot/queue_store.py:91` | 2026-11-07 |
| [symbols/reloadable-backend](model-backends.md#doc-85aba8d0cc88bd) | 请求固定后端代际，在途完成后才关闭旧工作进程 | `src/butler/runtime/model_switch.py:50` | 2026-10-31 |
| [symbols/resident-role](resident.md#doc-81303bd5af31f1) | 常驻角色按聊天空闲调度抖音观看，持久化额度与本机日记 | `src/butler/runtime/resident.py:91` | 2026-11-06 |
| [symbols/voice-asset-store](delivery-voice.md#doc-a41b10d5400ad9) | 本地 WAV 音色资产清单与文件存储 | `src/wxbot/voice/assets.py:80` | 2026-11-03 |

#### concepts / concept

| 词条 | 简介 | 首个来源 | 最后核对 |
|---|---|---|---|
| [concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a) | 根目录与 Archify 架构图按节点标识读写同一套 Markdown 文档 | `README.md:849` | 2026-11-07 |
| [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00) | 自动回复使用网页预设全文合成，流式缓冲、后台准备与录音前复核 | `src/butler/delivery/automatic_tts.py:33` | 2026-11-07 |
| [concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66) | 采集前恢复越屏微信窗口，监视器联合区域外的像素不能证明发送方 | `src/wxbot/wechat/viewport.py:15` | 2026-11-05 |
| [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6) | 完整回复、排队、已发送和结果不确定分别处理 | `src/wxbot/queue_store.py:339` | 2026-11-07 |
| [concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3) | 按实际工作树与解释器确定开发基线，区分当前配置、生产模型链路与历史布局 | `README.md:125` | 2026-11-07 |
| [concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a) | 群成员先按同群 member_key 与昵称认人，头像 dhash 只作证据且不足以区分个体 | `src/butler/identity/user_registry.py:375` | 2026-11-05 |
| [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37) | 窗口/头像/昵称是证据，服务签发上下文才是工具授权边界 | `src/butler/agent/tools.py:47` | 2026-11-04 |
| [concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15) | 窗口→收件→批次→Butler→分句→UI→只读投影 | `src/wxbot/inbox.py:264` | 2026-11-07 |
| [concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6) | 模型失败的分类、脱敏、自动重试与超时放行契约 | `src/butler/agent/hermes.py:36` | 2026-11-05 |
| [concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43) | 未读任务只有采集成才清除，读不到文字时必须退避并最终放弃，否则阻塞发送队列 | `src/wxbot/inbox.py:449` | 2026-11-05 |
| [concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0) | 自动回复语音须绑定；授权网页预设音频包独立提供参考音 | `src/wxbot/voice/policy.py:112` | 2026-11-07 |

#### 影响分析与台账

影响报告包含待核对的草稿，不能当成已验证的业务结论。

- [impacts/2026-10-31-group-identity-nickname](identity-tools.md#doc-fbe924ce9641ad)
- [impacts/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-0c3db1f926d782)
- [impacts/2026-10-31-switchable-models](model-backends.md#doc-7e58558178e006)
- [impacts/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-528d62fcf07d59)
- [impacts/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-b92e2632af0e9b)
- [impacts/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-f77e7236a67711)
- [impacts/2026-11-03-development-doc-baseline](wxbot.md#doc-6981deab6390ae)
- [impacts/2026-11-04-contact-index-tts](index-tts.md#doc-f3a570551cedc3)
- [impacts/2026-11-04-index-tts-skill](index-tts.md#doc-f72ff421fb5c31)
- [impacts/2026-11-04-root-workspace-unification](wxbot.md#doc-1002b3869f9b4f)
- [impacts/2026-11-04-webui-preset-binding](index-tts.md#doc-b47165c49a3a7a)
- [impacts/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-98f596dd5f8d22)
- [impacts/2026-11-05-contact-policy-save](identity-tools.md#doc-62206a40735cb5)
- [impacts/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-2d4c142263c11b)
- [impacts/2026-11-05-enable-group-binding](identity-tools.md#doc-b934820de6d35e)
- [impacts/2026-11-05-group-and-auto-voice](delivery-voice.md#doc-b194f18a38699d)
- [impacts/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-53fb2c0d450b09)
- [impacts/2026-11-05-resident-diary-web](resident.md#doc-5b4e90fba08643)
- [impacts/2026-11-05-resident-xiaochao](resident.md#doc-6323d188bd37df)
- [impacts/2026-11-06-resident-visible-edge](resident.md#doc-6cee41da4b9fa7)
- [impacts/2026-11-07-delivery-handlers](delivery-pump.md#doc-26369af37d5fda)
- [impacts/2026-11-07-stale-regression-tests](wxbot.md#doc-a371c9f059b5c8)
- [raw/changes/2026-10-31-group-identity-nickname](identity-tools.md#doc-f39c15a6fe0885)
- [raw/changes/2026-10-31-identity-placeholder-names](identity-tools.md#doc-f3232d3cef51df)
- [raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)
- [raw/changes/2026-10-31-model-access-switch-core-emit](model-backends.md#doc-6510cadeadeb37)
- [raw/changes/2026-10-31-model-access-switch](model-backends.md#doc-954a7ea1e7487b)
- [raw/changes/2026-10-31-queue-batches-format](queue-worker.md#doc-33b232c2a9cf1f)
- [raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)
- [raw/changes/2026-11-01-citation-sweep](wxbot.md#doc-4d0e5fc0ed39d9)
- [raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)
- [raw/changes/2026-11-01-knowledge-atomic-retry](knowledge-vault.md#doc-8614fbc4e2f39c)
- [raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)
- [raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)
- [raw/changes/2026-11-01-knowledge-migrate-source-recheck](knowledge-vault.md#doc-97b2533a5ffcf7)
- [raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)
- [raw/changes/2026-11-01-knowledge-sessions](knowledge-vault.md#doc-ba214c308af8ff)
- [raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)
- [raw/changes/2026-11-01-knowledge-vault-alignment](knowledge-vault.md#doc-3f269e1ad8b05e)
- [raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)
- [raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)
- [raw/changes/2026-11-01-model-error-contract](model-backends.md#doc-60c1969bb5f6f6)
- [raw/changes/2026-11-01-model-request-error-visibility](model-backends.md#doc-507fd880895f6c)
- [raw/changes/2026-11-01-readme-unread-note](wechat-ui.md#doc-0dfa536a596503)
- [raw/changes/2026-11-02-details-whitelist-reverify](delivery-pump.md#doc-ae7b71a2b37518)
- [raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)
- [raw/changes/2026-11-02-mention-picker-gating-residue](wechat-ui.md#doc-980ea358badbe6)
- [raw/changes/2026-11-02-mention-residue-reverify](wechat-ui.md#doc-989f2003dec3a1)
- [raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)
- [raw/changes/2026-11-02-web-global-search-clear](dashboard.md#doc-5c4b4348a3410a)
- [raw/changes/2026-11-03-development-doc-baseline](wxbot.md#doc-f9d149494a6267)
- [raw/changes/2026-11-03-feat-voice-001-anchor-refresh](delivery-voice.md#doc-d313df34d8cc8b)
- [raw/changes/2026-11-03-feat-voice-001-virtual-mic](delivery-voice.md#doc-3b7c8dcbc01ec2)
- [raw/changes/2026-11-03-feat-voice-002-indextts](index-tts.md#doc-56093eafa42389)
- [raw/changes/2026-11-03-feat-voice-003-model-worker-drift](delivery-voice.md#doc-2f6dcdc8d592e1)
- [raw/changes/2026-11-03-feat-voice-003-voice-assets](delivery-voice.md#doc-a855357d83ac5d)
- [raw/changes/2026-11-03-indextts-enqueue-media](index-tts.md#doc-29fc2d893f2889)
- [raw/changes/2026-11-03-voice-assets-polish](delivery-voice.md#doc-5f445f7abfb4d8)
- [raw/changes/2026-11-04-contact-index-tts](index-tts.md#doc-cdb6f65d88730c)
- [raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)
- [raw/changes/2026-11-04-root-workspace-unification](wxbot.md#doc-b44eb256c557c6)
- [raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)
- [raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)
- [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)
- [raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)
- [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)
- [raw/changes/2026-11-05-enable-group-binding](identity-tools.md#doc-6f2fac571f1610)
- [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)
- [raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)
- [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)
- [raw/changes/2026-11-05-resident-xiaochao-readme](resident.md#doc-3b5de0b90aca6b)
- [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)
- [raw/changes/2026-11-06-resident-recommend-navigation](resident.md#doc-b2141987114c61)
- [raw/changes/2026-11-06-resident-visible-edge](resident.md#doc-eb3bb4d27e3f68)
- [raw/changes/2026-11-07-archify-node-documents](wxbot.md#doc-1968450e794d2a)
- [raw/changes/2026-11-07-architecture-diagram-trim](wxbot.md#doc-7574510a1cf96f)
- [raw/changes/2026-11-07-architecture-node-notes-readme](wxbot.md#doc-65d1db0ccb5dda)
- [raw/changes/2026-11-07-architecture-node-notes](wxbot.md#doc-8790acdf96d310)
- [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)
- [raw/changes/2026-11-07-stale-regression-tests](wxbot.md#doc-df3c99eaa835f8)
<!-- end-migrated-part: doc-6e5a10e80a7955 -->

<a id="doc-dd2bd595b3d8f8"></a>

### 共享基础能力

来源：`llm wiki/wxbot/modules/common.md:1`。

```yaml
type: module
module: common
summary: 仓库根、事件追踪、流和 wire schema 的跨包纯基础层
coverage: overview
last_verified: '2026-11-04'
sources:
- path: src/common/paths.py
  line: 29
  anchor: REPO_ROOT = _root()
- path: src/common/flow_trace.py
  line: 74
  anchor: def record(
- path: src/common/media_bundle.py
  line: 9
  anchor: 'def '
- path: src/common/avatar_identity.py
  line: 57
  anchor: def avatar_is_informative(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-04-index-tts-skill
```
### 共享基础能力

#### 职责与边界

`src/common/` 不依赖 Butler 业务，不操作微信 UI。`common.paths.REPO_ROOT` 是项目路径唯一共享入口，支持 WXBOT_ROOT；新模块不按目录深度猜项目根。

#### 使用方

[modules/butler](butler.md#doc-38393df7a7b4da)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe) 和 [modules/wiki](wxbot.md#doc-ed5d88ddcd1b47) 都可使用其路径/纯 schema 能力。flow_trace 用请求 ID 记录流转，消息正文不能写进结构追踪证据。媒体 wire schema 由两服务共享，详细字段另行建档。

#### 头像证据

`voice_audio` 是无 UI/业务依赖的 PCM16 转换与分段工具。`media_bundle.validate_voice_items` 单独校验 `{kind: voice, media_id}`；原图文 `validate_items` 仍只接受 text/image。使用方与限制见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。

`avatar_identity.normalize_avatar` 统一输出 36×36 PNG + dhash-v1，透明区域用 `#1F1F1F` 兜底。`avatar_is_informative` 只拒绝颜色数不超过 `BLANK_AVATAR_COLORS` 的纯色块：窗口被遮挡、最小化或元素滚出视口时抓到的就是这种图，dhash 仍有值，不能当身份证据。不能改用颜色丰富度、亮度标准差或比特位数做判据，实测这些都和真实头像重叠（见 [concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)）。

#### 代码依据

- `src/common/paths.py:29` — `REPO_ROOT = _root()`
- `src/common/flow_trace.py:74` — `def record(`
- `src/common/media_bundle.py:9` — `def `
- `src/common/avatar_identity.py:57` — `def avatar_is_informative(`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。
<!-- end-migrated-part: doc-dd2bd595b3d8f8 -->

<a id="doc-ed5d88ddcd1b47"></a>

### 项目知识图谱工具

来源：`llm wiki/wxbot/modules/wiki.md:1`。

```yaml
type: module
module: wiki
summary: 本地关键词检索、证据入库和一致性巡检
coverage: core
last_verified: '2026-11-07'
sources:
- path: AGENTS.md
  line: 36
  anchor: '## Project knowledge graph'
- path: README.md
  line: 787
  anchor: '### 项目知识图谱'
- path: llm wiki/wxbot/scripts/wiki.py
  line: 69
  anchor: 'class Wiki:'
- path: llm wiki/wxbot/scripts/wiki.py
  line: 250
  anchor: def ingest(
- path: llm wiki/wxbot/scripts/wiki.py
  line: 301
  anchor: def query(
changes:
- raw/changes/2026-11-07-archify-node-documents
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-readme-unread-note
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
- raw/changes/2026-11-03-development-doc-baseline
- raw/changes/2026-11-04-root-workspace-unification
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao-readme
- raw/changes/2026-11-05-resident-diary-web
- raw/changes/2026-11-06-resident-visible-edge
- raw/changes/2026-11-07-architecture-node-notes
- raw/changes/2026-11-07-delivery-handlers
```
### 项目知识图谱工具

README 追加小潮使用说明后，原图谱维护章节仍为同一入口。来源 [raw/changes/2026-11-05-resident-xiaochao-readme](resident.md#doc-3b5de0b90aca6b)。

#### 入口和流程

`llm wiki/wxbot/scripts/wiki.py` 是本地开发工具，依赖 [modules/common](wxbot.md#doc-dd2bd595b3d8f8) 的 REPO_ROOT 和已有 PyYAML。query 展开双向双链；change 创建追加记录；ingest 验证词条来源并刷新索引/日志/快照；lint 只读检查；status 查看规模及待入库记录。操作见 [guide](wxbot.md#doc-9cf47fd939c877)。

开发前先核对实际工作树、分支、SHA、未提交修改及解释器的 `REPO_ROOT`，见 [concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3)。
若可编辑安装误指向另一工作树，本地工具支持 `--repo-root <当前项目根目录>` 显式限定图谱读写；
这不能替代修正业务运行环境，也不授权切分支、合并或重启服务。
2026-11-04 的主目录与可编辑安装统一已在 [concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3) 记录；
仍须按当前解释器和实际导入位置核验，不能把本次结果当成后续永久保证。

#### 边界

根目录架构图的节点笔记由浏览器单独维护，见 [concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a)。
图谱工具不读取这些用户笔记。来源 [raw/changes/2026-11-07-architecture-node-notes](wxbot.md#doc-8790acdf96d310)。

不会调用模型或业务服务；语义抽取/契约/字段血缘由开发模型对照源码维护。`ingest-state.json` 保存归一化文本摘要，来源完整文件任何变化都提示复核。只读命令不访问 runtime 数据。入口规则在根 AGENTS.md；[modules/plugin](resident-skills.md#doc-709338d3e083eb) 的运行时身份权限不受图谱影响。

#### 验证

本地离线用例在 tests/unit/test_project_wiki.py，测试临时库与命令输出/写入行为，不依赖 Obsidian。测试目录本地忽略，源码中不新增测试接口。

#### 代码依据

- `AGENTS.md:36` — `## Project knowledge graph`
- `README.md:787` — `### 项目知识图谱`
- `llm wiki/wxbot/scripts/wiki.py:69` — `class Wiki:`
- `llm wiki/wxbot/scripts/wiki.py:250` — `def ingest(`
- `llm wiki/wxbot/scripts/wiki.py:301` — `def query(`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)

[raw/changes/2026-11-01-readme-unread-note](wechat-ui.md#doc-0dfa536a596503)

[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)

[raw/changes/2026-11-02-mention-picker-gating-residue](wechat-ui.md#doc-980ea358badbe6)

[raw/changes/2026-11-03-development-doc-baseline](wxbot.md#doc-f9d149494a6267)

[raw/changes/2026-11-04-root-workspace-unification](wxbot.md#doc-b44eb256c557c6)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 联系人语音配置核对

[raw/changes/2026-11-04-contact-index-tts](index-tts.md#doc-cdb6f65d88730c)：新增会话授权控件与原接口消费，源码位置已核对；后端契约保持。


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。


#### 群聊采集与自动语音复核（2026-11-05）

README 追加自动语音真实 WebUI 默认、配置热读和窗口越屏恢复说明；安装路径、静态文件位置及图谱 CLI 合同不变。功能依据见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)、[concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66)。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。

#### 本次核对

README 的图谱维护流程沿用，更新联系人操作路径。 来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 本次核对

README 增补知识库事实删除，图谱流程沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 小潮日记接入核对

README 末尾追加管理台查看小潮日记的用法，图谱维护章节入口未移动。 来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。

README 追加有窗口运行说明后，图谱维护入口的原文和行号经复核。来源 [raw/changes/2026-11-06-resident-visible-edge](resident.md#doc-eb3bb4d27e3f68)。


#### 发件拆分文档复核

README 的 wxbot 文件职责新增 delivery_handlers，架构章节记录第一步与后续规划的界限；配置、安装和图谱维护流程未变。

来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。


#### Archify 笔记入口复核

README 的项目图谱维护流程与脚本入口没有变化。独立 Archify 查看器新增文档按钮，沿用项目 `architecture-notes/`；它不把用户笔记写入开发图谱，维护记录仍须按 raw → 词条 → ingest → lint 执行。见 [concepts/architecture-node-notes](wxbot.md#doc-6372a6d15b637a)、[raw/changes/2026-11-07-archify-node-documents](wxbot.md#doc-1968450e794d2a)。
<!-- end-migrated-part: doc-ed5d88ddcd1b47 -->

<a id="doc-8508032cbe5131"></a>

### wxbot UI 与持久队列

来源：`llm wiki/wxbot/modules/wxbot.md:1`。

```yaml
type: module
module: wxbot
summary: 微信 UI 主线程与不接触 UI 的模型队列线程
coverage: overview
last_verified: '2026-11-07'
sources:
- path: src/wxbot/voice/assets.py
  line: 80
  anchor: 'class VoiceAssetStore:'
- path: src/wxbot/voice/policy.py
  line: 112
  anchor: 'def has_usable_binding(self, contact: str) -> bool:'
- path: src/wxbot/inbox.py
  line: 45
  anchor: 'class MainInbox:'
- path: src/wxbot/queue_worker.py
  line: 26
  anchor: 'class ModelWorker:'
- path: src/wxbot/queue_store.py
  line: 91
  anchor: class QueueStore(
- path: src/wxbot/main.py
  line: 29
  anchor: def build_processor(
- path: src/wxbot/inbox.py
  line: 120
  anchor: def sync_users(
- path: src/wxbot/queue_store.py
  line: 192
  anchor: def identity_observations(
- path: src/wxbot/ui_contract.py
  line: 65
  anchor: 'class Snapshot:'
- path: src/wxbot/wechat/locator.py
  line: 9
  anchor: def wait_until(
- path: src/wxbot/wechat/chat_window.py
  line: 37
  anchor: 'ref: str = '''''
- path: src/wxbot/wechat/viewport.py
  line: 86
  anchor: 'def ensure_window_visible(window):'
changes:
- raw/changes/2026-11-03-indextts-enqueue-media
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-03-feat-voice-001-virtual-mic
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-10-31-identity-placeholder-names
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-picker-gating-residue
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-07-delivery-handlers
depends_on:
- modules/common
```
### wxbot UI 与持久队列

#### 职责与范围

`src/wxbot/` 负责窗口、轮询、差分、收发队列及微信发送。`MainInbox` 在 UI 主线程收集消息，[symbols/model-worker](queue-worker.md#doc-0183b6974519f0) 在后台调用模型，UI 操作不能进入模型线程。

#### 入口、依赖和数据

入口 `src/wxbot/main.py`。消息持久化在 [symbols/queue-store](queue-storage.md#doc-37f6245b143a25)，核心表 [tables/queue-inbox](inbox.md#doc-6529d9966e604a)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)；数据库路径由 queue_database(cfg) 解析，不从图谱读取真实库。

模型适配通过 processor.router.Router；Butler 适配是 [symbols/butler-processor](queue-worker.md#doc-0b0a168dc38d24)，消费 [apis/butler-handle](butler.md#doc-4f70359e7ae440) / [apis/butler-handle-stream](butler.md#doc-5135f5350303bc)。主动推送入口属于 outbound 服务，详细契约待建档。

#### 影响边界

[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) 的 `/send-voice-bundle` 下载已验证的标准 WAV，由 UI 线程一次事务写入语音包再确认 queued。`DeliveryPump` 直接加载媒体而不重复合成，依旧检查总开关/联系人模式；已提供网页参考音的包不要求管理台绑定。`VoiceSession` 先准备设备、按 RALT，等 250ms 再灌音；异常释放键，已开始录音的失败记 uncertain。包失败停止剩余项且不自动发文字回退。

改队列字段需检查 [modules/dashboard](dashboard.md#doc-bb47c9474691fe) 的只读 SQL 和 [modules/web](dashboard.md#doc-aeec90dfe23cd3) 展示。改分句/流式协议需检查 [symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)、[concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6) 及 [concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)。用户自己重启服务，离线验证不能发送真人微信。

#### 采集与提及

未读任务只在采集成（`_capture`）时清除；读不到可采内容的未读按指数退避，达到 `[bot].unread_give_up_attempts`（默认 5）后放弃并清掉 `pending_sessions`，否则同一行记录会让 `prepare` 永远跳过该联系人。细节见 [concepts/unread-capture-retry](wechat-ui.md#doc-8bf7e570157f43)。

群聊 @ 提及由 [symbols/mention-selection](wechat-ui.md#doc-c251b5ba0c9ae7) 完成：先等候选成员面板出现再输入昵称，候选不唯一或昵称不可信时回退为不带 @ 的纯正文；回退清理只能使用 uiautomation `SpecialKeyNames` 里声明过的键。面板在 `wechat.mention.open_timeout`（默认 1 秒）内没出现时只删除自己的 `@`，不会把昵称写成普通文字。失败后读回仍能证明是本会话输入的字面 `@...` 时，登记为 `outbox.draft_text`（`mention_residue=true`），下一次投递前自动清理，避免后续消息一直 `draft_conflict`。

#### 快照与引用

一次界面读取就是一个快照，每行带只属于这次读取的引用（`Message.ref`，来自控件运行期标识）。发件确认、会话切换后的就绪判定都不再依赖固定 sleep，而是「重读一次再比较」：条件等待由 `wechat/locator.wait_until` 提供，始终带超时上限。引用缺失、行数为空或被复用（不唯一）时显式降级为正文对齐，降级事实写进 `delivery_events.details` 的 `confirm_evidence` / `ref_available`；确认规则与失败码见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。引用不落库，`observations.snapshot` 与 `outbox.baseline` 只保存去引用版本。

#### 启动时的身份补登

`MainInbox.sync_users` 只重放头像证据，不重放历史消息正文，也不建回复。重放时丢弃空白头像（遮挡时抓到的纯色块）和没有昵称的群成员观测：这两类建不出可核对的人，只会在每次启动时多出一条「待命名」。昵称取群目录当前映射，而不是入库那一刻的快照；截图给不出真名时的占位名（`成员-<ID前8位>`）也当作无名，否则照样建出待命名档案。见 [concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)。

#### 代码依据

- `src/wxbot/inbox.py:45` — `class MainInbox:`
- `src/wxbot/queue_worker.py:26` — `class ModelWorker:`
- `src/wxbot/queue_store.py:91` — `class QueueStore(`
- `src/wxbot/main.py:29` — `def build_processor(`
- `src/wxbot/inbox.py:23` — `def member_nickname(`
- `src/wxbot/inbox.py:120` — `def sync_users(`
- `src/wxbot/queue_store.py:192` — `def identity_observations(`
- `src/wxbot/ui_contract.py:65` — `class Snapshot:`
- `src/wxbot/wechat/locator.py:9` — `def wait_until(`
- `src/wxbot/wechat/chat_window.py:37` — `ref: str = ''`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

#### 统一模型通道

有 installation 配置的安装仅允许 model.backend=butler；旧 direct 安装需显式 migrate。模型选择由 Butler 管理，见 [modules/models](model-backends.md#doc-69928b2a06b8f9)。


[raw/changes/2026-10-31-switchable-models](model-backends.md#doc-85f41883967373)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-mention-picker-gating-residue](wechat-ui.md#doc-980ea358badbe6)

#### 音色资产与绑定门控

- [symbols/voice-asset-store](delivery-voice.md#doc-a41b10d5400ad9) 管理本地参考 WAV；[concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0) 规定无绑定不合成。
- queue_worker / delivery 调用 delivery_mode_for / has_usable_binding。
- 入队语音 `media_path` 只在 `tts_provider=fixture` 时写假 WAV；`indextts` 留空，投递时走 `prepare`。见 [raw/changes/2026-11-03-indextts-enqueue-media](index-tts.md#doc-29fc2d893f2889)。

#### 变更

- 2026-11-03: FEAT-VOICE-001 P1 outbox kind=voice（虚拟麦+RALT）；见 [raw/changes/2026-11-03-feat-voice-001-virtual-mic](delivery-voice.md#doc-3b7c8dcbc01ec2)
- [raw/changes/2026-11-03-feat-voice-003-voice-assets](delivery-voice.md#doc-a855357d83ac5d)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 群聊采集与自动语音复核（2026-11-05）

[concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00) 补充自动语音的缓冲/后台准备与失败单次回退；[concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66) 补充越屏恢复，未修改模型后端请求/重试合同。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。


#### 发件处理器拆分

[symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca) 保留统一 outbox 认领与 UI 所有权，按 kind 调用 [symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c)。同会话顺序仍由 claim_delivery 的 seq/未终结前项约束保证，数据字段和 HTTP 不变。

来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。
<!-- end-migrated-part: doc-8508032cbe5131 -->

<a id="doc-f68e362b618ab8"></a>

### 项目知识图谱 Implementation Plan

来源：`llm wiki/wxbot/plan.md:1`。

### 项目知识图谱 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 在当前会话完成各项，保留用户已有工作。

**Goal:** 在已有 Obsidian 库内形成可执行、可追溯的查图与增量维护闭环。

**Architecture:** Markdown 是语义知识，raw 是追加台账，Python 仅做检索、结构检查和入库登记。AGENTS.md 约束开发模型维护流程。

**Tech Stack:** Python、现有 PyYAML、Markdown、Obsidian 双链。

**Spec:** [design](wxbot.md#doc-ba7d4d46f1c73f)

#### Global Constraints

所有图谱文件置于 `llm wiki/wxbot/`；不覆盖 Obsidian 配置；不读取运行时数据和秘密；不重启或发消息；保留脏工作树中其他改动。

#### Review Focus

- 路径越界或指向秘密的来源必须拒绝，失败前不得写图谱。
- raw 入库后改写必须报错，再次入库相同记录不能重复追加日志。
- 查询应同时找到出链和入链，命中为空时明确要求回到源码建档。
- 代码变化、断链及漏入库应有可操作的巡检诊断。
- 词条关系及契约有人工核对边界，不将脚本检查当作语义证明。

#### Tasks

- [x] 1. 用临时仓库编写命令测试，运行确认功能缺失；实现 query / change / ingest / lint / status 并运行回归。
- [x] 2. 阅读消息处理链路源码，建模块导航和核心 API、表、符号、概念词条；补齐模板、覆盖范围和操作说明。
- [x] 3. 在根 AGENTS.md 接入查图/修改记录/入库规范，README 加入口；本次实施也写 raw 和影响分析，完成真实入库。
- [x] 4. 执行离线测试、真实查询及 lint；核查仅修改本次范围并报告边界。专项 20 passed / 1 skipped；整库回归限制见 [verification](wxbot.md#doc-951820f4d5f621)。
<!-- end-migrated-part: doc-f68e362b618ab8 -->

<a id="doc-9be513138ee5dc"></a>

### 标题

来源：`llm wiki/wxbot/templates/api.md:1`。

```yaml
type: api
module: 模块名
summary: 一句话说明
coverage: overview
last_verified: YYYY-MM-DD
sources:
- path: src/模块/文件.py
  line: 1
  anchor: 指定行的非空原文
changes:
- raw/changes/YYYY-MM-DD-topic
```
### 标题

#### 方法、路径与鉴权

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 请求字段（类型、必填、默认、校验）

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 响应字段与错误语义

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 实现链（路由→服务→符号）

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 数据表与字段血缘

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 前端消费点（文件+函数）

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 测试与风险

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 代码依据与修改来源

填写真实位置与双链，删除全部占位后才可入库。
<!-- end-migrated-part: doc-9be513138ee5dc -->

<a id="doc-876e1a0156045c"></a>

### 修改记录

来源：`llm wiki/wxbot/templates/change.md:1`。

```yaml
type: change
title: 本次目标
pages: []
# 更正旧记录时使用 supersedes: [raw/changes/旧记录ID]
```
### 修改记录

#### 目标与背景

待填写

#### 文件与代码位置

待填写

#### 接口与字段

待填写

#### 数据库与迁移

待填写

#### 前端消费点

待填写

#### 测试与异步任务

待填写

#### 风险与回滚

待填写
<!-- end-migrated-part: doc-876e1a0156045c -->

<a id="doc-66a8899f322d51"></a>

### 标题

来源：`llm wiki/wxbot/templates/concept.md:1`。

```yaml
type: concept
module: 模块名
summary: 一句话说明
coverage: overview
last_verified: YYYY-MM-DD
sources:
- path: src/模块/文件.py
  line: 1
  anchor: 指定行的非空原文
changes:
- raw/changes/YYYY-MM-DD-topic
```
### 标题

#### 术语与状态含义

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 业务规则与边界

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 跨层映射

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 历史坑与冲突

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 相关模块、接口、测试

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 代码依据与修改来源

填写真实位置与双链，删除全部占位后才可入库。
<!-- end-migrated-part: doc-66a8899f322d51 -->

<a id="doc-2595bebb318aaa"></a>

### 改前影响分析

来源：`llm wiki/wxbot/templates/impact.md:1`。

```yaml
type: impact
status: draft
date: YYYY-MM-DD
```
### 改前影响分析

#### 需求关键词与图谱命中

待填写：词条双链、覆盖缺口和已核对源码。

#### 要改的文件、符号与调用方

待填写：真实路径、行号、反向调用和相关测试。

#### 接口与前端契约

待填写：方法/路径、请求/响应变化、页面/函数/类型。

#### 数据库与字段血缘

待填写：表/字段/索引/迁移、跨层传递和冗余来源。

#### 风险、验证、异步任务与回滚

待填写：已知坑、缺少覆盖、定时任务/消费者；明确授权边界。

#### 实际改动与 raw 归档

改完补充实际范围及修改记录双链，status 改为 completed；不改写旧 raw。
<!-- end-migrated-part: doc-2595bebb318aaa -->

<a id="doc-6a76d4ecff85eb"></a>

### 标题

来源：`llm wiki/wxbot/templates/module.md:1`。

```yaml
type: module
module: 模块名
summary: 一句话说明
coverage: overview
last_verified: YYYY-MM-DD
sources:
- path: src/模块/文件.py
  line: 1
  anchor: 指定行的非空原文
changes:
- raw/changes/YYYY-MM-DD-topic
depends_on: []
```
### 标题

#### 职责与目录范围

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 入口与对外接口

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 依赖模块与数据表

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 消费方与边界

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 风险与覆盖缺口

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 代码依据与修改来源

填写真实位置与双链，删除全部占位后才可入库。
<!-- end-migrated-part: doc-6a76d4ecff85eb -->

<a id="doc-b7b71e230e267e"></a>

### 标题

来源：`llm wiki/wxbot/templates/symbol.md:1`。

```yaml
type: symbol
module: 模块名
summary: 一句话说明
coverage: overview
last_verified: YYYY-MM-DD
sources:
- path: src/模块/文件.py
  line: 1
  anchor: 指定行的非空原文
changes:
- raw/changes/YYYY-MM-DD-topic
calls: []
called_by: []
```
### 标题

#### 签名与职责

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 所属模块

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 调用方与反向引用

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 调用了谁

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 副作用（库/文件/事件/网络）

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 契约、测试与风险

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 代码依据与修改来源

填写真实位置与双链，删除全部占位后才可入库。
<!-- end-migrated-part: doc-b7b71e230e267e -->

<a id="doc-b29fabcf0318a0"></a>

### 标题

来源：`llm wiki/wxbot/templates/table.md:1`。

```yaml
type: table
module: 模块名
summary: 一句话说明
coverage: overview
last_verified: YYYY-MM-DD
sources:
- path: src/模块/文件.py
  line: 1
  anchor: 指定行的非空原文
changes:
- raw/changes/YYYY-MM-DD-topic
```
### 标题

#### 含义、所属数据库与 schema 版本

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 最终字段（类型、约束、默认，包含升级补列）

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 索引与外键声明/是否强制

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 字段血缘（DB→对象/DTO→API→前端类型/组件）

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 冗余字段与数据迁移

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 读写符号与测试

待填写：所有事实标明代码位置；不涉及时说明原因。

#### 代码依据与修改来源

填写真实位置与双链，删除全部占位后才可入库。
<!-- end-migrated-part: doc-b29fabcf0318a0 -->

<a id="doc-951820f4d5f621"></a>

### 本次验证记录

来源：`llm wiki/wxbot/verification.md:1`。

### 本次验证记录

日期：2026-10-31。运行命令中的临时目录均在项目下，不访问真实微信剪贴板、联系人数据库或服务。

#### 本次功能

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_project_wiki.py --basetemp .tmp-wiki-tests-code-green --tb=short
```

结果：16 passed。覆盖双向链接查询、保存 draft、安全路径/来源、raw 禁止覆盖、入库幂等、代码摘要漂移、未登记词条、断链/锚点、反向调用、依赖环、孤立词条及代码块中的示例不误判为链接。

后续若审查修正代码，在本页追加新验证结果，并在最终入库前以实际结果为准。

#### 整库回归的限制

执行项目全量 `python -m pytest --basetemp .tmp-wiki-full-suite --tb=short`：在约 10% 已有多项失败，随后长时间没有输出，因此中止本次启动的测试进程，未得到完整结果。没有停止或重启业务服务。

用 `python -m pytest --basetemp .tmp-wiki-suite-first-failure --maxfail=1 --tb=short` 重新定位：53 passed，1 failed。失败为：

`tests/butler/identity/test_contact_migration.py::test_nonlocal_install_preserves_channel_management_and_rejects_cutover[deepseek]`

在该文件第 412 行，期望 `not is_unified(database)`，实际为 True。本次没有修改身份迁移实现或测试；不能据本次结果宣称整个工作树通过，也未在知识图谱任务中扩展修复身份模块。

#### 图谱实际核对

入库后执行 status、真实关键词 query、lint、编译和 diff 空白检查。来源限公开源码，Obsidian GUI 未做自动化验收；双链结构由本地巡检验证。

#### 审查后的最终专项回归

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_project_wiki.py --basetemp .tmp-wiki-tests-final-review --tb=short
```

结果：**20 passed，1 skipped**。新增验证增量入库保留旧记录、历史来源不可丢失，以及来源和 Markdown 路径解析后的重定向拒绝。创建真实 Windows 目录联接的测试因当前沙箱不支持而跳过；确定性路径解析回归已验证拒绝逻辑。独立只读审查复核后无剩余重要发现。

交付前使用 `.tmp-wiki-tests-delivery` 再次执行专项回归：20 passed / 1 skipped。首批入库 27 pages、1 条修改记录，pending changes: 0；再次 ingest 输出 already-ingested，未重复写日志；实际 lint 输出 OK。真实关键词查询命中处理接口并展开关联消费方。脚本编译和限定本次范围的 diff 空白检查通过；未做 Obsidian GUI 验收。

后续再次巡检实际检出 queue-batches.md 的表格排版变化；保留该编辑，以 [raw/changes/2026-10-31-queue-batches-format](queue-worker.md#doc-33b232c2a9cf1f) 追加登记。事实和业务代码未变，记录数由 1 增至 2。
<!-- end-migrated-part: doc-951820f4d5f621 -->

<a id="doc-aa2bc4bbdc2544"></a>

### tools

来源：`tools/README.md:1`。

### tools

开发与发布用的本机工具。运行时（wxbot / Butler / 管理台）不依赖这里的任何文件，
但改微信 UI 适配、联调 Codex、发布前都靠它们。

| 文件 | 用途 | 是否需要网络 |
|---|---|---|
| `probe.py` | 微信控件树探测，用来校准 `config.wxbot.toml` 的 `[wechat.*]` 选择器 | 否 |
| `avatar_calibration.py` | 头像采样校准：对比自动边界检测与旧的固定 36px 裁剪 | 否 |
| `debug_read.py` | 检查窗口／消息列表／输入框，并打印每条消息被判成谁发的 | 否 |
| `probe_codex.py` | Codex 端到端联调：真实模型调用 + MCP 记忆 + 线程续接 | 是（调模型） |
| `release.py` | 按白名单打两个可移植包，并做凭据形状审计 | 否 |
| `voice-ptt-ops.md` | FEAT-VOICE-001：虚拟麦选麦 + Right Alt 操作/卸载说明 | 否 |
| `indextts-ops.md` | FEAT-VOICE-002：IndexTTS 仓外安装/权重/卸载与配置键 |
| `indextts_worker.py` | FEAT-VOICE-002：uv 环境内合成并输出 P1 合同 WAV |
| `voice-fixtures/p1-tone.wav` | P1 固定测试音频（16k mono PCM） | 否 |

#### probe.py

打印微信窗口的 UIA 控件树，确认控件能不能读到、路径是什么。

```powershell
.\.venv\Scripts\python.exe tools\probe.py --list                     # 列出所有顶层窗口
.\.venv\Scripts\python.exe tools\probe.py --window 微信              # 打印控件树
.\.venv\Scripts\python.exe tools\probe.py --window 微信 --depth 12 --raw
```

- 默认**脱敏**：控件文字显示为 `***(长度)`，输出可以直接贴给别人分析；`--raw` 才显示真实文字。
- 只读本机界面，不联网、不发任何数据。
- 窗口必须在屏幕上、不遮挡；微信升级后控件结构变了，先用它重新校准。

#### debug_read.py

逐个检查 `[bot].bound_users` 里的窗口，输出四项：独立窗口、消息列表、输入框、
每条消息的判定结果（`左/右` 是两侧非背景像素数，用来区分谁发的）。

```powershell
.\.venv\Scripts\python.exe tools\debug_read.py
.\.venv\Scripts\python.exe tools\debug_read.py --raw
```

- 默认脱敏，`--raw` 显示真实文字；在项目根运行。
- 检查对象是 `[bot].bound_users`（通常由联系人目录投影而来，也可直接写在 toml 里），
  找的是独立聊天窗口 `mmui::ChatSingleWindow`。用 `[wechat].mode = "main"` 主窗口模式时，
  它检查的不是正在跑的那条链路，只能用来核对控件配置。
- 绑定列表为空时会直接提示"没有独立聊天窗口可检查"并退出，不报错。

#### avatar_calibration.py

把当前群聊窗口里每一行消息的头像截成两版并排放大：左列按像素边界自动定位，
右列是旧的固定 36px 裁剪。左边出现完整头像、右边露出被切掉的右下角，就说明采样正常。

```powershell
.\.venv\Scripts\python.exe tools\avatar_calibration.py
```

- 微信要停在一个群聊窗口，且窗口可见、不遮挡、不最小化——被挡住时会抓到桌面像素。
- 输出 `cache/avatar-calibration.png`，标签里带实测偏移量（正常是 `(+8,+8)`）。
- 只读屏幕，不发消息、不改配置。换了显示器缩放或微信大版本更新后跑一次即可。

#### probe_codex.py

在临时目录和随机端口上起一个一次性 Butler，验证 Codex 后端整条链路：
真实模型调用、MCP `memory_set` 落库、下一轮 `memory_get` 能取回；
两个假联系人分别绑定不同角色／skill（回复在输出的 JSON 里人工核对口吻）。

```powershell
.\.venv\Scripts\python.exe tools\probe_codex.py --auth-home data\codex
.\.venv\Scripts\python.exe tools\probe_codex.py --auth-home data\codex --model <模型名>
```

- `--auth-home` 必填：填**你自己已登录**的 Codex 目录，用相对当前目录或绝对路径都行，
  默认安装下就是 `data/codex`；脚本只读取，不复制任何凭据。
- 会真实调用模型，消耗额度；不改动现有服务与数据库（全部走临时目录）。
- `butler.push` 被替换成直接抛异常，**绝不外发微信**。
- 结果以 JSON 输出，`wechat_sent` 恒为 `false`；失败时抛错并带上后端最后的错误。

#### release.py

按显式白名单扫磁盘出包，**不看 Git 状态**，所以未提交的改动也会进包——发布前先确认工作区干净。

```powershell
.\.venv\Scripts\python.exe tools\release.py                  # 输出到 dist/
.\.venv\Scripts\python.exe tools\release.py --output <目录>
```

产出两个包：

- `butler-wxbot-<version>.zip`：应用包，根文件（`README.md`、`AGENTS.md`、`pyproject.toml`、
  `requirements.txt`、`uv.lock`、`.gitignore`）+ `src/`、`web/`、`plugins/` + 特例文件
  （`.agents/plugins/marketplace.json`、`scripts/setup.ps1`、`tools/probe_codex.py`、`tools/release.py`）。
- `butler-wechat-<version>.zip`：插件包，`plugins/butler-wechat/` 的内容。

排除项：`.venv`、`node_modules`、`__pycache__`、`.git`、`.idea`、`.pytest_cache`、`data`、`cache`、
`dist`、`.superpowers`、`*.pyc`、`auth.json`、`.env*`、`*.db`、`*.sqlite3`、`*.session*`、
`config.*.toml` 及其备份。`tests/` 不入库，也不进包。

打包前会扫描凭据形状的字面量（Telegram bot token、`sk-`、`gh[pousr]_`、私钥头），
只看 `.py`/`.md`/`.json`/`.toml`/`.txt`/`.html`/`.ps1`/`.js`/`.css` 这些文本后缀；
命中任一条直接抛错，包根本不会写出来。
<!-- end-migrated-part: doc-aa2bc4bbdc2544 -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [四项历史回归失败修复记录](#doc-b664511b293d11) · `docs/superpowers/plans/2026-11-07-stale-regression-tests-verification.md`
- [知识图谱落地影响分析](#doc-0c3db1f926d782) · `llm wiki/wxbot/impacts/2026-10-31-knowledge-graph-bootstrap.md`
- [开发文档与技术基线口径核对](#doc-6981deab6390ae) · `llm wiki/wxbot/impacts/2026-11-03-development-doc-baseline.md`
- [主目录、main 与 Python 环境统一](#doc-1002b3869f9b4f) · `llm wiki/wxbot/impacts/2026-11-04-root-workspace-unification.md`
- [四项历史回归失败核对](#doc-a371c9f059b5c8) · `llm wiki/wxbot/impacts/2026-11-07-stale-regression-tests.md`
- [项目知识图谱首批建档与维护闭环](#doc-f0c0814f02ebe4) · `llm wiki/wxbot/raw/changes/2026-10-31-knowledge-graph-bootstrap.md`
- [词条代码引用行号复核](#doc-4d0e5fc0ed39d9) · `llm wiki/wxbot/raw/changes/2026-11-01-citation-sweep.md`
- [统一当前开发基线、配置来源与发送实现文档](#doc-f9d149494a6267) · `llm wiki/wxbot/raw/changes/2026-11-03-development-doc-baseline.md`
- [统一主目录 main 与可编辑安装绑定](#doc-b44eb256c557c6) · `llm wiki/wxbot/raw/changes/2026-11-04-root-workspace-unification.md`
- [Archify 节点详情加入 Markdown 文档按钮](#doc-1968450e794d2a) · `llm wiki/wxbot/raw/changes/2026-11-07-archify-node-documents.md`
- [精简架构图底部区块](#doc-7574510a1cf96f) · `llm wiki/wxbot/raw/changes/2026-11-07-architecture-diagram-trim.md`
- [架构图节点文档使用说明与开发基线复核](#doc-65d1db0ccb5dda) · `llm wiki/wxbot/raw/changes/2026-11-07-architecture-node-notes-readme.md`
- [架构图节点 Markdown 文档](#doc-8790acdf96d310) · `llm wiki/wxbot/raw/changes/2026-11-07-architecture-node-notes.md`
- [四项历史失败的测试合同修正](#doc-df3c99eaa835f8) · `llm wiki/wxbot/raw/changes/2026-11-07-stale-regression-tests.md`
- [3.2 file｜代码文件（Controller / Service / Mapper / Vue 页面 / JS 等）](#doc-5fd0435fe93ef7) · `llm wiki/wxbot/raw/legacy/CLAUDE-wiki-schema.md`

<a id="doc-b664511b293d11"></a>

### 四项历史回归失败修复记录

来源：`docs/superpowers/plans/2026-11-07-stale-regression-tests-verification.md:1`。

### 四项历史回归失败修复记录

本次核对发现四项均为旧测试预期，生产代码无需修改。修改前独立运行四个原用例，确认均失败；修改后连同补充对照，共 8 项通过。

全项目回归结果：**1584 通过、0 失败**，耗时 121.72 秒。仍有 3 条 Pillow `Image.getdata` 弃用提示，来自原头像归一化代码，不影响本次测试通过。

执行命令（项目根目录）：

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp tests/.tmp-four-failures-full-1107a --tb=short
```

控制台完整结果保存在本地 `tests/.four-failures-full.log`。

| 原失败 | 源码依据 | 修正与补充 |
|---|---|---|
| 固定要求 6 个 Skill | 当前 manifest 导出 roles/tools，包含新增的 IndexTTS | 校验所有实际技能均导出、核心技能存在，并保留引导/MCP/协议检查 |
| 未确认发送后继续剩余段 | finish_delivery + _end_reply 保留 uncertain、停止剩余段 | 分别验证 CLI 确认和显式重试，其他段完整记录不变 |
| 重启后的旧批次继续阻塞 | recover 终结旧轮并保留待核对记录 | 核对正文登记不会消除审计、新轮能继续；补 sending/confirming 仍阻塞的对照 |
| 默认要求 0.5 秒输入间隔 | validate_typing_config 与 README 默认 0.25 秒 | 同时覆盖默认 0.25 和显式 0.5 秒，保留完整正文、单次回车和剪贴板恢复 |

新测试入口：

- `tests/integration/test_portable_install.py::test_plugin_references_and_protocol_are_self_contained`
- `tests/unit/queue/test_queue_admin.py::test_multipart_cli_resolution_preserves_sent_and_stopped_parts`（sent / retry）
- `tests/unit/queue/test_queue_store.py::test_user_confirmed_text_keeps_restart_review_without_blocking_new_messages`
- `tests/unit/queue/test_queue_store.py::test_record_actual_text_does_not_release_live_delivery`（sending / confirming）
- `tests/unit/text/test_typing.py::test_typing_steps_respect_interval_and_one_final_enter`（默认 / 显式间隔）

测试按项目约定只保存在本地 `tests/`，该目录不入 Git。测试使用临时 SQLite、假窗口、假剪贴板和本机 HTTP 替身；未发真实微信，未重启现有服务。

架构图组件和连线不变；`architecture-notes/delivery-pump.md` 补充批次 done 与送达确认的区别。没有 API、数据表、配置或前端改动。
<!-- end-migrated-part: doc-b664511b293d11 -->

<a id="doc-0c3db1f926d782"></a>

### 知识图谱落地影响分析

来源：`llm wiki/wxbot/impacts/2026-10-31-knowledge-graph-bootstrap.md:1`。

```yaml
type: impact
status: completed
date: '2026-10-31'
```
### 知识图谱落地影响分析

#### 需求与初建依据

需求：实现用户提供的 Markdown 项目图谱方案，文件放在 `llm wiki/`。初建前仅有 `llm wiki/wxbot/.obsidian/`，无可查询词条，故先读 README、AGENTS 和消息处理源码建档。实施方案 [design](wxbot.md#doc-ba7d4d46f1c73f)，步骤 [plan](wxbot.md#doc-f68e362b618ab8)，覆盖界限 [coverage](wxbot.md#doc-3d945de7c38143)。

#### 实际修改范围与调用方

- 根 `AGENTS.md:28` 接入查图、影响分析、raw、模型整合和命令入库纪律。
- 根 `README.md:611` 增加项目入口和命令，不重复项目运行说明。
- [modules/wiki](wxbot.md#doc-ed5d88ddcd1b47) 记录本地命令的准确代码位置；其唯一共享路径依赖是 `src/common/paths.py:29` 的 REPO_ROOT。
- [modules/wiki](wxbot.md#doc-ed5d88ddcd1b47) 及 26 个其它词条、7 个模板、索引、日志和证据快照均在既有库内。保留 Obsidian 个人设置。

#### 接口、前端与数据库

业务 HTTP/DTO、SQL schema、前端源码/构建产物均未修改。本次只读代码建立 [apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f) 以及三个队列表映射。图谱脚本不读取真实数据库、运行时配置或认证。

#### 验证与风险

CLI 回归使用临时库，详见 [verification](wxbot.md#doc-951820f4d5f621)。机器检查不能替代模型读代码；语义盲区见 [coverage](wxbot.md#doc-3d945de7c38143)。来源完整文件摘要对无关修改也敏感，需要后续核对。脏工作树既有其它变更，本次建档不代表那些变更的验证。

不启动、停止或重启服务，不发送微信，不调用模型或网络。回滚可移除本次知识目录新增资产并撤销 AGENTS/README 中本段入口，保留此前已有 `.obsidian` 设置和其它用户工作。历史修改记录不能为了回滚而改写。

#### 修改记录

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)
<!-- end-migrated-part: doc-0c3db1f926d782 -->

<a id="doc-6981deab6390ae"></a>

### 开发文档与技术基线口径核对

来源：`llm wiki/wxbot/impacts/2026-11-03-development-doc-baseline.md:1`。

```yaml
type: impact
status: verified
date: '2026-11-03'
```
### 开发文档与技术基线口径核对

#### 范围和核对结果

- 根 README、requirements 注释、前端包描述、Vite 注释与两个 Python 模块说明需要对齐；不改业务逻辑。
- 当前源码采用 src/ 布局；butler/README.md、PROJECT_MEMORY.md、旧示例 TOML 与嵌套包目录已不存在，不重建旧入口。
- 安装配置来自 src/butler/defaults.py，经 runtime/install_wizard.py 生成 config.butler.toml、config.wxbot.toml、config.log.toml；不能复制实际配置或凭据来造示例。
- 生产默认 model.backend=butler。Butler 后端可使用 Hermes、OpenAI 兼容 API 等；wxbot 直接适配器是另一个层级，仅保留旁路调试与旧配置兼容。
- 发送正文通过 TypingSession + ClipboardLease + Ctrl+V，默认 chunk_interval=0.25 秒。此次仅更正文档，不执行微信操作。
- heartbeat/ 当前含受版本控制的辅助脚本，不把整个目录当成运行残留忽略或删除。
- 核对时正式目录在 codex-butler-distribution，开发 worktree 在 codex/grok-setup 且多一个 WEB-001 提交；不能把“两个 tip 同 SHA”写成长期事实。实际运行进程加载版本不在本轮核验范围。
- 原目录 .venv 的 common.paths 实际来自开发 worktree；本轮图谱操作显式传 --repo-root 绑定当前仓库，不把另一个工作树的结果当作当前证据，不自动修改可编辑安装或运行服务。

#### 影响面、调用方与契约

安装消费者是 setup/install_wizard；正文发送消费者是 wxbot UI 主线程；前端产物由 src/dashboard/http.py 在 /app/ 提供。只改变说明、注释与 package description，配置值、HTTP/API/DTO、数据库及迁移、前端交互、异步任务均不变。

#### 图谱与验证

新增开发基线概念页，与 modules/wiki 互相链接；复核 README 来源行号与完整文件摘要。原图谱未覆盖工作树基线和历史布局区别，本次补充。

验证依赖与锁文件不变、Python 非文档 AST 不变、Vite 非注释内容不变、package.json 除 description 外不变，并运行图谱 ingest/lint 与 git diff --check。无需重启服务、真实发送、模型调用或发布打包；回滚仅需撤销本轮文档/注释/元数据与配套图谱差异。
<!-- end-migrated-part: doc-6981deab6390ae -->

<a id="doc-1002b3869f9b4f"></a>

### 主目录、main 与 Python 环境统一

来源：`llm wiki/wxbot/impacts/2026-11-04-root-workspace-unification.md:1`。

```yaml
type: impact
status: verified
date: '2026-11-04'
```
### 主目录、main 与 Python 环境统一

用户要求将最新代码和环境统一到主目录。操作前主目录为 detached 7a2ccd0，最新 main 为 a1f40c3；主目录自己的解释器通过可编辑安装误导入另一个 worktree。

#### 影响面与处置

- 主目录接管 main a1f40c3；另一个 worktree 解除 main 分支占用、保留原提交与目录。
- 原有 14 处文档、注释和图谱修订先备份并保存到恢复 stash，再基于 Git clean/smudge 规则与 main 三方合并；保留 main 的语音功能与图谱历史，没有整文件覆盖这些新增内容。
- 使用主目录自己的 .venv 离线执行本项目可编辑安装，仅重装 wxbot 项目包，不同步或升级第三方依赖。
- 前后端 API/DTO、数据库字段和迁移均不涉及；原有两个 Python 模块修订仍只修改模块说明，合并后的执行 AST 与 main 相同。
- 本机配置保持原字节，数据和认证不复制、不合并；没有调用模型、真实投递、启动或重启服务。

#### 调用方与核验边界

`src/common/paths.py:23` 根据实际导入位置确定 REPO_ROOT；三个应用包、管理台静态资源和默认配置入口共同依赖它。须从仓库外使用主目录解释器验证，避免当前目录或测试 sys.path 掩盖错误安装。

`README.md:125` 的基线流程与 [concepts/development-baseline](wxbot.md#doc-f0b302749d6eb3) 继续适用。默认配置来源、模型链路和发送实现均已对照最新 main 复核；`src/dashboard/http.py:88` 的托管锚点随版本修正。

#### 风险与回滚

原有未提交修订与 Git 历史保留本机备份，另外保留恢复 stash。运行数据未移动，无数据库回滚步骤。若需要撤销目录归属，应先保护当前修订，再调整分支占用和可编辑安装；不能通过删除工作目录或复制其他安装的凭据来回退。

整合完成只证明后续新进程的代码和环境来自主目录，不证明既有服务已加载此版本；服务由使用者自行决定启停。

#### 本轮核验

仓库外隔离导入、32 个 Python 包依赖完整性、前端锁文件版本、CLI 帮助、前端独立构建和假数据 smoke 均通过。完整离线回归为 1472 通过、3 项既有失败，失败用例与统一前相同。本机配置内容保持一致，未修改业务执行逻辑；具体处置见 [raw/changes/2026-11-04-root-workspace-unification](wxbot.md#doc-b44eb256c557c6)。
<!-- end-migrated-part: doc-1002b3869f9b4f -->

<a id="doc-a371c9f059b5c8"></a>

### 四项历史回归失败核对

来源：`llm wiki/wxbot/impacts/2026-11-07-stale-regression-tests.md:1`。

### 四项历史回归失败核对

用户已授权修复四个测试失败。当前源码和既有通过测试一致，失败用例仍断言旧合同；修复仅涉及本地测试与开发文档。

#### 原因与依据

1. `tests/integration/test_portable_install.py:45` 固定期望 6 个技能。manifest 覆盖 roles/tools，当前有 7 个 SKILL.md，含已实现的 IndexTTS。改为核对实际技能是否完整导出及核心技能路径，保留目录边界、引导入口、MCP 和协议断言。
2. `tests/unit/queue/test_queue_admin.py:58` 仍期望 uncertain 之后继续第三段。`src/wxbot/queue_store.py:639 finish_delivery` 和 `delivery_policy.py:5 _end_reply` 已采用“保留待核对段、停止本轮余段”的规则。分别验证 CLI 确认与显式重试，只操作选中项，不复活被停止的后续段。
3. `tests/unit/queue/test_queue_store.py:182` 在 recover 后要求旧批次继续阻塞。`queue_store.py:717 recover` 将未知投递保留为 uncertain/detached，并关闭旧轮，放行新收件。`record_submitted_text` 只登记正文，不改变状态；补活跃 sending/confirming 的相反用例，确保实际发送中仍阻塞。
4. `tests/unit/text/test_typing.py:46` 使用缺省配置却要求 0.5 秒间隔。`src/wxbot/config.py:33 validate_typing_config`、`src/butler/defaults.py:13 wxbot_defaults` 和 README 均为 0.25 秒。参数化验证默认 0.25 与显式 0.5 秒，保留输入内容、单次回车和剪贴板恢复断言。

#### 影响范围与风险

生产 Python、HTTP/DTO、前端、数据库/迁移、异步任务均不变。ARCHITECTURE.html 已复核，没有组件、接口或数据流变化；在调度器节点 Markdown 补充状态含义。
测试使用临时库、假 UI/剪贴板，不发送微信、不重启服务。
风险是修改预期掩盖回归，因此必须保留精确断言，并增加活跃任务阻塞、显式间隔和选中段重试的对照用例。
回滚本地测试改动及本次文档即可，不涉及数据回退。
<!-- end-migrated-part: doc-a371c9f059b5c8 -->

<a id="doc-f0c0814f02ebe4"></a>

### 项目知识图谱首批建档与维护闭环

来源：`llm wiki/wxbot/raw/changes/2026-10-31-knowledge-graph-bootstrap.md:1`。

```yaml
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
```
### 项目知识图谱首批建档与维护闭环

#### 目标与背景

按用户提供的方案实现可持续维护的 Markdown 知识图谱。使用已有 llm wiki/wxbot Obsidian 库，与项目一起版本化；不创建另一套运行时知识或服务。初建前无词条可查询，先读 README/AGENTS 和匹配源码，影响分析见 [impacts/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-0c3db1f926d782)。

#### 文件与代码位置

- `AGENTS.md:28`：开发模型改前查询、改后记录/整合/入库的纪律；保留已有 Hallmark 等规则。
- `README.md:611`：图谱目录、操作入口与命令。
- `llm wiki/wxbot/scripts/wiki.py`：Wiki 读取、结构检查、证据快照；准确行号及 ingest/query/main 位置以 [modules/wiki](wxbot.md#doc-ed5d88ddcd1b47) 为准。
- `llm wiki/wxbot/`：27 个 modules/apis/tables/symbols/concepts 词条、7 个模板、guide/coverage/design/plan/verification、影响分析、索引、日志与 ingest-state.json。词条逐项携来源路径、行号和锚点；完整词条范围见本记录 pages。
- `src/butler/server.py:308`、`src/butler/agent/core.py:205`、`src/wxbot/queue_store.py:330` 等仅作为核对来源，未修改它们。

本次基于脏工作树快照建档，不替已有源码变更追认作者/目的或验证结果。指定的 knowledge/资料库/README.md 在本安装不存在，未使用不存在的外部知识。

#### 接口与字段

不涉及业务 HTTP/DTO 变更。新增开发命令 query/change/ingest/lint/status；语义抽取由模型完成，CLI 只检索、检查和登记。词条元信息 sources 是 path/line/anchor 对象列表，changes 指向追加 raw。calls/called_by 表示已核对关键关系，depends_on 只用于显式模块依赖，不等于全部静态调用分析。

#### 数据库与迁移

不涉及业务数据库变更或运行时迁移，不读真实数据库。三个队列表按 queue_schema.py 的初始建表与升级补列建立最终结构说明；额外的 ingest-state.json 只是开发证据台账，存归一化文本摘要和来源路径，不存业务内容。

#### 前端消费点

不涉及前端实现改动或 dist 重建。只读 WorkflowView.vue:356 和 QueueView.vue:248 等消费点，将它们链到管理台 API。前端契约不是另造 TypeScript DTO；项目实际采用 Vue/JS 消费字段。保留既有 Obsidian 配置，忽略个人工作区/缓存。

#### 测试与异步任务

新增本地 tests/unit/test_project_wiki.py，以临时库执行真实 CLI。最终 20 项通过、1 项因无法创建真实 Windows 目录联接而跳过；另有确定性路径解析回归验证拒绝逻辑，详见 [verification](wxbot.md#doc-951820f4d5f621)。首次失败来自命令尚未实现，随后逐项完成。审查修复来源/词条路径重定向和历史来源丢失问题，增量更新也已测试。工具不调模型、服务、调度器或消费者，没有新增运行任务。

整库回归已有多项失败并在约 10% 后停滞，中止本次测试后用 --maxfail=1 定位：53 passed / 1 failed，失败在 test_contact_migration.py:412 的 nonlocal deepseek 安装用例；不宣称整个工作树通过。

#### 风险与回滚

首批完整覆盖消息处理核心，其余模块只做概览，缺口见 [coverage](wxbot.md#doc-3d945de7c38143)。完整来源文件摘要对无关行修改也提示复核；机械 lint 无法证明接口语义、遗漏调用方和业务规则正确。避免并发写图谱；同一记录已入库后不可改写，有错追加 supersedes 更正记录。

本次未重启服务、未发微信、未读凭据/运行数据，未提交或发布。回退本次新增知识资产及 AGENTS/README 新增入口时保留已有 Obsidian 设置和用户其它改动；历史记录不静默改写。待办：逐模块补齐身份/提醒/Telegram 等细节；整库失败由相应功能任务处理。
<!-- end-migrated-part: doc-f0c0814f02ebe4 -->

<a id="doc-4d0e5fc0ed39d9"></a>

### 词条代码引用行号复核

来源：`llm wiki/wxbot/raw/changes/2026-11-01-citation-sweep.md:1`。

```yaml
type: change
title: 词条代码引用行号复核
pages:
- concepts/group-identity-evidence
```
### 词条代码引用行号复核

#### 目标与背景

上一份记录 [raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a) 入库后，`concepts/group-identity-evidence` 的 frontmatter 已把 `sync_users` 的引用改到 111，但正文「代码依据」段仍留 109。两份引用互相矛盾，且插入行后需要确认其它词条没有同类漂移，因此做一次机械核对并补本记录登记词条变更。

#### 文件与代码位置

- `llm wiki/wxbot/concepts/group-identity-evidence.md`「代码依据」段：`src/wxbot/inbox.py:109` 改为 `src/wxbot/inbox.py:111`（`def sync_users(` 实际位置）。
- 复核范围：`llm wiki/wxbot/` 下各词条中所有 `- \`path:line\` — \`…\`` 形式的正文引用，逐条比对「该行是否包含该锚点」。
- 复核结果：命中 6 条差异，其中 5 条是核对脚本的误报——`apis/dashboard-knowledge.md` 两条把代码后的「（GET）」「（POST）」一起当成锚点，`modules/web.md` 一条用 `…` 省略了锚点，`concepts/unread-capture-retry.md` 三条写的是说明文字而不是锚点。真实漂移只有 `sync_users` 这一处。
- 脚本为一次性核对工具，不进仓库。

#### 接口与字段

不涉及。

#### 数据库与迁移

不涉及。

#### 前端消费点

不涉及。

#### 测试与异步任务

不改代码，不新增测试。功能测试结果沿用 [raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)：`tests/unit/wxbot`、`tests/unit/text`、`tests/unit/queue`、`tests/unit/media`、`tests/butler/identity` 只剩 3 个与本轮无关的既有失败。本记录只做图谱引用核对。

#### 风险与回滚

纯文档改动，回滚即把行号改回旧值。机械核对只能证明「该行包含该子串」，不能证明语义正确；语义仍需对照源码阅读，漂移也可能出现在锚点相同但上下文已变的情况。
<!-- end-migrated-part: doc-4d0e5fc0ed39d9 -->

<a id="doc-f9d149494a6267"></a>

### 统一当前开发基线、配置来源与发送实现文档

来源：`llm wiki/wxbot/raw/changes/2026-11-03-development-doc-baseline.md:1`。

```yaml
type: change
title: 统一当前开发基线、配置来源与发送实现文档
pages:
- concepts/development-baseline
- modules/wiki
```
### 统一当前开发基线、配置来源与发送实现文档

#### 目标与背景

逐项核对用户列出的八项旧说明，以当前工作分支源码为准纠正文档、模块说明和前端元数据；不重建已退场的包或文档。
当前根目录为 codex-butler-distribution @ 7a2ccd0；开发 worktree 的 codex/grok-setup @ db26164 多一个 WEB-001 提交。
此处仅为核对快照，不把分支名、两个 tip 同 SHA 或进程已加载版本当作长期事实。

实际处置：
1. butler/README.md 与 PROJECT_MEMORY.md 已不存在；根 README 记录当前 src/ 布局和历史说明的边界。
2. config.butler.example.toml 等示例文件已不存在；根 README 改为默认值／安装向导生成，明确实际三个配置文件名。
3. 明确正文使用剪贴板租约 + Ctrl+V + 读回校验，默认分批间隔从旧说明 0.5 秒更正为代码的 0.25 秒。
4. 区分生产默认 wxbot→Butler 与 wxbot 直接后端旁路；不把 Butler 自身的 provider 误标为调试功能。
5. 旧嵌套包目录当前不存在，不执行删除；heartbeat/ 当前含受版本控制的辅助脚本，保留其源码，不整目录忽略。
6. requirements.txt 删除“整个 Butler 无第三方依赖”的旧注释，依赖声明和版本约束不变。
7. web/package.json 描述、Vite 配置注释和流水日志模块说明统一指向 src/dashboard。
8. 新增工作树、SHA、修改状态、解释器路径与 REPO_ROOT 核对流程，正式／开发目录分叉时重新核对差异。

额外发现原目录 .venv 的 common.paths 实际导入自开发 worktree；早期未显式指定根目录的图谱查询结果不能作为当前仓库证据。
后续查询、change、ingest、lint 均显式传 --repo-root D:/work/code/wxbot；未修改可编辑安装，不把工具根目录限定当作运行环境修复。

#### 文件与代码位置

- README.md：总览、生产默认与旁路、开发基线、配置来源、正文发送和维护边界。
- requirements.txt：仅头部和 tomlkit 行注释；所有依赖项不变。
- src/wxbot/config.py:1：模块说明改用实际 config.wxbot.toml；load_config 在 :110 的逻辑不变。
- src/butler/runtime/flowlog.py:1：仅模块说明中的管理台名称与解析器路径。
- web/package.json:6：仅 description；web/vite.config.js 仅更正两处注释。
- llm wiki/wxbot/concepts/development-baseline.md：补齐原图谱中的工作树／解释器基线覆盖缺口。
- llm wiki/wxbot/modules/wiki.md：互链、README 来源锚点和复核日期；coverage.md、index.md、changelog.md、ingest-state.json 随记录维护。
- 影响分析见 [impacts/2026-11-03-development-doc-baseline](wxbot.md#doc-6981deab6390ae)。

#### 接口与字段

不涉及 HTTP/API/DTO 或配置字段、默认值的改动；配置名、backend 层级和发送机制的说明对齐现有实现。
Python 模块执行 AST 去掉模块文档字符串后与 HEAD 相同；Vite 去掉整行注释后的执行配置相同。

#### 数据库与迁移

不涉及数据库、表、字段血缘或迁移；未读取真实配置、凭据、消息或业务数据。
未删除任何历史目录、看门狗脚本或运行产物，未改变 .gitignore。

#### 前端消费点

无 UI 或交互变更。package.json 除 description 外解析结果与 HEAD 相同；Vite 仅注释变化。
src/dashboard/http.py:84 的 WEBAPP_DIR 指向 web/dist，托管 /app/ 的事实未变。
构建输出写入 cache 下的临时目录，不覆盖已提交 web/dist；无新增依赖或前端字段。

#### 测试与异步任务

无新增测试、异步任务或后台进程。静态语义等价检查通过：两个 Python 模块执行 AST、Vite 执行配置、requirements 依赖项均不变。
package.json 仅 description 变化；pyproject.toml、uv.lock、web/package-lock.json、.gitignore 和已提交 web/dist 未变。
使用便携 Node 24，node --check web/vite.config.js、前端 build（临时输出）和既有假数据 smoke 均通过。
本轮不执行后端回归，不能宣称后端回归通过；业务逻辑未变且未启动服务或发送微信。
图谱 ingest/lint 与 git diff --check 为本轮交付检查，结果以实际工具输出为准。

#### 风险与回滚

风险是按历史资料、分支名或错误的可编辑安装识别基线；文档加入实际目录／提交／解释器核对，图谱操作显式指定当前根目录。
原目录 .venv 的绑定问题仍需独立处理，未静默修改运行环境。
回滚仅撤销本轮文档、注释、元数据和配套图谱记录的变更；无需数据库迁移或服务重启。
<!-- end-migrated-part: doc-f9d149494a6267 -->

<a id="doc-b44eb256c557c6"></a>

### 统一主目录 main 与可编辑安装绑定

来源：`llm wiki/wxbot/raw/changes/2026-11-04-root-workspace-unification.md:1`。

```yaml
type: change
title: 统一主目录 main 与可编辑安装绑定
pages:
- concepts/development-baseline
- modules/wiki
supersedes:
- raw/changes/2026-11-03-development-doc-baseline
```
### 统一主目录 main 与可编辑安装绑定

#### 目标与背景

用户明确要求将最新代码和环境统一到主目录。此前主目录停在旧提交并保留 14 处未提交文档修订，main 由开发 worktree 占用；主目录的可编辑安装又指向该开发 worktree。

本记录只接续旧记录“环境绑定尚未修复”的后续状态，不改写旧记录的历史核对事实，也不撤销其文档、配置来源及发送实现结论。

#### 文件与代码位置

- 主目录 Git 基线改为 main a1f40c3；开发 worktree 保留相同提交、改为 detached。
- 主目录 .venv 中重新离线安装当前项目包，修正可编辑安装指向；环境元数据为本机产物，不进入源码或图谱。
- 原有 14 处文档、注释与图谱修订经备份、恢复 stash 和三方合并保留；两个 Python 文件的执行 AST 与 main 相同。
- concepts/development-baseline：复核最新代码、修正 dashboard HTTP 来源锚点、记录环境核验与进程加载边界。
- modules/wiki：追加本记录、核对日期和相关概念说明。
- 影响报告：[impacts/2026-11-04-root-workspace-unification](wxbot.md#doc-1002b3869f9b4f)。

#### 接口与字段

不涉及 API、DTO 或配置字段变更。保留主目录本机配置的原字节；没有复制另一处配置或凭据。前端 package description 与 Vite 的已有修订仍只改变说明和注释。

#### 数据库与迁移

不涉及数据库、表、字段、数据迁移或合并。两个工作树各自的数据、认证和缓存均保留原位置；本记录不收录其内容、配置值或个人数据。

#### 前端消费点

沿用 main 已提交的 Vue 源码及 web/dist。使用主目录已有前端依赖进行独立输出构建和假数据 smoke；没有设计或交互变更，也不覆盖已提交构建产物。

#### 测试与异步任务

核验从仓库外以隔离模式导入 common、butler、wxbot、dashboard，均来自主目录 src/；REPO_ROOT 与解释器归属一致。检查依赖完整性、CLI 帮助、前端依赖、构建与 smoke，并运行主目录现有离线回归；具体结果追加在下方核验结果，不用旧测试结果冒充本轮通过。

没有新增测试用例、异步任务或后台服务；没有真实模型请求或微信操作。知识图谱巡检区分本次开发基线修订与 main 自带的待入库/漂移提示。

#### 风险与回滚

风险是跨工作树合并遗漏已有修订，或仅修改 Git 分支而留下错误导入。先完成原文件、Git bundle、恢复 stash 备份，再按 Git 文本过滤规则合并并从仓库外实测导入。

回滚依靠本机备份和恢复 stash，并重新绑定目标目录的可编辑安装；不需要数据库迁移。开发 worktree 保留，不执行目录删除或服务重启。

#### 核验结果

- 主目录为 main a1f40c3；原有 14 处修订全部保留，main 的语音代码与图谱历史未丢失。
- 从仓库外执行主目录 Python 的 -I 隔离导入：common、butler、wxbot、dashboard 与 REPO_ROOT 均归属主目录 src/；可编辑安装来源为主目录。
- uv pip check：32 个已安装包检查通过，兼容性无错误。前端直接依赖及 Vue 编译器版本与 package-lock.json 一致。
- Butler CLI 帮助正常；前端独立输出 build 与现有假数据 smoke 通过；git diff --check 通过。
- 首次受限沙箱回归因本地假服务器回环连接被拒绝而终止；同一失败用例在允许本地连接的环境中通过。随后主目录完整离线回归为 1472 通过、3 失败，失败用例与统一前相同，仍为队列旧断言及输入间隔默认值差异，没有新增失败。
- 本机配置文件内容摘要与操作前完全一致。未复制运行数据或认证，未启动或重启应用服务。
<!-- end-migrated-part: doc-b44eb256c557c6 -->

<a id="doc-1968450e794d2a"></a>

### Archify 节点详情加入 Markdown 文档按钮

来源：`llm wiki/wxbot/raw/changes/2026-11-07-archify-node-documents.md:1`。

```yaml
type: change
title: Archify 节点详情加入 Markdown 文档按钮
pages:
- concepts/architecture-node-notes
- concepts/development-baseline
- modules/wiki
```
### Archify 节点详情加入 Markdown 文档按钮

#### 目标与背景

用户要求对比根目录 ARCHITECTURE.html 与现有 Archify 图，把节点 Markdown 功能接入后者，在既有节点弹窗增加一个小按钮。复用原有 architecture-notes 文件，保留节点和连接。当前工作目录 D:/work/code/wxbot，分支 codex/index-tts-skill，HEAD 20fc624bcf09e221079edd498fac85a5f2c1404f，工作区原有未提交工作全部保留。

#### 文件与代码位置

- 交付页 `.archify/architecture-wxbot-20261107-201947/wxbot.html:5673` 注入文档按钮，`:15013` 起加入独立主题样式、dialog 与脚本；读取 `:15145`，保存 `:15249`。
- 同目录 `node-notes.extension.html` 保存可重复应用的扩展源；`apply-node-notes.py` 幂等注入，并保留首次应用前 HTML。
- 原图 `ARCHITECTURE.html:294–503` 提供编辑器参考；原图自身和已有 Markdown 文件均未修改。
- README.md:859 追加使用说明。三个图谱词条核对 README 原锚点，更新本功能及来源；coverage/index/changelog/ingest-state 随入库更新。

#### 接口与字段

不涉及 HTTP API/DTO 或业务字段。浏览器本地新增 #btn-node-note；节点 ID 通过固定映射找到 Markdown 文件键。web 与 dashboard 共用 dashboard.md；新语义节点使用 model-backends、identity-tools、knowledge-vault、configuration。仅读取 architecture-notes，目录选择必须验证根目录 ARCHITECTURE.html。保存复用独占 writer、前后内容复核与失败时保留草稿。

#### 数据库与迁移

不涉及数据库、表字段或迁移。该页面只通过用户授权的 File System Access 句柄读写项目 Markdown；不读 runtime 配置、消息、凭据或数据库。

#### 前端消费点

仅独立 HTML：原生节点详情显示文档按钮，点击打开 Markdown 原文弹窗。弹窗是 focus-chip 子节点，避免查看器捕获阶段的外部点击逻辑清除选中状态。隔离编辑器快捷键，关闭后恢复焦点。多节点和关系选择隐藏文档按钮。深浅主题和打印状态使用本地样式适配。不改 web/，无 npm build/smoke 或 Hallmark web 页面工作流。

#### 测试与异步任务

- 先运行浏览器用例确认缺少文档按钮的预期失败，再实现功能。
- 同目录 node-notes.test.cjs 使用隔离无头 Edge 和内存目录/文件句柄：权限取消/拒绝、选错根目录、文本安全预览、读取/保存、全部 12 个节点映射、授权复用、新文件延迟创建、外部改动冲突、草稿保护、焦点恢复、多选/关系状态隐藏、深浅主题、弹窗居中、窄窗口、快捷键隔离、不支持浏览器与无页面异常均通过。
- 截图人工检查小按钮和居中弹窗；当前字节摘要记录 node-notes-verification.json。原生成回执只对应扩展前字节，不宣称覆盖扩展。
- 幂等应用及字节比对通过：除小按钮和完整扩展片段外，原 HTML 不变；再次应用字节不变，浏览器回执摘要与最终页一致。
- 不涉及业务后台任务、服务重启、真实微信发送或真实笔记写入。测试全部使用内存假数据。
- 变更前 wiki lint 已有两个未入库历史记录：2026-11-03-feat-voice-002-indextts、2026-11-03-indextts-enqueue-media；本次不擅自入库这些历史工作。

#### 风险与回滚

浏览器需 Edge/Chrome 文件系统 API 和用户选择项目目录授权；读取失败、选错目录、外部改动和未保存草稿有提示。权限仅在当前页面会话复用。原功能的文件竞态边界沿用，未声称浏览器文件写入与外部编辑器间具备跨进程事务。未来重新渲染会移除扩展，运行 apply-node-notes.py 可恢复；若查看器节点详情结构改变，脚本明确失败，须先核对插入点。回滚用同目录 wxbot.before-node-notes.html 恢复，保留 architecture-notes 中的用户文档。
<!-- end-migrated-part: doc-1968450e794d2a -->

<a id="doc-7574510a1cf96f"></a>

### 精简架构图底部区块

来源：`llm wiki/wxbot/raw/changes/2026-11-07-architecture-diagram-trim.md:1`。

```yaml
type: change
title: 精简架构图底部区块
pages:
- concepts/architecture-node-notes
```
### 精简架构图底部区块

#### 目标与背景

从根目录 HTML 架构图移除「主动推送、后台与可选接入」和独立的「发件分流」区块。

#### 文件与代码位置

`ARCHITECTURE.html:70` 收短画布，图例移至管理与存储区块下方。
`ARCHITECTURE.html:79` 起保留主图节点，`ARCHITECTURE.html:272` 是节点文档对话框。

#### 接口与字段

无 HTTP 或 DTO 变更。保留节点的 `data-note` 沿用原键，仍对应已有文件。

#### 数据库与迁移

不涉及。

#### 前端消费点

根目录架构图显示 24 个可点击节点。主图保留文字、语音与文件发件队列，以及语音合成的 IndexTTS 节点。

#### 测试与异步任务

解析 SVG，确认区块已移除、主图节点存在且对话框及编辑脚本一致。无异步任务变更。

#### 风险与回滚

变更范围是文档展示。节点笔记文件保持原路径，回滚图形即可恢复隐藏的入口。
<!-- end-migrated-part: doc-7574510a1cf96f -->

<a id="doc-65d1db0ccb5dda"></a>

### 架构图节点文档使用说明与开发基线复核

来源：`llm wiki/wxbot/raw/changes/2026-11-07-architecture-node-notes-readme.md:1`。

```yaml
type: change
title: 架构图节点文档使用说明与开发基线复核
pages:
- concepts/development-baseline
```
### 架构图节点文档使用说明与开发基线复核

#### 目标与背景

为架构图的新节点文档入口补充打开、授权及保存路径说明。功能记录见 [raw/changes/2026-11-07-architecture-node-notes](wxbot.md#doc-8790acdf96d310)。

#### 文件与代码位置

`README.md:848` 追加使用说明。复核 `README.md:125` 的开发基线和 `README.md:596` 的配置锚点，
两处原文与位置保持一致。

#### 接口与字段

不涉及 HTTP API 或 DTO；使用说明引用本地项目路径及节点键。

#### 数据库与迁移

不涉及。

#### 前端消费点

用户按 README 指引直接打开项目根目录的 HTML。

#### 测试与异步任务

使用图谱工具核对来源锚点和修改记录，无后台任务。

#### 风险与回滚

本记录对应使用说明和来源复核，移除说明不影响已经保存的文档。
<!-- end-migrated-part: doc-65d1db0ccb5dda -->

<a id="doc-8790acdf96d310"></a>

### 架构图节点 Markdown 文档

来源：`llm wiki/wxbot/raw/changes/2026-11-07-architecture-node-notes.md:1`。

```yaml
type: change
title: 架构图节点 Markdown 文档
pages:
- concepts/architecture-node-notes
- modules/wiki
```
### 架构图节点 Markdown 文档

#### 目标与背景

在项目根目录架构图上点击节点即可查看或编辑该节点的 Markdown 文件。

#### 文件与代码位置

`ARCHITECTURE.html:79` 起定义节点键；`ARCHITECTURE.html:357` 是查看编辑对话框。
`ARCHITECTURE.html:425` 读取文档，`ARCHITECTURE.html:494` 选择项目目录，
`ARCHITECTURE.html:527` 打开写入流。核对 `AGENTS.md:36` 的图谱章节位置并修正已漂移的导航锚点。

#### 接口与字段

不涉及 HTTP API 或 DTO。SVG 上的 `data-note` 映射到项目目录下的
`architecture-notes/<键>.md`；`data-component` 是节点显示名。
用户通过浏览器目录选择器授予文件读写权限。

#### 数据库与迁移

不涉及数据库、迁移或运行时数据；节点文档是独立的文本文件。

#### 前端消费点

独立的 `ARCHITECTURE.html` 打开并编辑 Markdown 源文，主图和发件分流的同名组件复用文档键。
Vue 管理台不消费节点文档。

#### 测试与异步任务

验证 SVG 的 35 个入口及 30 个文档键，并在 Edge 中检查交互。无新增后台任务。

#### 风险与回滚

本地读写依赖支持 File System Access API 的浏览器及用户目录授权。
检测到外部改写时保留编辑草稿。回滚页面交互后，已保存的 Markdown 仍可用文本编辑器打开。
<!-- end-migrated-part: doc-8790acdf96d310 -->

<a id="doc-df3c99eaa835f8"></a>

### 四项历史失败的测试合同修正

来源：`llm wiki/wxbot/raw/changes/2026-11-07-stale-regression-tests.md:1`。

```yaml
type: change
title: 修正四项过期回归预期并补边界对照
pages:
- modules/plugin
- concepts/delivery-state
- symbols/queue-store
- concepts/development-baseline
```
### 四项历史失败的测试合同修正

#### 目标与背景

用户要求修复重构前已存在的四个测试失败。改前独立复现 4 失败，核对源代码、README 和已通过的生命周期用例后确认全部是旧预期。保留当前生产行为，修正测试并增加边界对照。
影响报告：[impacts/2026-11-07-stale-regression-tests](wxbot.md#doc-a371c9f059b5c8)。

#### 文件与代码位置

- tests/integration/test_portable_install.py：由固定技能数量改为实际文件完整导出和核心技能路径校验。
- tests/unit/queue/test_queue_admin.py：参数化 CLI sent/retry，只恢复/确认选中段，前段与已停止后段保持完整记录不变。
- tests/unit/queue/test_queue_store.py：恢复后的待核对记录不阻塞新轮；补 sending/confirming 活跃任务登记正文后仍阻塞的对照。
- tests/unit/text/test_typing.py：分别验证默认 0.25 秒与显式 0.5 秒，保留粘贴正文、单次提交和剪贴板恢复。
- architecture-notes/delivery-pump.md 补充 done 与送达状态的区别；ARCHITECTURE.html 已复核，组件和连接未变化。
- tests/ 按仓库规则仅本地保存且不入 Git；图谱来源仍使用已核对的生产源码。

#### 接口与字段

不涉及生产接口或 DTO 变更。技能 manifest、队列 API、typing 配置合同保持原状。

#### 数据库与迁移

不涉及。现有 outbox/batches 状态、detached、submitted_text 和 resolve/retry 的血缘已复核；没有迁移或生产数据库访问。

#### 前端消费点

不涉及 web/ 源码、构建产物或管理台接口。架构节点笔记只是补充已有规则。

#### 测试与异步任务

四项原失败先复现；调整后扩展为 8 项用例全部通过。全项目 `python -m pytest` 为 1584 通过、0 失败、3 条原有 Pillow 弃用提示，耗时 121.72 秒。本次不新增异步任务。
用临时库、假窗口/剪贴板及随机本机 HTTP 替身；没有发真实微信，没有重启现有服务。

#### 风险与回滚

风险是通过放宽预期掩盖错误，因此保留精确状态/正文/先后顺序断言，并加入相反状态对照。
本次没有改产品行为。回滚四个本地测试文件和相关开发说明即可；不回滚其他已有未提交工作。
旧记录中四项失败是当时运行结果，保留历史；本记录说明之后的处理结果，不改写已入库 raw。
<!-- end-migrated-part: doc-df3c99eaa835f8 -->

<a id="doc-5fd0435fe93ef7"></a>

### 3.2 file｜代码文件（Controller / Service / Mapper / Vue 页面 / JS 等）

来源：`llm wiki/wxbot/raw/legacy/CLAUDE-wiki-schema.md:1`。

> **已废弃（2026-11-01）：仅作归档留证，不要按本文件执行。**
> 本文件是早期引入的另一套 Wiki 规范模板，与项目现行体系不一致。唯一有效的图谱维护规范是 [guide](wxbot.md#doc-9cf47fd939c877)（配合根目录 `AGENTS.md`）。
> 冲突时以 `guide.md` 和源码为准：现行体系允许修改 `src/`，图谱根为 `llm wiki/wxbot/`，实体类型只有 module/api/table/symbol/concept/change/impact，流程为 query → change → ingest → lint。
> 本文件中的 `/code-wiki/` 目录、files/enums/tasks/biz_flows/third_deps/risks 类型、`status`/`last_sync`/`static_analysis_uncertain` 字段与 shturl 日志，在本项目中均未实现。

---

```
# CLAUDE.md｜LLM Code Wiki 项目知识图谱 Schema 规范
> 本文件为 Claude Code 专用约束文档，强制遵循【LLM Code Wiki】范式。
> 核心铁则：**任何代码修改动作之前，必须先执行 Query 影响评估流程，从图谱获取改动范围、依赖链路、表信息；图谱为双向关联知识底座，源码为唯一可信源。**
> 禁止跳过图谱查询直接生成代码；禁止修改原始源码、DDL、原始接口文档；所有图谱变更、实体维护、链路更新必须遵守下面 Schema。

## 一、全局约束与行为规则
1. 可信源隔离：`/src/`（源码仓库）只读，你只能读取、解析、diff，**严禁写入、修改源码**。
2. 图谱根目录：`/code-wiki/`，所有Markdown实体、index.md、shturl 都放在这个目录。
3. 双向链路强制：所有关联关系必须双向维护。A调用B → A.depends += B，B.called_by += A；A读写Table X → A.read_write += X，X.read_by / write_by += A。单向链路属于缺陷，Lint阶段必须修复。
4. 人工备注隔离：页面内 `> 人工备注：` 区块属于人工业务经验，**自动更新时禁止覆盖、删除、修改**，仅追加新内容。
5. 废弃标记规则：实体下线/删除时，不直接删除Wiki页面，设置 `status: deprecated`，并填写 `deprecated_at`、`deprecated_reason`。
6. 索引与日志强制更新：每次 Ingest / Query归档 / Lint 修复完成，必须同步更新 `index.md` 和追加一条记录到 `shturl`。
7. 动态逻辑兜底：反射、动态SQL、动态路由、动态代理、MQ动态消费等无法静态解析的链路，自动标记 `static_analysis_uncertain: true`，并在页面备注提醒人工补全。
8. 输出优先级：需求变更先输出【影响评估报告】，经确认后，再生成代码修改方案。

## 二、目录结构约定
```

code-wiki/
├── index.md                # 全局实体索引
├── shturl.md               # 时序操作日志
├── modules/                # module 模块词条
├── files/                  # file 代码文件词条
├── apis/                   # api 接口词条（HTTP/RPC/MQ）
├── tables/                 # table 数据表 / 视图词条
├── enums/                  # enum 枚举词条
├── tasks/                  # task 定时 / 异步任务词条
├── biz_flows/              # biz_flow 业务流程词条
├── third_deps/             # third_dep 第三方依赖 / 外部服务词条
├── risks/                  # risk 历史风险、坑点、兼容问题
└── assets/                 # 附图、ER 图、时序图

```

## 三、实体类型、YAML Frontmatter 模板
> 所有页面头部必须带YAML，字段严格对齐；不存在的字段留空，不要删掉key。
> 关系字段全部填写内部链接 `[[xxx]]`

### 3.1 module｜模块/包
```yaml
---
type: module
name: ""
module_path: ""
belong_to: []
contains: []
depends: []
called_by: []
status: active # active / deprecated
last_sync: ""
static_analysis_uncertain: false
tags: []
---
# {{name}} 模块
## 概述
一句话业务描述。

## 子实体
- 包含文件：
- 包含接口：
- 包含数据表：

## 依赖说明
依赖模块：
被上游调用：

> 人工备注：
```

##### 3.2 file｜代码文件（Controller / Service / Mapper / Vue 页面 / JS 等）

```
---
type: file
name: ""
file_path: ""
belong_module: []
class_or_func: []
depends: []
called_by: []
read_tables: []
write_tables: []
apis_provide: []
apis_consume: []
tasks: []
status: active
last_sync: ""
static_analysis_uncertain: false
tags: []
---
# {{name}}
## 位置
`{{file_path}}`

## 内部核心方法/类
- 类名/方法：作用简述

## 对外提供接口
- [[api/xxx]]

## 消费的接口
- [[api/xxx]]

## 读写表
读：[[table/xxx]]
写：[[table/xxx]]

## 依赖文件/模块
- [[file/xxx]]

## 调用方
- [[file/xxx]]

> 人工备注：
```

##### 3.3 api｜接口（HTTP / RPC / MQ 生产消费）

```
---
type: api
name: ""
api_type: http # http / rpc / mq_produce / mq_consume / dubbo
path_or_topic: ""
method: ""
belong_module: []
provider: []
consumer: []
read_tables: []
write_tables: []
request_params: []
response_params: []
front_binding: []
status: active
deprecated_at: ""
deprecated_reason: ""
last_sync: ""
static_analysis_uncertain: false
tags: []
---
# {{name}}
## 基础信息
类型：{{api_type}}
地址/topic：{{path_or_topic}}
请求方式：{{method}}

## 入参
| 参数名 | 类型 | 是否必填 | 说明 |
|--------|------|----------|------|

## 出参
| 参数名 | 类型 | 说明 |
|--------|------|------|

## 提供方
- [[file/xxx]]

## 消费方
- [[file/xxx]]

## 读写数据表
读：
写：

## 绑定前端页面
- [[file/xxx]]

> 人工备注：
```

##### 3.4 table｜数据表 / 视图

```
---
type: table
name: ""
table_comment: ""
schema: ""
engine: ""
columns: []
indexes: []
relate_table: []
read_by: []
write_by: []
status: active
last_sync: ""
static_analysis_uncertain: false
tags: []
---
# {{name}}
## 表说明
{{table_comment}}

## 字段清单
| 字段名 | 类型 | 主键 | 非空 | 业务含义 |
|--------|------|------|------|----------|

## 索引
- 索引名：字段，唯一/普通

## 关联表
- [[table/xxx]]

## 读取来源（哪些接口/文件读这张表）
- [[api/xxx]]
- [[file/xxx]]

## 写入来源（哪些接口/文件写这张表）
- [[api/xxx]]
- [[file/xxx]]

> 人工备注：
```

##### 3.5 enum｜枚举

```
---
type: enum
name: ""
file_path: ""
belong_module: []
used_by: []
status: active
last_sync: ""
tags: []
---
# {{name}}
## 枚举值
| code | desc | 业务含义 |
|------|------|----------|

## 使用方
- [[file/xxx]]
- [[api/xxx]]

> 人工备注：
```

##### 3.6 task｜定时任务 / 异步任务

```
---
type: task
name: ""
cron_or_trigger: ""
belong_module: []
execute_file: []
read_tables: []
write_tables: []
depends: []
status: active
last_sync: ""
tags: []
---
# {{name}}
## 触发规则
{{cron_or_trigger}}

## 执行入口
[[file/xxx]]

## 读写表
读：
写：

## 依赖接口/服务
- [[api/xxx]]

> 人工备注：
```

##### 3.7 biz_flow｜业务流程

```
---
type: biz_flow
name: ""
flow_desc: ""
steps: []
relate_api: []
relate_table: []
relate_file: []
status: active
last_sync: ""
tags: []
---
# {{name}}
## 流程简述
{{flow_desc}}

## 步骤
1. 步骤1：调用 [[api/xxx]]，操作 [[table/xxx]]
2. ...

## 关联实体
接口：
表：
代码文件：

> 人工备注：
```

##### 3.8 third_dep｜第三方依赖、外部服务

```
---
type: third_dep
name: ""
vendor: ""
caller: []
interface_doc: ""
status: active
last_sync: ""
tags: []
---
# {{name}}
## 说明
外部服务、SDK、第三方接口。

## 调用方
- [[file/xxx]]
- [[api/xxx]]

> 人工备注：
```

##### 3.9 risk｜风险、坑点、历史兼容问题

```
---
type: risk
name: ""
risk_level: high # high / medium / low
relate_entity: []
symptom: ""
cause: ""
solution: ""
regression_point: []
status: open # open / fixed
last_sync: ""
tags: []
---
# {{name}}
## 风险等级：{{risk_level}}
## 关联实体
- [[api/xxx]]
- [[table/xxx]]

## 现象
{{symptom}}

## 根因
{{cause}}

## 处理方案
{{solution}}

## 回归检查点
-

> 人工备注：
```

#### 四、三大核心流程执行规范

##### 4.1 Ingest｜导入 & 增量同步图谱

触发条件：全仓扫描 / 指定模块 / 文件扫描 /git diff 增量同步 / 导入 DDL/OpenAPI
执行步骤：

1. 读取可信源（源码、SQL、openapi），AST / 静态解析识别全部实体
2. 提取元数据、签名、入参出参、读写表、调用关系
3. 新建 / 更新对应实体页面，填充 YAML 与正文
4. **双向回写所有关联关系**
5. 标记 `static_analysis_uncertain: true` 给动态逻辑
6. 更新 index.md
7. 在 shturl 追加一条 ingest 日志
8. 输出摘要：本次新增 / 更新实体数量、发现的动态无法识别点

> 
> 禁止：Ingest 阶段直接修改源码。

##### 4.2 Query｜需求变更评估（最重要，改代码前必跑）

触发条件：用户给出功能需求、改动关键字、变更需求
执行步骤：

1. 读取 index.md，检索匹配相关实体，沿着双向链路递归遍历依赖、调用、读写关系
2. 收集全部关联实体，输出标准化【影响评估报告】，固定包含下面栏目：
   - 需求简述
   - ✅ 需要改动的文件、精确路径、类 / 方法位置
   - ✅ 直接影响的上下游代码、调用方、被调用方
   - ✅ 前后端交互链路：前端页面、接口、入参出参
   - ✅ 涉及数据表、字段、读写行为（读 / 增 / 改 / 删）
   - ✅ MQ、定时任务、缓存、第三方依赖
   - ✅ 历史风险、同类变更记录、兼容提醒
   - ✅ 风险等级、回归范围建议
3. 将本次评估新识别到的链路、新增风险，归档写入对应实体页面
4. 更新 index.md
5. shturl 追加 query 日志
6. 等待用户确认评估报告，**用户确认后，才允许生成代码修改方案**

> 
> 禁止：跳过评估直接写代码。

##### 4.3 Lint｜图谱巡检、一致性修复

触发条件：定期巡检、版本上线前、用户手动触发
检查清单（逐条校验）：

1. 图谱记录的调用关系和源码事实不一致
2. 源码已删除，但图谱未标记 deprecated
3. 孤立实体：无入链、无出链
4. 单向引用，缺少反向关联
5. 字段注释、接口参数、读写标记缺失
6. 动态逻辑未标注 `static_analysis_uncertain: true`
7. risk 清单过期、已修复风险未更新 status
8. index.md 条目缺失、链接失效

执行步骤：

1. 对比源码可信源，批量检出问题
2. 输出巡检报告，区分【自动修复】和【需要人工确认】项
3. 自动修复安全项，更新实体页面、双向链路
4. 需要人工确认的问题，列出清单交给用户
5. 更新 index.md
6. shturl 追加 lint 日志

#### 五、index.md 格式规范

```
# 实体总索引
> 自动维护，不要手动大量修改

## module 模块
- [[modules/xxx]] | 简述 | 最后同步：xxx | 状态：active

## file 文件
- [[files/xxx]] | 简述 | module:[[modules/xxx]] | 状态：active

## api 接口
- [[apis/xxx]] | 简述 | type:http | 状态：active

## table 数据表
- [[tables/xxx]] | 简述 | schema:xxx | 状态：active

## enum 枚举
- [[enums/xxx]]

## task 任务
- [[tasks/xxx]]

## biz_flow 业务流程
- [[biz_flows/xxx]]

## third_deps 第三方依赖
- [[third_deps/xxx]]

## risk 风险清单
- [[risks/xxx]] | level:high
```

#### 六、shturl 日志格式规范

每条日志固定模板，追加式，不修改历史行

```
## [YYYY-MM-DD HH:MM:SS] ingest | 描述：xxx，新增：x，更新：x
## [YYYY-MM-DD HH:MM:SS] query | 需求：xxx，评估影响实体：xxx
## [YYYY-MM-DD HH:MM:SS] lint | 巡检：全量，自动修复：x，待人工确认：x
## [YYYY-MM-DD HH:MM:SS] manual | 人工修正：xxx
```

#### 七、标签 tag 推荐（统一标签体系）

`#high-risk` `#legacy` `#cache-related` `#mq` `#rpc` `#front` `#back` `#deprecated` `#dynamic-sql` `#reflection`

#### 八、禁止行为清单

- ❌ 跳过 Query 评估直接生成代码
- ❌ 修改原始源码、DDL、原始接口文档
- ❌ 覆盖人工备注区块
- ❌ 只维护单向链路
- ❌ 删除已经下线的实体页面，只允许标记 deprecated
- ❌ 把密钥、敏感业务数据写入图谱
<!-- end-migrated-part: doc-5fd0435fe93ef7 -->
