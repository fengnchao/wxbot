# Telegram 联合早报 → 微信新闻分组

本渠道通过安装者自己的 Telegram 账号，接收已加入的 `@zaobaosg` 官方频道的新文字，再经 Butler 和 wxbot 推送给 log → 联系人中为实际收件会话开启“新闻”订阅的用户。

文字正文和媒体附带的文字说明都会转发，附来源、北京时间和原消息链接。无需 OCR，也不下载图片/视频。Telegram 消息不调用模型、不执行消息中的指令。

## 安装和配置

在项目根目录，用现有 Python 3.14 环境安装可选依赖：

```powershell
uv sync --locked --extra dev --extra telegram
```

没有 uv 时，先安装项目基础依赖，再执行：

```powershell
.\.venv\Scripts\python.exe -m pip install "Telethon==1.45.0" "python-socks[asyncio]>=2.7,<3"
```

首次运行 `python -m butler.channels.telegram init`，由代码默认值生成 `config.telegram.toml`；已有本机配置保留，不覆盖。生成配置默认关闭、凭据为空。

在 [Telegram API development tools](https://my.telegram.org/apps) 为自己的账号申请 `api_id`、`api_hash`，在本机配置中填写，并设置 `enabled = true`。不把密钥、验证码、二次验证密码或 `.session` 文件发到聊天中。

默认配置：

- 来源：`sources = ["@zaobaosg"]`。
- Butler 配置：`butler_config = "config.butler.toml"`。
- 授权会话：`data/telegram/account.session`。
- 状态目录：`data/telegram/`。
- 补收扫描间隔：10 秒，新消息事件可提前唤醒扫描。

相对路径均以配置文件所在目录为基准。代理如有需要，在本机配置增加 `[proxy]`，填写 `type`、`host`、`port` 及必要凭据，使用 Telegram 可用代理；本地 Butler 请求绕过代理。

电脑 Telegram 已登录不代表接收程序已授权。接收程序使用独立本地会话，不读取桌面客户端的 `tdata`。账号须已加入来源频道；程序不会自动入群。

## 授权、启动和查看状态

在本机终端执行授权，按提示输入手机号、验证码及必要的两步验证密码。验证码和密码不回显：

```powershell
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m butler.channels.telegram login
```

确认 Butler 和 wxbot 已由安装者启动后，再运行接收程序：

```powershell
.\.venv\Scripts\python.exe -m butler.channels.telegram run
```

按 Ctrl+C 停止新增接收及任务领取；已有 HTTP 请求等待其回执或超时后退出。不自动停止或重启 Butler、wxbot、log。

另一个终端可只读查看保存的状态：

```powershell
.\.venv\Scripts\python.exe -m butler.channels.telegram status
```

`status` 不登录 Telegram、不发送消息、不创建会话或数据库；它显示最近保存的快照，不能单凭 `running`/`connected` 字段判定进程仍活着。请结合扫描时间和终端状态检查。

`message_results` 按最近 100 条消息列出计划接收人数及完成接收人数；仅当某人的全部分段都获得 Butler 成功回执，才计入该条消息的 `completed_recipients`。

上述命令支持 `--config <Telegram配置路径>`；`--butler-config <Butler配置路径>` 可覆盖配置中的 Butler 路径。

## 接收和发送规则

- 首次运行将每个来源的最新消息 ID 记为起点，不发送历史。以后重启会从保存的扫描游标补收离线期间的新消息。
- 每条消息按“来源 ID＋消息 ID”去重；同样文字但不同消息 ID 仍是两条消息。
- 首次展开某条消息时读取最新新闻分组。分组为空记为跳过，之后加人不补发该消息。
- 新增订阅者从后续展开的消息开始接收。发送前已取消订阅的人，其未提交部分取消。
- 长消息按约 500 字分段，完整 URL 不截断，较长 URL 可超过分段目标长度。
- 只有 Butler 确认对应接收人发送成功才记 `sent`。超时、无有效回执或提交中退出记 `uncertain`，不自动重发。
- `uncertain` 或明确被拒绝的 `not_submitted` 会暂停该接收人的后续投递，其他接收人继续。到 log 收发队列核对，再明确安排人工处理；不要删除数据库来强制重发。
- 账号或来源数字 ID 与已绑定身份不符时停止，不自动切换到同名来源。
- 不处理编辑/删除事件，不向 Telegram 发送回复。

Telegram 接收与每日 09:00 RSS 简报独立运行。两者使用同一新闻分组接收人；RSS 页面配置的类别、来源和每日条数不限制 Telegram 的即时消息数量。

## 运行文件与检查

`data/telegram/relay.sqlite3` 保存来源游标、收件、逐人逐段回执及最近状态；`run.lock` 和会话旁的锁防止重复运行。会话和实际配置不能提交或分发。

离线测试使用假的 Telegram 客户端和假的 HTTP 回执，不访问真实账号或剪贴板。真实接入是否成功以本机授权、来源核对和实际 Butler 回执为准。

参考：[联合早报官方入口](https://www.zaobao.com.sg/products)、[Telegram API 参数申请](https://core.telegram.org/api/obtaining_api_id)、[Telethon 登录](https://docs.telethon.dev/en/stable/basic/signing-in.html)。
