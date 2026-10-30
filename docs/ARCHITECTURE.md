# 架构：进程、边界与目录

> 从 `PROJECT_MEMORY.md` 抽出的架构描述；约定与踩坑记录仍留在 `PROJECT_MEMORY.md`。
> 以当前代码和 `config.*.example.toml` 为准。

## 进程与链路

三个本地进程，两条边：

| 进程 | 入口 | 端口 | 职责 |
|---|---|---|---|
| wxbot | `python -m wxbot.main` | 8765（外发 HTTP） | 微信主窗口监听、群聊 @ 判断、收发队列、分批输入；兼容独立窗口模式 |
| butler | `python -m butler.server --config config.butler.toml` | 8770 | 用户、权限、记忆、提醒、心跳与消息接口（`/v1/handle`、`/v1/push`…） |
| 管理台 | `python -m dashboard.server` | 8788 | 只读展示与配置编辑：配置、角色、队列、模型工具进度、记忆与提醒记录 |

也可以用 `python -m butler start` 按 `[installation].mode` 一次性拉起（`local` 三个进程，
`external`/`direct` 只有管理台与 wxbot）；端口被占用时保留已有进程，不自动重启。

主要链路：微信主窗口 → `wxbot` SQLite 收件/合并 → `POST /v1/handle`（butler 8770）→ 模型
（本机 Codex 或外部 Hermes/OpenAI 兼容服务）→ butler → SQLite 发件 → wxbot UI 主线程回复。
主动提醒链路：脚本/外部调度 → butler `/v1/push` → wxbot 外发服务（8765）→ 发件队列 → 微信窗口。

## 职责边界

- 窗口定位、轮询、消息差分、发送和 `/ping` 等通道命令属于 wxbot。
- 联系人身份、模型 Profile/uid、会话 id、补发、静默和 skill 决策属于 butler。
- 管理台只读运行事实、写配置文件；不启动业务进程，不替业务发消息。
- 群聊由 wxbot 按右侧人数标签识别；`[bot].mention_names` 决定机器人昵称；WeChat UIA 不暴露群昵称，
  wxbot 用左侧头像感知哈希生成 member_id，真实昵称在 `[wechat.group_sender.member_names]` 配，
  每批消息携 speaker/member_id 标签进入该成员的独立群会话。

## 目录地图

```
src/butler/    编排层：agent/ identity/ delivery/ runtime/ channels/telegram/ news/ backends/
src/wxbot/     UI 收发层：主窗口监听、收件箱、队列、发件与后端适配
src/dashboard/ 管理台 HTTP 服务：server.py + http/routes/api + 各 *_view / *_action
src/common/    跨包共用：REPO_ROOT（paths.py）与跨进程配置锁（config_lock.py）
web/           Vue 3 + Vite 管理台源码，构建产物 web/dist 由管理台在 /app/ 提供
plugins/       独立插件：安装引导、角色、功能 Skill、MCP 连接
scripts/       启动/运维脚本（栈启停、投递、提醒）
tools/         打包与探活脚本（release.py、probe_codex.py）
tests/         support/ unit/ butler/ dashboard/ integration/
docs/          本文档目录，入口见 INDEX.md
data/          本机认证和运行数据，禁止提交 Git
```

包都在 `src/` 下，靠 `pyproject.toml` 的可编辑安装导入：`python -m butler`、
`python -m dashboard.server`、`python -m wxbot.main` 均可在仓库外运行。

## 关键路径

- `src/butler/agent/core.py`：主流程、补发、模型调用、行动执行、出站推送。
- `src/butler/server.py`：HTTP 路由、Bearer 校验和状态探活。
- `src/butler/config.py`、`src/butler/identity/contacts.py`、`src/butler/agent/hermes.py`：
  配置、身份映射和 Hermes wire/session 语义。
- `src/butler/agent/router.py`、`src/butler/agent/skills.py`、`src/butler/delivery/pending.py`：
  路由/标记协议、skill 白名单、补发。
- `src/butler/identity/groups.py`、`src/butler/delivery/push.py`、`src/butler/runtime/flowlog.py`：
  分组推送与流水日志。
- `src/wxbot/main.py`、`state.py`、`wechat/chat_window.py`：主轮询、消息差分、窗口读写。
- `src/wxbot/outbound.py`：接收主动推送的 HTTP 队列服务；`src/wxbot/processor/` 是各后端适配器。
- `src/dashboard/server.py`、`web/`：管理台服务与 Vue 前端；`/` 302 到 `/app/`。
- `scripts/wechat_stack_ctl.py`：栈启停状态；`scripts/butler_reminder_*.py`：提醒创建/投递。

## 协议要点

- butler HTTP 接口都要求 `Authorization: Bearer <token>`：`GET /health`、`GET /v1/catalogue`、
  `POST /v1/handle`、`POST /v1/reset`、`POST /v1/push`，默认仅绑定 loopback。形状见
  [`MESSAGE_API.md`](MESSAGE_API.md) 与 `src/butler/server.py`。
- 调用 Hermes 时同时传 `X-Hermes-Session-Key`（长期身份/记忆归属）与 `X-Hermes-Session-Id`
  （同一段对话连续性）；只传前者可能每轮派生新会话，`/new` 或 `/重置` 会轮换会话 id。
- 模型行动标记 `<<butler:action {"skill":"...","args":{...}}>>` 由 `src/butler/agent/router.py`
  去除并交 `src/butler/agent/skills.py` 白名单执行；未知 skill 失败留痕。现有 catalog：
  `reminder.create/list/cancel`（本地实现）、`learn.card`、`quiz.next`（再委派模型）。
- 每条消息开始先认领补发队列，再调用模型；模型失败或静默时仍应送出已认领内容。
- 主动推送不调用模型且不改会话。`type=1` 指定联系人；`type=2` 按 `messageType` 从 groups JSON
  逐人发送，分组文件默认在 Hermes root 的 `cache/butler_groups.json`，每次推送重新读取。

## 配置与运行

- 单一 `pyproject.toml` / `requirements.txt` / `.venv`，声明 Python 3.14+；核心依赖
  `uiautomation`、`requests`、`pillow`，开发测试用 pytest，锁文件 `uv.lock`。
- 从 `config.butler.example.toml`、`config.wxbot.example.toml`、`config.log.example.toml`
  生成本地配置；含 token/key 的本地配置不要提交。也可直接跑 `python -m butler setup` 由向导写入。
- 管理台：`python -m dashboard.server --open`（默认 8788，`LOG_CONFIG` 可覆盖配置文件）。
- wxbot：`python -m wxbot.main`，默认保持微信主窗口打开（`[wechat].mode = "main"`）；独立模式需打开绑定窗口。
  UI 自动化要求窗口可见、不遮挡，机器不能锁屏；控件随版本变化时用 `tools/probe.py` 校准。
- 测试：`.\.venv\Scripts\python.exe -m pytest`（全离线）；分组见 `tests/`。
