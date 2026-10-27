# Telegram 频道窗口转发与图文投递

路径为：已登录的 Telegram Desktop 频道 → 客户端原生转发给现有机器人 → Bot 接收器 → Butler 新闻分组 → wxbot 微信图文队列。持续监听由确定性服务执行，不逐条调用模型。

本功能默认关闭；本次实现使用假 UI、假网络和临时数据库进行离线验证，未据此启用真实路由，也未完成真实 Telegram 转发和微信图片发送的端到端验证。不同客户端版本仍需本机校准；真实发送须由使用者明确授权。

## 配置入口

先确认现有 [Telegram Bot 接收器](TELEGRAM_BOT.md) 已按本机账号配置，使用同一个机器人和现有新闻消息分组。无需新增个人 Telegram API 凭据，也不启动第二个轮询接收器。

在 Butler 配置所在目录，将 [config.telegram-relay.example.toml](../config.telegram-relay.example.toml) 复制为 `config.telegram-relay.toml`，或在 log 的「Telegram 转发」页面保存配置。示例的 `enabled=false`、`include_images=false`、空管理员和空频道不会开启监听或图片投递。配置文件缺失同样保持关闭。

| 设置 | 用途 |
|---|---|
| `enabled` | 频道窗口监听总开关；不会启动或重启进程 |
| `window_title`、`desktop` | Telegram 窗口及消息列表、搜索、复制链接、转发弹层等控件名称 |
| `bot_username`、`bot_id` | 现有接收机器人的用户名和数字 ID；转发前与接收器 `getMe` 身份快照核对 |
| `poll_interval` | 频道扫描间隔，单位秒 |
| `include_text`、`include_source`、`include_time` | 图文路径中保留正文、来源和原发布时间 |
| `include_images` | 开启图片下载与微信图文投递；独立于桌面监听开关，关闭监听后手动转发到机器人的图片仍可进入此路径 |
| `album_quiet_seconds`、`max_album_wait` | 图集静默等待和最长聚合时间；超时或迟到成员会留下待核对记录 |
| `admin_contacts` | 允许通过管理 Skill 查看、暂停、恢复全局监听的微信会话名称 |
| `channels` | 每个频道的稳定 `key`、显示 `name`、`username`／数字 `chat_id` 和独立 `enabled` |

启用监听需要窗口标题、完整机器人身份和至少一个启用且有用户名或数字 ID 的频道。频道名称不能单独充当唯一身份；遇到同名、来源无法验证或机器人身份不符时停止相关操作。频道显示名可修改，稳定 `key` 用于保存游标，应保持不变。

Telegram 转发选择器还必须暴露可读取的真实用户名字段和收件人选中状态。`desktop.recipient_username_field` 默认定位名为「用户名」的元数据控件，并读取其 Value；行显示名即使写成 `@机器人` 也不能作为身份证据。控件缺失或无法证明唯一选中目标时保留待校准状态，不猜选第一个结果。

Bot Token 继续保存在现有 `config.telegram-bot.toml` 中，不填写到 relay 配置、Skill 或浏览器。接收器仍检查原始发送者 `from.id` 的 `allowed_user_ids`，转发频道身份不能替代发送者授权。微信接收人沿用新闻消息分组；展开时去重，发送前重新检查订阅。

默认各配置位于同一项目目录，Bot 数据为 `data/telegram-bot`，Desktop 数据为 `data/telegram-relay`。使用自定义目录时，应让 wxbot 的 `[telegram_relay].config`、Bot 的 `relay_config` 与 Butler 指向同一份设置，并让 Desktop 状态目录与 Butler 的 `data_dir/telegram-relay` 一致；当前 Desktop 身份核对从其状态目录同级的 `telegram-bot/bot-identity.json` 读取接收器身份。

## 管理 Skill

在 log「角色与心跳」为管理员会话允许 `telegram-relay`，并在「Telegram 转发」的管理员名单中填写同一会话名称。两项都满足后才开放工具；只允许 Skill 不会获得全局管理权。

- `telegram_relay_status`：读取配置和运行快照。
- `telegram_relay_pause`：关闭监听开关，保留游标和任务。
- `telegram_relay_resume`：恢复已配置的监听开关，不补发历史。

工具身份由 Butler 签发，不接受模型提供的联系人、频道或文件路径。心跳只能查看状态。频道正文和图片说明属于转发数据，不能提供权限或修改设置。

log 保存使用文件版本检查，冲突时保留浏览器草稿，需放弃旧草稿、刷新后重新编辑。保存、暂停和恢复均不会启动或重启服务；新增代码或微信图片控件配置需要由使用者自行重载相应服务。程序不会自动停止已有进程。

## 首次扫描、积压与桌面协调

首次启用每个频道时只建立当前已加载消息的基线，仅处理后续新增内容。不会自动向上补读历史；加载区缺少历史锚点时记录 `snapshot_gap` 待核对。修改配置不会重置游标或重新投递历史，勿通过删除数据库来补发。

同文、同分钟的消息若原生行身份已经改变，会记录 `snapshot_ambiguous`，避免静默当作旧消息；客户端重建消息控件也可能触发这一暂停，需要核对实际来源。同一 `key` 被改成另一个频道身份时重新建立基线，并取消旧的待提交任务；已经阻断或结果未知的记录仍需人工核对。

各频道保存独立基线、来源消息标识和转发任务，多频道轮转处理。新任务先持久化，再进行原生转发；可靠来源通过消息链接等核对，不能凭相同正文认定相同消息。受保护且禁止转发的内容不会通过截图等方式绕过。

本功能集成在 wxbot 的主窗口模式（`wechat.mode="main"`）。Telegram 与微信共用一个 UI 调度线程，在完整事务边界轮转；微信正在输入文字、选择 @、粘贴图片、预览或确认气泡时不会切换到 Telegram。Bot 网络轮询、图片下载和 Butler 请求不占用 UI 所有权。用户手工切换到其他应用、输入草稿或界面身份变化时暂停相应操作，不与用户争抢。

## 图片限制与微信控件校准

启用 `include_images` 后下载真实图片并交给微信图片发送流程，包含纯图片和图集；不以图片链接代替图片本体。当前支持单帧 JPEG、PNG、WebP，单图不超过 **20 MiB**，解码尺寸不超过 4000 万像素；图文包最多 50 个文字／图片项目。视频、音频、动画和普通文件不会伪装成图片发送。损坏、超限、下载失败或图集缺员保留失败记录，固定采用 `image_failure_policy="hold"`，不把缺图消息标记为完整成功。

微信图片发送要求在本机 `config.wxbot.toml` 校准以下三个选择器；它们不是通用有效值，不能直接复制占位名称后启用：

```toml
[wechat.image.preview]
name = "本机图片预览容器的准确名称"

[wechat.image.send]
name = "预览容器内发送按钮的准确名称"

[wechat.image.item]
class_name = "消息列表内图片条目的准确类名"
```

`preview` 定位当前聊天内的图片预览，`send` 在该预览内定位发送按钮，`item` 匹配消息列表中的图片行。用本机控件探针读取实际名称、类名等特征，并在授权的验证流程中确认目标、草稿、预览和新图片气泡。缺少任一选择器时不开始图片粘贴；出现预览不符、焦点变化或无法确认自己的新图片气泡时保留阻断／不确定状态。只看到微信发送气泡也不代表对方已读。

Butler 和 wxbot 之间只传服务端签发的 `media_id`，不接受模型指定的任意磁盘路径或 URL。图文包以稳定请求 ID 去重，文字与图片按包内顺序进入持久队列，同一接收人的一个包不会被其他包插入打断；整包确认后才记录成功。

## 状态与人工核对

log「Telegram 转发」展示开关、各频道最近扫描、队列数量和最近任务；「实时工作流」「收发队列」继续展示 Bot 收件、图片准备及微信实际投递。来源缺少可靠关联时各阶段独立展示，不按正文强行合并。

| 状态／阶段 | 含义与处理 |
|---|---|
| Desktop `awaiting_bot` | 原生提交窗口已关闭，释放桌面操作权，等待机器人实际收件回执 |
| Desktop `forwarded` | 已匹配来源消息的 Bot 收件回执，或经管理员人工确认；尚不代表微信发送成功 |
| `received` | Butler 收件已落盘，尚无整包发送确认 |
| `preparing` | 图片下载、校验或图集准备中 |
| `media_failed` | 图片准备失败，查看具体原因，其他频道可继续 |
| `blocked` | 当前任务被阻断，先核对原因和残留界面 |
| `uncertain` | 可能已提交但结果未知，不自动重发 |
| 图文投递 `sent` | Butler 收到整个图文包的微信发送确认 |

桌面转发结果不确定或遗留搜索、菜单、弹层时会持久化 UI 核对暂停。重启、Skill 暂停或恢复不能清除它。先核实**频道键、来源消息 ID、任务 ID**及机器人实际收件，再手动清理 Telegram 残留界面，在对应任务勾选确认后选择：

- **确认已转发**：仅确认 Telegram 阶段，不再次转发。
- **确认未发，重试**：只有确认尚未发送后才重新排队。
- **放弃**：结束该转发任务。

没有消息任务的全局桌面核对只提供「界面已清理，继续／放弃本次操作」，不能标记消息已转发。正在转发的任务不能被人工处置。操作由本机 log 通过服务端认证提交 Butler；Token 不进入浏览器，普通 Skill 无权清除核对暂停。

Desktop 默认持久库为 `data/telegram-relay/desktop.sqlite3`，运行快照为同目录 `desktop-status.json`；Bot 聚合与逐接收人图文状态保存在现有 `data/telegram-bot/relay.sqlite3`，实际微信任务进入既有 wxbot 队列。网络超时或进程中断不会被当作可以安全重放的证据。Telegram 转发核对操作不会清除微信侧未知结果；微信异常任务应在「收发队列」核对后单独处理。

### 仅重试尚未投递的图片准备

临时下载或图片注册失败会保留 `media_failed`，不会自动重复准备。修复网络等原因后，先从 `python -m butler.telegram_bot status --config config.telegram-bot.toml` 的 `news_package` 读取准确 `bot` 和 `package_key`，再显式执行：

```powershell
python -m butler.telegram_bot retry-media --bot-id 123456 --package-key "source:album:从状态页复制的完整键" --config config.telegram-bot.toml
```

命令只重置指定包的失败准备记录、相关原始消息计划和归属该包的来源别名，保留原始入站消息。它在同一事务中两次检查包仍为 `media_failed` 且**没有任何图文投递记录**；已有 pending、sending、sent、uncertain、blocked、取消等投递记录都拒绝重置，关联文字投递存在时也拒绝。未知包、非失败状态或缺少的数据库不会被创建或改写。

CLI 不执行下载、Bot 转发或微信发送。返回 `retry_ready` 后，正在运行的接收服务按现有图片开关、权限、订阅及图集规则重新准备；图片准备成功后才会进入正常投递。结构性问题、受保护／不支持的附件或部分图集来源重叠仍可能再次保留失败，须先处理原因。此命令不能解除已提交或结果不确定的微信投递，勿用删除数据库替代核对。
