# Butler + wxbot

Windows 微信机器人：wxbot 负责收发与持久队列，Butler 负责用户、权限、记忆、心跳和提醒，可选择本机 Codex 或已有智能体／模型 API。

## 安装

先安装本仓库提供的 **butler-wechat** Codex 插件，再克隆项目：

```powershell
codex plugin marketplace add <本仓库的Git地址>
codex plugin add butler-wechat@butler-wechat-plugins
git clone <本仓库的Git地址> butler-wxbot
cd butler-wxbot
.\scripts\setup.ps1
.\.venv\Scripts\python.exe -m butler doctor
```

要求 Windows、Python 3.14+、已登录的微信；选择本机 Codex 时需要可用的本人账户，并按向导提示运行 `python -m butler login`。
安装脚本进入 `python -m butler setup` 交互向导，选择接入方式、地址、端口和机器人昵称，确认后写入本机配置。
支持 Codex、Hermes、OpenClaw、Cursor、DeepSeek、已有 Butler、自定义 Chat Completions／Responses。
默认值来自代码，不需要复制配置模板。`python -m butler init` 保留为非交互、幂等初始化；两者均保留已有配置，不复制其他安装的数据。

## 运行

```powershell
.\.venv\Scripts\python.exe -m butler start
```

`start` 按 `config.wxbot.toml` 的 `[installation].mode` 启动：`local` 启动 Butler、log、wxbot；
`external` 和 `direct` 启动 log、wxbot。端口被占用时保留已有进程，不自动重启。
本机 Butler 新安装在 log 的「联系人」统一维护监听、群昵称、角色／心跳、订阅和记忆；联系人唯一来源为 `data/business.sqlite3`。
本机 Codex 模式可绑定角色、允许的 Skill 和心跳；直接模型模式不提供 Butler 记忆、提醒及业务工具。
外部 Butler 模式只通过配置的消息接口调用服务；本机管理台关闭远端账户、记忆与心跳管理，请使用远端自己的管理台。
直接模型／外部 Butler 模式继续在「配置管理」维护本机监听和昵称，远端身份与业务在远端管理。
既有本机 Butler 安装不会自动启用统一联系人。先运行 `python -m butler contacts-preview` 只读核对；
自行停止旧服务和后台写入者后，再运行 `python -m butler contacts-migrate --acknowledge-stopped`。
迁移保留原 uid／会话、监听开关、策略、订阅目的地和停用状态，同名联系人共享个人记忆并保留冲突来源。
[升级说明](docs/CODEX_INSTALL.md#升级现有安装) 包含备份、手动切换和回退步骤。

## 结构

| 模块 | 职责 |
|---|---|
| `plugins/butler-wechat` | 独立插件：安装引导、角色、功能 Skill、MCP 连接 |
| `butler/backends` | Codex SDK 适配、隔离 worker、会话恢复；保留 Hermes 手动回退 |
| `butler/business.py`、`butler/tools.py` | SQLite 业务记录和身份权限边界 |
| `butler/reminders.py`、`butler/heartbeat.py` | 提醒投递、随机心跳 |
| `wxbot` | 微信主窗口监听、群聊 @ 判断、收发队列和分批输入 |
| `log` | 可编辑配置、角色、队列、模型工具进度、记忆与提醒记录 |
| `data/` | 本机认证和运行数据，禁止提交 Git |

## 文档与验证

- [完整安装、故障排查、升级与旧部署切换](docs/CODEX_INSTALL.md)
- [插件和业务工具协议](docs/CODEX_PROTOCOL.md)
- [本次实现与验证、手动切换清单](docs/CODEX_VERIFICATION.md)
- [微信 UI 与队列说明](docs/WXBOT_UI.md)
- [固定用户身份、长期记忆、群上下文与真正 @](docs/USER_MEMORY.md)
- [综合新闻订阅、每日投递与状态记录](docs/NEWS_DELIVERY.md)
- [Telegram 联合早报文字转发到新闻分组](docs/TELEGRAM_NEWS.md)
- [Telegram 机器人收件到 Butler](docs/TELEGRAM_BOT.md)
- [Telegram 频道窗口转发 Skill、图文投递与人工核对](docs/TELEGRAM_RELAY_SKILL.md)
- [原 Butler/Hermes 接口说明](butler/README.md)：仅用于旧后端兼容。

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe tools\release.py
```

发布包包含代码默认值、安装向导和接口文档，排除全部配置 TOML、认证、聊天数据和旧 Hermes 运维脚本。源码保留旧接口；当前配置没有
`agent.provider` 时继续使用 Hermes，非交互 init 默认选择 Codex；setup 由使用者选择接入方式。

微信 UI 自动化需要可访问的主窗口及未锁屏的电脑，不同版本可能需要校准控件。实际微信收发请由使用者确认后验证。
