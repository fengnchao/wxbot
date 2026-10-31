# tools

开发与发布用的本机工具。运行时（wxbot / Butler / 管理台）不依赖这里的任何文件，
但改微信 UI 适配、联调 Codex、发布前都靠它们。

| 文件 | 用途 | 是否需要网络 |
|---|---|---|
| `probe.py` | 微信控件树探测，用来校准 `config.wxbot.toml` 的 `[wechat.*]` 选择器 | 否 |
| `avatar_calibration.py` | 头像采样校准：对比自动边界检测与旧的固定 36px 裁剪 | 否 |
| `debug_read.py` | 检查窗口／消息列表／输入框，并打印每条消息被判成谁发的 | 否 |
| `probe_codex.py` | Codex 端到端联调：真实模型调用 + MCP 记忆 + 线程续接 | 是（调模型） |
| `release.py` | 按白名单打两个可移植包，并做凭据形状审计 | 否 |

## probe.py

打印微信窗口的 UIA 控件树，确认控件能不能读到、路径是什么。

```powershell
.\.venv\Scripts\python.exe tools\probe.py --list                     # 列出所有顶层窗口
.\.venv\Scripts\python.exe tools\probe.py --window 微信              # 打印控件树
.\.venv\Scripts\python.exe tools\probe.py --window 微信 --depth 12 --raw
```

- 默认**脱敏**：控件文字显示为 `***(长度)`，输出可以直接贴给别人分析；`--raw` 才显示真实文字。
- 只读本机界面，不联网、不发任何数据。
- 窗口必须在屏幕上、不遮挡；微信升级后控件结构变了，先用它重新校准。

## debug_read.py

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

## avatar_calibration.py

把当前群聊窗口里每一行消息的头像截成两版并排放大：左列按像素边界自动定位，
右列是旧的固定 36px 裁剪。左边出现完整头像、右边露出被切掉的右下角，就说明采样正常。

```powershell
.\.venv\Scripts\python.exe tools\avatar_calibration.py
```

- 微信要停在一个群聊窗口，且窗口可见、不遮挡、不最小化——被挡住时会抓到桌面像素。
- 输出 `cache/avatar-calibration.png`，标签里带实测偏移量（正常是 `(+8,+8)`）。
- 只读屏幕，不发消息、不改配置。换了显示器缩放或微信大版本更新后跑一次即可。

## probe_codex.py

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

## release.py

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
