# Butler + wxbot + Codex

Windows 微信机器人：wxbot 负责收发与持久队列，Butler 负责用户、权限、记忆、心跳和提醒，Codex 负责角色对话与工具调用。

## 安装

先安装本仓库提供的 **butler-wechat** Codex 插件，再克隆项目：

```powershell
codex plugin marketplace add <本仓库的Git地址>
codex plugin add butler-wechat@butler-wechat-plugins
git clone <本仓库的Git地址> butler-wxbot
cd butler-wxbot
.\scripts\setup.ps1
.\.venv\Scripts\python.exe -m butler login
.\.venv\Scripts\python.exe -m butler doctor
```

要求 Windows、Python 3.14+、已登录的微信和可用的 Codex 账户。登录在使用者自己的机器人环境完成。
初始化生成本机 Token，默认空联系人、空绑定、关闭心跳；不会导入 Hermes 数据或覆盖现有配置。

## 运行

```powershell
.\.venv\Scripts\python.exe -m log.server --open
.\.venv\Scripts\python.exe -m butler.server
.\.venv\Scripts\python.exe -m wxbot.main
```

在 log 的「配置管理」设置机器人昵称、联系人，再在「角色与心跳」绑定角色和允许的 Skill。
配置完成后按页面提示自行重启。全部服务停止时，也可用 `python -m butler start` 一次启动。

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
- [微信 UI 与队列说明](README.wxbot.md)
- [综合新闻订阅、每日投递与状态记录](docs/NEWS_DELIVERY.md)
- [Telegram 联合早报文字转发到新闻分组](docs/TELEGRAM_NEWS.md)
- [原 Butler/Hermes 接口说明](butler/README.md)：仅用于旧后端兼容。

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe tools\release.py
```

发布包排除真实配置、认证、聊天数据和旧 Hermes 运维脚本。源码保留旧接口；当前配置没有
`agent.provider` 时继续使用 Hermes，新增安装由 init 默认选择 Codex。

微信 UI 自动化需要可访问的主窗口及未锁屏的电脑，不同版本可能需要校准控件。实际微信收发请由使用者确认后验证。
