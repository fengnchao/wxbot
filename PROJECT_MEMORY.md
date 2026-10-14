# 项目要点记忆

> 面向后续维护会话的速查文档。扫描日期：2026-10-14。以代码和配置模板为准；密钥、真实联系人和本机私有配置不记入本文。

## 项目定位

Windows 上的个人微信机器人，Python 项目，拆成两个本地进程：

- `wxbot/` 是 UI 收发层：通过 Windows UI Automation 读取独立聊天窗口、判断发送方、调用处理器并模拟发送。
- `butler/` 是对话编排层：提供 HTTP API，按联系人映射 Hermes Profile/uid，处理补发、会话、行动标记、提醒和主动推送。
- Hermes 网关提供模型与既有 skill runtime；默认地址/端口见 `config.butler.example.toml`（本地 8642）。
- 可选 `log/` 看板提供日志、任务和分组管理；`heartbeat/` 看门狗检查/重启进程；`scripts/` 提供启动、投递和提醒运维入口。

主要链路：微信独立窗口 → `wxbot` → `POST /v1/handle`（butler 8770）→ Hermes → butler → wxbot 回复。主动提醒链路为脚本/Hermes → butler `/v1/push` → wxbot 外发服务（8765）→ 微信窗口。

## 关键边界和协议

- 窗口定位、轮询、消息差分、发送和 `/ping` 等通道命令属于 wxbot；联系人身份、Hermes Profile/uid、会话 id、补发、静默和 skill 决策属于 butler。
- wxbot 通过 `wxbot/processor/butler.py` 把消息发给 butler；仍支持 `echo`、Hermes/OpenAI 兼容和 Ollama 后端，路由见 `wxbot/main.py`。
- 群聊监听通过 `[bot].bound_groups` 配置窗口标题，通过 `[bot].mention_names` 配置机器人昵称；仅处理以 `@昵称` 开头的其他成员文字消息，移除提及前缀后走同一处理器并在原群聊回复。
- butler HTTP 接口都要求 `Authorization: Bearer <token>`：`GET /health`、`GET /v1/catalogue`、`POST /v1/handle`、`POST /v1/reset`、`POST /v1/push`。默认仅绑定 loopback。处理接口形状见 `butler/server.py`。
- Hermes 调用同时传 `X-Hermes-Session-Key`（长期身份/记忆归属）和 `X-Hermes-Session-Id`（同一段对话连续性）。只传前者可能每轮派生新会话。`/new` 或 `/重置` 会轮换会话 id。
- 模型行动标记 `<<butler:action {"skill":"...","args":{...}}>>` 由 `butler/router.py` 去除并交 `butler/skills.py` 白名单执行；未知 skill 失败留痕。现有 catalog：`reminder.create/list/cancel`（本地实现）、`learn.card`、`quiz.next`（再委派 Hermes）。`<<butler:silent>>` 等标记用于静默。
- 每条消息开始先认领补发队列，再调用模型；模型失败或静默时仍应送出已认领内容。队列 schema 复用 Hermes Profile 下的 `pending_delivery.py`。
- 主动推送不调用模型且不改会话。`type=1` 指定联系人；`type=2` 按 `messageType` 从 groups JSON 逐人发送。分组文件默认在 Hermes root 的 `cache/butler_groups.json`，可由配置覆盖，每次推送重新读取。

## 重要路径

- `butler/core.py`：主流程、补发、Hermes 调用、行动执行、出站推送。
- `butler/server.py`：HTTP 路由、Bearer 校验和状态探活。
- `butler/config.py`、`contacts.py`、`hermes.py`：配置、身份映射和 Hermes wire/session 语义。
- `butler/router.py`、`skills.py`、`pending.py`：路由/标记协议、skill 白名单、补发。
- `butler/groups.py`、`push.py`、`flowlog.py`：分组推送与流水日志。
- `wxbot/main.py`、`state.py`、`wechat/chat_window.py`：主轮询、消息差分、窗口读写。
- `wxbot/outbound.py`：接收主动推送的 HTTP 队列服务；`wxbot/processor/` 是各后端适配器。
- `log/server.py`、`log/index.html`：看板服务和前端；看板直接读取配置/日志/任务数据。
- `scripts/wechat_stack_ctl.py`：栈启停状态；`scripts/butler_reminder_*.py`：提醒创建/投递；`heartbeat/`：进程监控。
- `tests/`：离线测试，包括主流程不变量、HTTP/Hermes 传输、消息状态、分组、推送和任务归属。

## 配置与运行

- 根目录单一 `pyproject.toml` / `requirements.txt` / `.venv`。项目声明 Python 3.14+；依赖主要是 `uiautomation`、`requests`、`pillow`，开发测试用 pytest。锁文件为 `uv.lock`。
- 从 `config.butler.example.toml`、`config.wxbot.example.toml` 复制生成本地配置；两者分开且含 token/key 的本地配置不要提交。
- 启动 butler：`\.venv\Scripts\python -m butler.server --config config.butler.toml`；`--status` 做配置和 Hermes 探活。
- 启动 wxbot：`\.venv\Scripts\python -m wxbot.main`。先在微信打开绑定联系人对应的独立聊天窗口；UI 自动化要求窗口可见、不遮挡，机器不能锁屏。控件变化时用 `tools/probe.py` 检查校准。
- 测试命令：`\.venv\Scripts\python -m pytest`（全离线）；此轮扫描未运行测试。
- butler 的本地提醒执行器从 `[dispatch].script_dir` 调 `butler_reminder_create.py`；补发程序从 `{hermes.root}/profiles/<profile>/skills/messaging/wechat-reminder/scripts/pending_delivery.py` 复用 Hermes 队列。

## 维护注意

- 此仓库的 UI 自动化是非官方方式，存在账号风险；发送依赖剪贴板和窗口焦点。
- `config.*.example.toml` 是安全文档/示例来源；运行时配置可能含真实密钥，不要在日志、记忆或提交里复制秘密。
- `butler/README.md` 的示例含旧机器路径和过期目录/文件名（例如旧的根目录、`config.example.toml`、`kmg/`），实际操作请以根目录 README、当前代码和 `config.*.example.toml` 为准。
- `butler/skills.py` 的 `HERMES_HINT` 提供行动协议，但 README 记录提示词仍需由 Hermes Profile 的 SOUL/skill 引导模型发标记。
- `reminder.cancel` 直接更新 Hermes Profile 下 `reminders.json`，再原子替换 cron `jobs.json`；维护时注意提醒记录与调度任务要保持一致。

## 扫描时工作区状态

扫描时 `git status --short` 显示大量已修改、删除和未跟踪文件，涉及根目录重组（原 `wxbot/`、`wxbot-util/` 内容移至根目录布局等）。这些改动属于当时工作区现状，本次只新增本记忆文档；后续编辑前先检查 git diff，避免覆盖或误认为这些变化是新产生的。
