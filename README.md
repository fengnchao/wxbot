# wxbot / Butler

Windows 微信机器人：wxbot 负责收发与持久队列，Butler 负责用户、权限、记忆、心跳和提醒，
可选择本机 Codex 或已有智能体／模型 API；管理台提供实时工作流、队列核对与配置编辑。

## 安装

要求 Windows、Python 3.14+、已登录的微信；选择本机 Codex 时需可用的本人账户。
插件与项目使用同一个 Git 仓库地址。

```powershell
codex plugin marketplace add <本仓库的Git地址>
codex plugin add butler-wechat@butler-wechat-plugins
git clone <本仓库的Git地址> butler-wxbot
cd butler-wxbot
.\scripts\setup.ps1
.\.venv\Scripts\python.exe -m butler doctor
```

`setup.ps1` 调用交互向导 `python -m butler setup`，选择接入方式、地址、端口和机器人昵称，
确认后写入本机配置。支持 Codex、Hermes、OpenClaw、Cursor、DeepSeek、已有 Butler、
自定义 Chat Completions／Responses；默认值来自代码，不需要复制配置模板。
完整步骤、升级与回退见 [docs/CODEX_INSTALL.md](docs/CODEX_INSTALL.md)。

## 运行

```powershell
.\.venv\Scripts\python.exe -m butler start
```

`start` 按 `config.wxbot.toml` 的 `[installation].mode` 拉起进程：`local` 启动 Butler、管理台、
wxbot；`external` 和 `direct` 启动管理台与 wxbot。端口被占用时保留已有进程，不自动重启。

也可以分别启动：

```powershell
.\.venv\Scripts\python.exe -m butler.server --config config.butler.toml   # 8770
.\.venv\Scripts\python.exe -m dashboard.server                           # 8788，管理台在 /app/
.\.venv\Scripts\python.exe -m wxbot.main                                 # 8765，微信收发
```

服务由使用者自行管理；改动后按页面提示重启对应进程。

## 目录

```
src/butler/     编排层：agent/ identity/ delivery/ runtime/ channels/telegram/ news/ backends/
src/wxbot/      UI 收发层：主窗口监听、收件箱、队列、发件与后端适配
src/dashboard/  管理台 HTTP 服务；src/common/ 提供 REPO_ROOT 与跨进程配置锁
web/            Vue 3 + Vite 前端源码，构建产物 web/dist 由管理台在 /app/ 提供
tests/  scripts/  plugins/  tools/  docs/  data/   测试域、运维脚本、插件、打包脚本、文档、本机数据
```

包都在 `src/` 下，靠 `pyproject.toml` 的可编辑安装导入：`python -m butler`、
`python -m dashboard.server`、`python -m wxbot.main` 均可在仓库外运行。

## 文档与验证

全部文档从 [docs/INDEX.md](docs/INDEX.md) 进入：架构、安装与升级、消息接口、身份与记忆、
新闻投递、Telegram、管理台与前端、验证记录。

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe tools\release.py
```

微信 UI 自动化需要可访问的主窗口及未锁屏的电脑，不同版本可能需要校准控件。
实际微信收发请由使用者确认后验证。
