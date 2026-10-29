# Telegram 机器人 → Butler 新闻投递

机器人私聊消息先提交 Butler 收件入库，再按“新闻消息”类别投递到微信新闻分组。不调用 Codex、不向 Telegram 回复。可直接私聊机器人，或把允许转发的频道消息手动转发给机器人。[可配置的频道窗口转发与微信图片投递](TELEGRAM_RELAY_SKILL.md) 已提供，默认关闭，需本机校准与自行重载服务。

收件先走 `/v1/telegram/inbox`。确认落盘后，读取 Butler 配置的分组文件 `groups["1"]`，逐人逐段调用 `/v1/push`，请求为 `{type:1,messageType:1,contact:"订阅者",text:"新闻正文"}`。与新闻分组群发的目标一致，逐人提交便于记录独立回执。

## 本机配置

```powershell
.\.venv\Scripts\python.exe -m butler.telegram_bot init
```

`init` 从代码默认值生成配置，保留已有文件，不复制模板。编辑 `config.telegram-bot.toml`：

```toml
[telegram_bot]
token = "本机填写新的 BotFather Token"
allowed_user_ids = [123456789] # 换成你自己的 Telegram 用户数字 ID
butler_config = "config.butler.toml"
state_dir = "data/telegram-bot"
proxy_url = "" # 如需要，可填 http://127.0.0.1:本机HTTP代理端口
```

不要填 api_id/api_hash，不要使用聊天里已公开的 Token。真实配置已加入 Git 忽略。

不知道自己的数字 ID：先只填 Token，保持 `allowed_user_ids = []`，启动接收器并给机器人发 `/start`。终端会输出 `sender_id=... 不在 allowed_user_ids`，不会保存正文或提交 Butler。将**自己的账号**对应 ID 填入白名单，自行重启接收器，再发送一条新消息。之前被拒绝的消息不会补发。

## IDE 启动

1. 自行重启 Butler，加载新的 `/v1/telegram/inbox` 接口。wxbot/log 无需重启。
2. 新建 Python 运行配置，选择 **模块名** `butler.telegram_bot`；参数 `run`；工作目录为项目根目录；解释器使用项目 `.venv`。
3. 环境变量可设置 `PYTHONIOENCODING=utf-8`。

仅更新基础文字收件时，自行重载 Telegram 接收器。首次使用可选图文路径需自行重载 Butler、wxbot、接收器和 log；配置和校准见上述图文文档。启动后会为已有 `received` 且尚未生成新闻任务的记录补建投递任务。机器人命令（如 `/start`）跳过；图片功能关闭时纯媒体记录标注不支持，不发送空消息。不要手动重置数据库以补发。

等价终端命令：

```powershell
.\.venv\Scripts\python.exe -m butler.telegram_bot run
```

有需要时在参数末尾添加 `--config 配置文件路径`。启动接收器不会启动 Butler 或 wxbot。Telegram 使用显式 HTTP 代理配置；不会自动读取系统代理环境变量。本机 Butler 请求不走代理。

启动会显示 `getMe` 连接阶段、直连/显式代理模式，再检查 Webhook。`连接 Telegram 超时` 表示尚未完成联网，不能据此判断 Token 无效；401 表示认证未通过；代理连接失败、TLS 失败和 409 轮询冲突会分别提示。即使桌面客户端可用，Python 接收器也可能仍需手动填写 `proxy_url`。日志不会输出包含 Token 的请求 URL。

## 确认收到

向机器人发送或转发一条消息，预期日志：

- 接收器：`已收件 update=... sender=...；等待 Butler 确认`
- Butler：`[Telegram] 收件已持久化 bot=... update=... receipt=... status=received`
- 接收器：`Butler 已确认入库 receipt=...`
- 接收器：`新闻 update=...：已生成 ... 人 × ... 段任务；messageType=1`
- 接收器：`新闻 update=... → 用户：sent；Butler 确认微信发送成功`，或明确失败/未确认原因。

只读查看最近 20 条收件和提交状态：

```powershell
.\.venv\Scripts\python.exe -m butler.telegram_bot status
```

`status` 会在本机显示收到的正文/图片说明；不要公开分享包含私人内容的输出。`relay` 是收件提交队列，`butler_received` 是 Butler 真正落盘的消息，`news_plan` 显示新闻展开或跳过原因，`news_delivery` 显示逐人逐段的发送状态（最近 50 条）。收件的 received 不代表微信已发送，新闻任务的 sent 才表示 Butler 确认微信发送成功。

在 log 的「实时工作流」查看 Telegram → Butler 新闻提交与投递回执；Codex 仍位于顶部，新闻不经过模型。在「收发队列」的 Telegram 区查看机器人收件、跳过原因、逐人分段及阻塞任务；默认“全部消息”，支持独立分页和异常筛选。微信侧实际任务同时显示在发件队列，已提交外发仍可在「消息流转」查看。尚无共同任务 ID 的两端记录独立展示，不把同文消息猜测合并。

新增页面功能需自行重启 log 并强制刷新浏览器。页面只读查询 Telegram 数据库，不迁移、不恢复、不清理任何队列。

## 数据与失败行为

- 接收器 `state_dir/relay.sqlite3`：待提交消息、状态、轮询游标；一次事务保存消息和游标。未授权账号只推进游标，不存正文。
- Butler `data_dir/telegram-bot/inbox.sqlite3`：收到的文字、实体链接、图片文件标识、图集标识及转发来源。启用可选图片路径后，图片本体校验存入 `data_dir/media`；视频和普通文件仅保留元数据。
- 私聊原始发送者必须属于白名单。白名单检查使用 `from.id`，不使用转发来源身份。
- 按 `bot_id + update_id` 幂等入库；收件回执丢失可安全重试，新闻任务只展开一次。
- Butler 不在线/HTTP 404/认证失败：保留队列，每 10 秒尝试提交；检查 Butler 启动版本、配置和端口。HTTP 400 内容拒绝：记录 rejected，不阻塞后续，须人工核对。
- 新闻投递与收件分别运行，等待微信发送期间继续采集。每个新闻任务在请求前持久化 sending；中断后改为 uncertain，不自动重发。明确拒绝记 not_submitted，也不会自动重试；核对 log 后再安排人工处理。同条新闻后续分段等待前段成功，其他消息仍可继续。
- 在展开新闻任务时读取订阅列表，空分组跳过该条；配置修复或后续订阅不自动补发已跳过消息。提交前再次检查订阅，已取消的接收人不发送。
- 正文保留图片说明及显式/隐藏的网页链接；附可获取的频道来源链接。默认文字路径按序发送文字并附媒体提示。启用 `include_images` 后改用整包图片和图集投递，限制与失败行为见图文文档；视频和普通文件不发送到微信。
- Bot Token 无效或轮询冲突会停止接收；同一机器人只运行一个接收器。已有 Webhook 时拒绝启动，不自动删除或替换。
- 网络中断期间 Telegram 服务端仅暂存有限时间的更新，不能保证无限期离线补收。

接口使用现有 Butler Bearer Token 鉴权；请求 `{bot_id, update_id, message}`，message 是私聊消息的受支持字段。回执 `{ok, status, receipt_id, bot_id, update_id}`，status 为 received 或 duplicate。这个接口只信任持有本机 Butler 凭据的桥接程序，不向公网开放。

参考：[Telegram Bot API getUpdates / Message](https://core.telegram.org/bots/api#getupdates)。
