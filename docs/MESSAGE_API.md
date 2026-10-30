# wxbot / Butler 消息收发接口文档

核对日期：2026-10-28。依据 `D:\work\code\wxbot` 当前工作区源码整理，包含尚未提交的现有实现。文档中的回包为格式示例，动态 ID、正文和状态以实际响应为准。

## 1. 接口地址与接入方式

| 服务 | 基础地址 | 地址配置 | 用途 |
|---|---|---|---|
| Butler | `http://127.0.0.1:8770` | `config.butler.toml` 的 `[server].host / port` | 接收消息并调用模型、归档、主动推送 |
| wxbot 外发服务 | `http://127.0.0.1:8765` | `config.wxbot.toml` 的 `[outbound].host / port` | 将文字、图片实际投递到微信 |
| log 管理台 | `http://127.0.0.1:8788` | `config.log.toml` 的 `[server]`；启动参数可覆盖 | 查询收件、发件和消息流转 |

本次仅提取了本机配置中的非敏感连接信息：Butler 配置为 `127.0.0.1:8770`、Codex 后端；wxbot 外发配置为 `127.0.0.1:8765`、`enabled=true`，微信模式为 `main`。管理台表中地址为项目默认值。以上为配置地址，不代表已验证服务正在监听或已加载最新源码。

这些是本机 HTTP 接口。`127.0.0.1` 指调用程序所在的电脑，其他电脑不能直接使用这里的地址连接机器人；Codex Butler 启动时要求绑定回环地址。

安装向导 `python -m butler setup` 生成本机配置，不依赖模板。`local` 运行本机 Butler；
`external` 调用已有 Butler；`direct` 直接使用 `[model]` 指定的模型协议，不运行本机 Butler，
因此下文 Butler 记忆、提醒和业务工具接口不会由直接接入模式自动提供。
外部 Butler 模式仅通过配置的消息接口调用远端，本机管理台关闭远端账户、记忆和心跳管理；使用远端自己的管理台维护。
共享联系人、监听设置和按群昵称存放在 `data/business.sqlite3`，通过管理台维护；稳定身份授权仍由服务端校验。
相对运行路径以相应配置所在目录为基准。已有安装用 `python -m butler migrate` 显式升级。

### 1.1 鉴权与请求格式

| 接口所在服务 | 请求头 | Token 来源 |
|---|---|---|
| Butler 消息、推送及媒体接口 | `Authorization: Bearer <BUTLER_TOKEN>` | `config.butler.toml` 的 `[server].token` |
| wxbot `/send`、`/send-bundle` | `X-Wxbot-Token: <WXBOT_TOKEN>` | `config.wxbot.toml` 的 `[outbound].token` |
| wxbot `GET /health` | 无需 Token | 无 |
| log 下文所列只读 GET 接口 | 当前实现无 Token 鉴权 | 供本机管理台使用 |

两套 Token 分别配置，不能混用。Butler 调用 wxbot 时使用自己的 `[wxbot].token`，该值需要与 wxbot 的 `[outbound].token` 一致。wxbot 调用 Butler 时使用 `[butler].token`，该值需要与 Butler 的 `[server].token` 一致。

除图片上传外，POST 请求均使用 UTF-8 JSON 对象：

```http
Content-Type: application/json; charset=utf-8
```

JSON 中布尔值写作 `true / false`，空值写作 `null`，数字不要加引号。普通 JSON 请求体上限为 **1 MiB（1,048,576 字节）**，特定接口另有更小限制。请求应发送准确的 `Content-Length`，不依赖分块传输。响应通常为 `application/json; charset=utf-8`，图片下载返回图片二进制。

Butler Token 为空时拒绝请求并返回 500；wxbot `/send` 在服务端 Token 为空时会跳过校验，而 `/send-bundle` 必须配置非空 Token。接入时应配置非空 Token，示例均使用占位符。

### 1.2 收件与发件的关系

```text
微信界面 → wxbot 采集和收件队列 → Butler /v1/handle
                                       ↓ 返回 reply / reply_parts
微信界面 ← wxbot 发件队列和 UI 发送 ← wxbot 调用方保存回复

外部程序 → Butler /v1/push → wxbot /send → 微信界面
外部程序 ─────────────────→ wxbot /send → 微信界面
```

`/v1/handle` 会处理输入消息并返回回复，调用方负责后续投递；它不自动把返回的 `reply` 发送到微信。模型获准执行的业务工具可能有各自的副作用，仍受服务端权限约束。

微信原始收件依靠 Windows UI 采集。当前没有供第三方订阅微信实时消息的 Webhook、WebSocket、SSE 或“注册回调 URL”接口；第三方可以调用处理接口，或通过管理台只读接口查询已采集记录。

### 1.3 指定联系人只转发到其他接口

在 `config.butler.toml` 添加规则，也可以在管理台「配置管理」搜索「指定联系人消息转发」，
编辑对应 JSON 数组。`contact` 是微信私聊会话的精确名称（通常是备注名），
`code` 是目标接口要求的用户代码，两者可以不同：

```toml
[[message_routes]]
contact = "微信联系人备注名"
url = "http://127.0.0.1:8790/v1/message"
code = "101"
enabled = true
timeout = 10
```

该联系人发来「你好」时，Butler 发送：

```http
POST http://127.0.0.1:8790/v1/message
Content-Type: application/json

{"code":"101","text":"你好"}
```

规则在模型调用、个人记忆读取、补发认领及 Butler 自身命令前判断；
收到任意 2xx 响应即记为转发成功，响应正文不解析、不回微信。
失败、超时或重定向只记录错误，不改走 Codex，也不自动重放请求。
对端应在接收成功后返回 2xx；超时可能发生于对端已接收之后，需要人工核对。

没有规则、`enabled = false` 的联系人以及群聊继续原有处理流程；一个联系人最多一条规则。
`enabled` 缺省为 true，`timeout` 缺省为 10 秒。删除或禁用规则后恢复模型处理。
配置更改需由使用者自行重载 Butler，程序不自动重启。

转发正文沿用 wxbot 已送到 Butler 的文本批次；短时间内多条消息仍按原队列规则合并。
wxbot 本地 `/ping`、`/help`、`/reset` 等斜杠命令仍在 wxbot 处理，不进入此转发接口。
此功能不转发记忆、角色、服务凭证、其他用户上下文或图片原文件。

## 2. 接口速查

以下路径分别拼接对应服务的基础地址。

| 分类 | 方法与路径 | 服务 | 作用 |
|---|---|---|---|
| 接收处理 | `POST /v1/handle` | Butler | 接收一条私聊或群聊消息，返回模型处理结果 |
| 接收归档 | `POST /v1/group/archive` | Butler | 批量保存群公开上下文，不调用模型、不直接发消息 |
| 身份观测 | `POST /v1/users/observe` | Butler | 登记收件中的用户身份观测，不调用模型 |
| Telegram 收件 | `POST /v1/telegram/inbox` | Butler | 将 Telegram 私聊消息持久化入库 |
| 文字发送 | `POST /v1/push` | Butler | 发送给指定联系人，或按订阅分组逐人群发 |
| 文字发送 | `POST /send` | wxbot | 直接提交指定微信会话的文字发送 |
| 图文发送 | `POST /v1/push/bundle` | Butler | 向新闻订阅联系人发送有序图文包 |
| 图文发送 | `POST /send-bundle` | wxbot | 直接提交指定微信会话的有序图文包 |
| 媒体 | `POST /v1/media` | Butler | 上传图片，获得 `media_id` |
| 媒体 | `GET /v1/media/{media_id}` | Butler | 下载已上传图片 |
| 订阅检查 | `GET /v1/telegram-relay/authorize?contact=...` | Butler | 查询联系人是否在新闻订阅分组 |
| 会话 | `POST /v1/reset` | Butler | 重置指定会话 |
| 主动问候 | `POST /v1/heartbeat/trigger` | Butler | 异步触发一次模型心跳问候 |
| 主动问候 | `POST /api/heartbeat-trigger` | log | 管理台对 Butler 心跳接口的转发入口 |
| 探活 | `GET /health` | Butler / wxbot | 分别检查两个 HTTP 服务 |
| 查询 | `GET /api/queue` | log | 查询收件、批次、发件及 Telegram 队列 |
| 查询 | `GET /api/flow` | log | 查询消息流转与发送状态 |
| 查询 | `GET /api/workflow` | log | 查询工作流汇总和消息列表 |
| 查询 | `GET /api/workflow-content?id=...` | log | 查询一条记录的完整正文和回复 |
| 查询 | `GET /api/wxbot` | log | 查询历史收发流水、统计和内嵌流转信息 |

## 3. 接收消息接口

### 3.1 接收并处理消息：POST /v1/handle

完整地址：`http://127.0.0.1:8770/v1/handle`。使用 Butler Bearer Token。

| 参数 | JSON 类型 | 必填 / 默认 | 说明 |
|---|---|---|---|
| `contact` | string | 必填 | 微信联系人备注名或群名，即机器人识别的会话标题；去掉首尾空白后不能为空，不是微信号、手机号或业务 `user_id` |
| `text` | string | 建议必填；默认 `""` | 收到的消息正文；路由层未强制非空，正常接入应传实际正文 |
| `msg_id` | string | 可选 | 调用方请求关联 ID；若提供，回包 `meta.msg_id` 原样回传。建议使用稳定的唯一字符串 |
| `channel_type` | string | 可选；`"dm"` | `dm` 为私聊，`group` 为群聊 |
| `member_key` | string | 可选；`""` | 群成员观测标识，用于区分同群成员；群聊接入应提供稳定值，不等同于固定用户 ID |
| `member_name` | string | 可选；`""` | 群成员显示名，辅助身份观测 |
| `avatar` | string | 可选；`""` | 头像图片的 Base64，或 PNG/JPEG/WebP Base64 Data URL；具体约束见下文 |
| `group_context_seq` | integer | 可选；`0` | 非负群上下文序号，通常传先前群归档回包的 `seq`，用于确定上下文边界 |

私聊请求：

```json
{
  "contact": "张三",
  "text": "你好，帮我整理一下今天的安排",
  "msg_id": "external-20261028-001",
  "channel_type": "dm"
}
```

群聊请求：

```json
{
  "contact": "项目讨论群",
  "text": "请总结刚才的讨论",
  "msg_id": "external-group-20261028-001",
  "channel_type": "group",
  "member_key": "member-a001",
  "member_name": "张三",
  "group_context_seq": 123
}
```

成功回包的典型结构：

```json
{
  "reply": "你好，我可以帮你整理。",
  "actions": [],
  "reply_parts": ["你好，我可以帮你整理。"],
  "meta": {
    "reply_complete": true,
    "msg_id": "external-20261028-001",
    "identity_status": "confirmed"
  }
}
```

| 回包字段 | 类型 | 含义 |
|---|---|---|
| `reply` | string 或 null | 完整回复；`null` 可表示静默或未产生可投递回复 |
| `reply_parts` | string[] | 按项目规则切好的完整回复分块；默认分块阈值 500 字符，可配置，受保护内容可能超过阈值 |
| `actions` | object[] | 动作结果；旧后端可能包含 `skill / ok / detail / text`，没有动作时为空数组 |
| `meta.reply_complete` | boolean | 是否已提供完整处理结果；为 `false` 时不可把结果当成完整回复发送 |
| `meta.msg_id` | string | 请求提供 `msg_id` 时回传 |
| `meta.error / status / retry_safe` | 可选字段 | 模型异常信息、状态及是否明确允许安全重试 |
| `meta.user_id / binding_id / identity_status` | 可选 string | Codex 后端解析出的身份结果 |
| `meta.mention_name` | 可选 string | 已确认的群提及目标，供现有 wxbot 回复链路使用 |

注意：`meta.sent` 是历史字段，在 `/v1/handle` 中表示产生了可返回回复，不能用作“已发到微信”的凭据。`msg_id` 也不构成跨所有后端的通用幂等保证。

头像补充约束：HTTP 路由限制 `avatar` 长度不超过 750,000 字符；Codex 身份解析还会检查 Base64 和真实图片内容，原图最多 512 KiB、最多 400 万像素，宽高至少 16 像素。没有有效头像时可省略该字段。

### 3.2 群消息归档：POST /v1/group/archive

完整地址：`http://127.0.0.1:8770/v1/group/archive`。使用 Butler Bearer Token。

| 参数 | 类型 | 必填 / 默认 | 说明 |
|---|---|---|---|
| `contact` | string | 必填 | 群会话标题。归档层上限 300 字符；Codex 后续身份观测上限 200，接入统一控制在 200 内 |
| `source_id` | string | 必填 | 本批次稳定来源 ID；非空，最多 300 字符 |
| `messages` | object[] | 必填 | 1～200 条消息 |
| `messages[].text` | string | 必填 | 单条最多 10,000 字符，允许空串；整批正文总长度最多 100,000 字符 |
| `messages[].member_key` | string | 可选；`""` | 成员观测 ID；归档层最多 300 字符，需身份观测时建议控制在 128 内 |
| `messages[].member_name` | string | 可选；`""` | 成员名，归档层最多 300 字符 |
| `messages[].sender` | string | 可选；`"other"` | `other` 为他人，`self` 为自己 |
| `messages[].avatar` | string | 可选 | 用于随后身份观测，格式同 3.1；不属于公开上下文正文 |

顶层仅允许 `contact / source_id / messages`。

```json
{
  "contact": "项目讨论群",
  "source_id": "wx-batch-20261028-001",
  "messages": [
    {"text": "下午三点开会", "member_key": "member-a001", "member_name": "张三", "sender": "other"},
    {"text": "好的", "member_key": "member-b002", "member_name": "李四", "sender": "other"}
  ]
}
```

```json
{"seq": 123, "inserted": 2}
```

`seq` 是本次归档最后一条的序号，可用于 `/v1/handle.group_context_seq`。相同 `contact + source_id`、相同规范化内容重复提交，返回原 `seq`、`inserted: 0`；相同来源 ID 更改公开消息内容返回 400。该接口只归档及观测身份，不调用模型、不直接投递微信。

### 3.3 收件身份观测：POST /v1/users/observe

完整地址：`http://127.0.0.1:8770/v1/users/observe`。使用 Butler Bearer Token。

| 参数 | 类型 | 必填 / 默认 | 说明 |
|---|---|---|---|
| `contact` | string | 必填 | 非空会话标题，最多 200 字符 |
| `channel_type` | string | 必填 | `dm / group` |
| `messages` | object[] | 必填 | 1～200 条身份观测 |
| `messages[].member_key` | string | 可选；`""` | 群成员观测标识，建议最多 128 字符 |
| `messages[].member_name` | string | 可选；`""` | 显示名 |
| `messages[].avatar` | string | 可选；`""` | 同 3.1 的头像编码 |
| `messages[].sender` | string | 可选；`"other"` | 只有值为 `other` 的项目参与登记；其他值跳过 |

顶层仅允许 `contact / channel_type / messages`。消息正文不是该接口的必需字段。

```json
{
  "contact": "项目讨论群",
  "channel_type": "group",
  "messages": [{"member_key": "member-a001", "member_name": "张三", "sender": "other"}]
}
```

```json
{"users": [{"user_id": "u_example", "binding_id": "b_example", "status": "observed"}]}
```

`status` 由实际解析结果决定，可能为 `confirmed / observed / unknown / ambiguous / disabled` 等；不要把观测标识直接视为权限凭据。没有 Codex 身份注册组件时，格式校验通过后返回 `{"users": []}`。

### 3.4 Telegram 收件：POST /v1/telegram/inbox

完整地址：`http://127.0.0.1:8770/v1/telegram/inbox`。使用 Butler Bearer Token。这是本机桥接程序的收件接口，当前 Telegram 接收器通过轮询获取更新后调用它。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `bot_id` | integer | 是 | 正整数，Telegram 机器人 ID |
| `update_id` | integer | 是 | 大于等于 0 的更新 ID |
| `message` | object | 是 | Telegram 消息对象 |
| `message.message_id` | integer | 是 | 正整数 |
| `message.from` | object | 是 | 发送者对象 |
| `message.from.id` | integer | 是 | 正整数，真人发送者 ID |
| `message.from.is_bot` | boolean | 建议提供 false | 不能为真 |
| `message.chat` | object | 是 | 私聊对象 |
| `message.chat.id` | integer | 是 | 必须等于 `message.from.id` |
| `message.chat.type` | string | 是 | 只能是 `private` |
| `message.text` | string | 否 | 文字正文 |
| `message.date` | integer | 否 | Unix 秒级时间戳 |

桥接程序还会保留 `entities / caption / caption_entities / photo / document / video / animation / audio / voice / sticker / media_group_id / forward_origin / has_protected_content / link_preview_options` 等原始消息字段。此接口只做基础包络校验和持久化，不逐项校验上述扩展对象；保留媒体元数据不等于提供该媒体的微信发送能力。规范化存储后的完整 JSON 最多 **500,000 字节**。

```json
{
  "bot_id": 123456789,
  "update_id": 10001,
  "message": {
    "message_id": 501,
    "date": 1793145600,
    "from": {"id": 987654321, "is_bot": false, "first_name": "示例用户"},
    "chat": {"id": 987654321, "type": "private"},
    "text": "待接收的消息"
  }
}
```

```json
{"ok": true, "status": "received", "receipt_id": 1, "bot_id": 123456789, "update_id": 10001}
```

回包代表已提交数据库。同一 `bot_id + update_id`、相同完整 JSON 内容再次提交，`status` 为 `duplicate`；同一键内容冲突返回 400。这个回包不代表新闻已转发到微信。独立 Telegram 接收器还会按 `allowed_user_ids` 筛选来源；直接持有 Butler Token 的调用方由该 Token 授权，收件路由本身不重复检查这份名单。

## 4. 发送文字接口

### 4.1 通过 Butler 发送：POST /v1/push

完整地址：`http://127.0.0.1:8770/v1/push`。使用 Butler Bearer Token。该接口不调用模型，记录外发流水后转发给 wxbot。

| 参数 | 类型 | 必填 / 默认 | 说明 |
|---|---|---|---|
| `text` | string | 必填 | 正文，不能全为空白 |
| `type` | integer | 可选；`1` | `1`：指定会话；`2`：按订阅分组逐人群发 |
| `contact` | string | `type=1` 必填 | 联系人或微信群的准确会话标题；`type=2` 按分组取目标，不使用该字段指定目标 |
| `messageType` | integer | `type=2` 必填 | 标准分组：`1` 新闻、`2` 问候、`3` 其他；`type=1` 可省略 |

`messageType` 大小写必须保持一致。当前解析器兼容整数形式字符串和整数值浮点数，接入统一使用 JSON integer。`type` 只支持 1、2；`messageType` 实现没有硬性限制为 1、2、3，其他整数会作为自定义分组键查询，前提是确实配置了相应分组。

指定会话：

```json
{"contact": "张三", "text": "提醒：下午三点开会。", "type": 1, "messageType": 2}
```

按新闻订阅组群发：

```json
{"text": "今天的新闻摘要……", "type": 2, "messageType": 1}
```

**`type=2` 的“群发”指向订阅分组中的多个会话逐个发送。向一个微信群发消息，应使用 `type=1`，将 `contact` 设为群名。** 分组来自 Butler 的 `[groups].file` 所指 JSON 文件。

单发成功回包示例：

```json
{
  "reply": null,
  "actions": [],
  "reply_parts": [],
  "meta": {"reply_complete": true, "ok": true, "detail": "sent", "contact": "张三", "type": 1, "messageType": 2}
}
```

群发回包的 `meta` 还包含 `targets` 数组和 `results` 数组，每项结果含 `contact / ok / detail`。全部目标成功且目标非空时 `meta.ok=true`；部分失败或分组为空时为 `false`。

该接口的发送超时由 Butler 的 `[wxbot].timeout` 配置控制，默认 120 秒；请求体没有 `wait / timeout` 参数。群发顺序等待每个目标，客户端超时需考虑目标数量。HTTP 200 下也必须检查 **`meta.ok`**。

### 4.2 直接调用 wxbot：POST /send

完整地址：`http://127.0.0.1:8765/send`。使用 `X-Wxbot-Token`。

| 参数 | 类型 | 必填 / 默认 | 说明 |
|---|---|---|---|
| `contact` | string | 必填 | 准确的联系人或群会话标题，去首尾空白后非空 |
| `text` | string | 必填 | 要发送的原始正文，不传或空串返回 400 |
| `wait` | boolean | 可选；`true` | `true` 等待执行结果，`false` 立即返回已进入 HTTP 内存队列 |
| `timeout` | number | 可选；`60` | `wait=true` 时最多等待的秒数；建议传正数 |

```json
{"contact": "项目讨论群", "text": "会议将在十分钟后开始。", "wait": true, "timeout": 120}
```

典型回包：

```json
{"ok": true, "detail": "sent"}
```

```json
{"ok": true, "detail": "queued"}
```

```json
{"ok": false, "detail": "timeout：主循环未在时限内发出"}
```

三种情况都可能返回 HTTP 200。`queued` 仅表示放入 HTTP 服务的内存队列，此刻尚不保证已经持久化到 SQLite，更不代表已发出。超时也不会自动取消已提交任务，随后仍可能发出，不要据此直接重试。`/send` 没有通用幂等键或回传的消息 ID，也没有请求参数可指定真正的微信 @ 对象。

主窗口模式由发件队列和 UI 确认流程完成投递；独立窗口模式走原主循环发送。`ok=true, detail=sent` 表示本地发送流程确认成功，不是微信服务器或收件人提供的已读回执。

## 5. 图片与图文发送

### 5.1 上传图片：POST /v1/media

完整地址：`http://127.0.0.1:8770/v1/media`。使用 Butler Bearer Token。

请求体是**图片原始二进制**，不是 JSON、Base64，也不是 `multipart/form-data`。建议使用实际图片 MIME，例如 `Content-Type: image/png`；服务端依据文件真实内容验证格式。

| 项目 | 限制 |
|---|---|
| 图片类型 | JPEG、PNG、WebP，单帧 |
| 文件大小 | 大于 0，最多 20 MiB（20,971,520 字节） |
| 像素数 | 最多 40,000,000 像素，宽高均大于 0 |

```json
{
  "media_id": "0123456789abcdef0123456789abcdef",
  "mime": "image/png",
  "size": 12345,
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "width": 640,
  "height": 480
}
```

回包字段均由服务端生成；示例各数值仅说明类型。上传成功后，把实际 `media_id` 用于图文包。接口不接受外部图片 URL 或调用方本地磁盘路径代替图片内容。

### 5.2 下载图片：GET /v1/media/{media_id}

完整地址示例：`http://127.0.0.1:8770/v1/media/0123456789abcdef0123456789abcdef`。使用 Butler Bearer Token。

路径参数 `media_id` 为上传接口生成的 **32 位小写十六进制字符串**，无请求体。成功返回原始图片字节，响应头为对应 `image/png / image/jpeg / image/webp`，并带 `Cache-Control: no-store`；不存在返回 404，ID 或缓存校验失败返回 400。

### 5.3 图文项目 items 的统一格式

`/v1/push/bundle` 与 `/send-bundle` 共用以下格式，按数组顺序发送：

```json
[
  {"kind": "text", "text": "图片说明"},
  {"kind": "image", "media_id": "0123456789abcdef0123456789abcdef"},
  {"kind": "text", "text": "补充内容"}
]
```

| 参数 | 类型 | 约束 |
|---|---|---|
| `items` | object[] | 1～50 项，可只有文字、只有图片，或两者混合 |
| 文字项 | object | 只能包含 `kind: "text"` 和 `text`；正文必须是非空白字符串，最多 10,000 字符 |
| 图片项 | object | 只能包含 `kind: "image"` 和 `media_id`；ID 必须为 32 位小写十六进制 |
| `request_id` | string | 1～200 字符，只允许英文字母、数字、`_ . : -`；调用方提供稳定 ID |

单项不允许额外字段，不支持文件路径、外部 URL、文件、视频、语音等 `kind`。图片必须先上传到 Butler，并保证 wxbot 能使用配置的 Butler 地址和 Token 取到图片。图文包仅支持 `wechat.mode="main"`，还需要本机图片发送控件配置可用。

### 5.4 经 Butler 发图文：POST /v1/push/bundle

完整地址：`http://127.0.0.1:8770/v1/push/bundle`。使用 Butler Bearer Token。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `contact` | string | 是 | 非空，最多 200 字符；必须在新闻订阅分组 `groups["1"]` 中 |
| `items` | object[] | 是 | 同 5.3 |
| `request_id` | string | 是 | 同 5.3 |

顶层必须恰好只有以上三个字段，不接收 `type / messageType / wait / timeout`。

```json
{
  "contact": "张三",
  "request_id": "news-20261028-001",
  "items": [
    {"kind": "text", "text": "今日图片新闻"},
    {"kind": "image", "media_id": "0123456789abcdef0123456789abcdef"}
  ]
}
```

```json
{"ok": true, "detail": "sent", "contact": "张三", "request_id": "news-20261028-001"}
```

此接口与普通 `/v1/push` 的回包结构不同，结果在顶层 `ok`。未订阅新闻返回 403；包格式或媒体无效返回 400；订阅策略暂不可读返回 503。发送等待上限取 Butler `[wxbot].timeout`。

可事先调用 `GET http://127.0.0.1:8770/v1/telegram-relay/authorize?contact=张三` 查询订阅资格。唯一查询参数 `contact` 必填、非空、最多 200 字符；中文需 URL 编码，使用同一 Bearer Token。回包为 `{"contact":"张三","allowed":true}`。

### 5.5 直接提交图文：POST /send-bundle

完整地址：`http://127.0.0.1:8765/send-bundle`。使用非空配置的 `X-Wxbot-Token`。

| 参数 | 类型 | 必填 / 默认 | 说明 |
|---|---|---|---|
| `contact` | string | 必填 | 去首尾空白后非空，最多 256 字符 |
| `items` | object[] | 必填 | 同 5.3 |
| `request_id` | string | 必填 | 同 5.3 |
| `wait` | boolean | 可选；`true` | 提供时必须严格为 `true`，不能传 `false` 或字符串 |
| `timeout` | number | 可选；`60` | 解析后的等待上限须为有限正数且不超过 3600 秒；接入请直接传有效正数 |

顶层只允许上述五个字段。相比 Butler 图文入口，本接口不检查新闻订阅分组。

```json
{
  "contact": "项目讨论群",
  "request_id": "external-bundle-20261028-001",
  "items": [
    {"kind": "text", "text": "本次会议图片"},
    {"kind": "image", "media_id": "0123456789abcdef0123456789abcdef"}
  ],
  "wait": true,
  "timeout": 120
}
```

完成回包：

```json
{"ok": true, "detail": "sent", "contact": "项目讨论群", "request_id": "external-bundle-20261028-001"}
```

只有所有项目都确认发送，整个包才成功。正式入队前先校验并准备全部图片。wxbot 持久队列按 `contact + request_id` 复用相同内容的包，不能用同一键修改 `items`；但 HTTP 超时、断连或未知结果仍须核对，不应自动换新 ID 重发。通用超时回包可能只有 `ok / detail`，未必包含 `contact / request_id`。

## 6. 会话、主动问候及探活

### 6.1 重置会话：POST /v1/reset

完整地址：`http://127.0.0.1:8770/v1/reset`。使用 Butler Bearer Token。

| 参数 | 类型 | 必填 / 默认 | 说明 |
|---|---|---|---|
| `contact` | string | 必填 | 非空会话标题 |
| `channel_type` | string | 可选；`"dm"` | `dm / group` |
| `member_key` | string | 可选；`""` | 重置群成员会话时传对应成员标识 |
| `avatar` | string | 可选；`""` | 头像格式同 3.1 |

```json
{"contact": "项目讨论群", "channel_type": "group", "member_key": "member-a001"}
```

返回 3.1 的统一 `reply / actions / reply_parts / meta` 结构，`meta.reset=true`。重置模型会话不会自动删除已排队发件，也不会自动把回包中的提示发到微信。

### 6.2 触发一次主动问候：POST /v1/heartbeat/trigger

完整地址：`http://127.0.0.1:8770/v1/heartbeat/trigger`。使用 Butler Bearer Token。

唯一业务参数为必填字符串 `contact`，对应已经配置且已保存角色/Skill 策略的联系人。

```json
{"contact": "张三"}
```

```json
{"ok": true, "status": "started", "contact": "张三"}
```

成功返回 HTTP **202**，代表后台任务已启动；任务后续可能调用模型并投递微信。联系人未配置或策略缺失返回 400，心跳正在执行返回 409，调度器不可用返回 503。此接口与直接发送指定正文的 `/v1/push` 用途不同。

管理台另有 `POST http://127.0.0.1:8788/api/heartbeat-trigger`：请求体同样为 `{"contact":"张三"}`，当前路由本身无 Token 校验，使用管理台配置中的凭据转发 Butler；成功同样返回 202 和上述结构。业务程序接入宜直接使用带 Bearer Token 的 Butler 接口。

### 6.3 健康检查

| 完整地址 | 鉴权 | 典型回包 |
|---|---|---|
| `GET http://127.0.0.1:8770/health` | Butler Bearer Token | `{"ok":true,"hermes":{"wxbot-example":true},"contacts":["张三"]}` |
| `GET http://127.0.0.1:8765/health` | 无 | `{"ok":true}` |

Butler 的 `hermes` 字段为兼容历史接口保留。探活成功不表示微信窗口和后续实际发送一定成功。

## 7. 查询已经接收或发送的消息

以下均为 log 本机管理台的只读接口，没有请求体、当前未检查 Token。它们提供查询视图，不是可靠消息队列的消费/确认协议；字段可能随管理台版本变化。

### 7.1 GET /api/queue

完整地址：`http://127.0.0.1:8788/api/queue`。

| 查询参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `contact` | string | 空 | 按会话标题过滤 |
| `state` | string | `all` | `all / active / unbatched` 或具体队列状态，如 `pending / sent / blocked / uncertain`，按对应表生效 |
| `scope` | string | 空 | 支持 `all / active / issues / history`，按活动、异常、历史范围筛选 |
| `order` | string | 空 | `asc / desc`；未传时按范围选择排序 |
| `limit` | integer | `50` | 每个列表最多返回条数，微信队列限制为 1～200 |
| `offset` | integer | `0` | 非负偏移，作为微信列表的公共默认偏移 |
| `inbox_offset / batches_offset / outbox_offset / rounds_offset` | integer | `offset` | 对应列表的独立偏移 |
| `telegram_offset` | integer | `0` | Telegram 列表独立偏移 |

主要回包字段：`status / read_only / contacts / counts / pages / inbox / batches / outbox / rounds / events / telegram / error`。各列表保留对应记录 ID 和状态；部分表没有可用数据时可能缺少扩展字段。库不存在时可返回 `status="missing"`，不要把它当成空消息消费成功。

### 7.2 GET /api/flow

完整地址：`http://127.0.0.1:8788/api/flow`。

| 查询参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `contact` | string | 空 | 按会话标题过滤 |
| `limit` | integer | `50` | 1～100 |
| `offset` | integer | `0` | 非负偏移 |
| `order` | string | `desc` | `asc / desc` |

主要回包字段：`read_only / status / at / flows / contacts / sources / total / offset / limit / has_more / error`。`flows` 中可查看收件、模型处理和 `wechat_delivery` 事件；发件状态以实际队列及确认事件为准。

### 7.3 GET /api/workflow 与 GET /api/workflow-content

`GET http://127.0.0.1:8788/api/workflow` 无业务查询参数，返回工作流的 `sources / nodes / messages / counts` 等汇总信息。

`GET http://127.0.0.1:8788/api/workflow-content?id=...` 的唯一业务查询参数为必填字符串 `id`，最多 160 字符。直接使用工作流返回的记录 ID，不自行猜测；支持批次 ID、`inbox:<数字>`、`push:<发件ID>`、`tg:<bot_id>:<update_id>` 等格式。

```json
{"status": "ok", "id": "inbox:123", "kind": "inbox", "text": "收到的完整正文", "reply_text": ""}
```

批次记录可以同时返回完整 `reply_text`。记录不存在返回 404，ID 格式错误返回 400，读取暂不可用返回 503。文档以当前工作区实现为准，运行中的旧版 log 可能尚未提供全文接口。

### 7.4 GET /api/wxbot

完整地址：`http://127.0.0.1:8788/api/wxbot`。这是历史管理台的收发流水汇总视图，包含日志解析结果和内嵌 `flow` 查询结果。

| 查询参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `flow_contact` | string | 空 | 过滤内嵌 `flow` 中的会话 |
| `flow_offset` | integer | `0` | 内嵌 `flow` 的非负偏移 |
| `flow_order` | string | `desc` | 内嵌 `flow` 的 `asc / desc` 排序 |

主要回包字段为 `ok / log / log_exists / generated_at / window_s / stats / contacts / events / flow`。这三个筛选参数只作用于内嵌 `flow`，不会把外层全部历史日志按同样条件筛选。需要直接查询持久队列中的实际收发状态时，使用 7.1、7.2 的接口。

## 8. 调用示例

以下命令是接入模板，本文整理和验证过程没有执行真实消息发送。将占位符替换成自己的 Token 和目标；Windows 使用 `curl.exe` 避免 PowerShell 别名差异。

### 8.1 接收处理

把 3.1 的私聊请求保存为 UTF-8 文件 `handle.request.json`，再执行：

```powershell
curl.exe -X POST "http://127.0.0.1:8770/v1/handle" `
  -H "Authorization: Bearer <BUTLER_TOKEN>" `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@handle.request.json"
```

### 8.2 主动发送文字

把 4.1 的指定会话请求保存为 UTF-8 文件 `push.request.json`：

```powershell
curl.exe -X POST "http://127.0.0.1:8770/v1/push" `
  -H "Authorization: Bearer <BUTLER_TOKEN>" `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@push.request.json"
```

若直接调用 wxbot，将地址改为 `http://127.0.0.1:8765/send`，鉴权头改为 `X-Wxbot-Token: <WXBOT_TOKEN>`，请求内容使用 4.2 的格式。

### 8.3 上传图片

```powershell
curl.exe -X POST "http://127.0.0.1:8770/v1/media" `
  -H "Authorization: Bearer <BUTLER_TOKEN>" `
  -H "Content-Type: image/png" `
  --data-binary "@example.png"
```

取回包中的实际 `media_id` 填入 5.4 或 5.5 的 `items` 再发送。

### 8.4 查询收发状态

```powershell
curl.exe -G "http://127.0.0.1:8788/api/flow" `
  --data-urlencode "contact=张三" `
  --data-urlencode "limit=20" `
  --data-urlencode "order=desc"
```

## 9. 错误处理与实现边界

| HTTP 状态 / 业务结果 | 含义与处理 |
|---|---|
| `200` 且 `/v1/push.meta.ok=false` | 发送失败或无群发目标，读取 `meta.detail / results` |
| `200` 且 `/send`、图文接口顶层 `ok=false` | 执行失败或等待超时，读取 `detail`，核对队列 |
| `200` 且 `/v1/handle.meta.reply_complete=false` | 模型结果未完成，不投递；结合 `error / retry_safe` 处理 |
| `202` | 心跳后台任务启动，不等于消息发送成功 |
| `400` | 参数、图片、消息包或重复 ID 内容冲突；修正请求再提交 |
| `401` | Token 缺失、错误；注意区分 Bearer 和 `X-Wxbot-Token` |
| `403` | 图文 Butler 入口的目标未订阅新闻 |
| `404` | 路由、图片或查询记录不存在，也可能运行的是旧版本服务 |
| `409` | 本文心跳接口表示已有心跳正在执行 |
| `500 / 503` | 服务配置、模型异常、存储或依赖服务不可用；读取实际回包 |

Butler 参数错误通常为 `{"error":"..."}`，wxbot 通常为 `{"ok":false,"detail":"..."}`，图文 Butler 校验错误可为 `{"ok":false,"error":"..."}`。不要假设所有接口共享同一错误结构。畸形 JSON、非对象或超限输入的处理尚未完全统一，调用方应按本文类型构造有效请求。

本项目没有提供 `/v1/chat/completions` 作为 Butler 对外收件接口；配置中的该类地址属于外部模型后端。`/mcp` 使用服务签发的临时能力凭据，不是普通收发消息入口。用户记忆管理、配置修改、队列删除及人工核对路由不在本文收发接入范围内。

## 10. 源码依据

| 文件 | 核对内容 |
|---|---|
| [src/butler/server.py](../src/butler/server.py) | Butler 路由、鉴权、HTTP 参数及状态码 |
| [src/butler/agent/core.py](../src/butler/agent/core.py) | 处理结果结构、身份观测、单发和群发业务 |
| [src/wxbot/outbound.py](../src/wxbot/outbound.py) | `/send`、`/send-bundle`、等待语义及鉴权 |
| [src/wxbot/processor/butler.py](../src/wxbot/processor/butler.py) | 实际 wxbot → Butler 请求和回复解析 |
| [src/wxbot/delivery.py](../src/wxbot/delivery.py)、[src/wxbot/queue_store.py](../src/wxbot/queue_store.py) | 持久入队、图文幂等和本地发送回执 |
| [src/common/media_bundle.py](../src/common/media_bundle.py)、[src/butler/delivery/media.py](../src/butler/delivery/media.py) | 图文和图片格式限制 |
| [src/common/avatar_identity.py](../src/common/avatar_identity.py)、[src/butler/identity/user_registry.py](../src/butler/identity/user_registry.py) | 头像编码与身份观测约束 |
| [src/butler/identity/group_context.py](../src/butler/identity/group_context.py) | 群归档格式、序号及幂等 |
| [src/butler/channels/telegram/bot/inbox.py](../src/butler/channels/telegram/bot/inbox.py) | Telegram 收件校验和持久化回执 |
| [src/butler/channels/telegram/bot/service.py](../src/butler/channels/telegram/bot/service.py) | Telegram 桥接筛选和保留字段 |
| [src/butler/delivery/push.py](../src/butler/delivery/push.py)、[src/butler/identity/groups.py](../src/butler/identity/groups.py) | 发件转发、超时和订阅分组 |
| [src/dashboard/server.py](../src/dashboard/server.py)、[src/dashboard/queue_view.py](../src/dashboard/queue_view.py)、[src/dashboard/flow_view.py](../src/dashboard/flow_view.py)、[src/dashboard/workflow_content.py](../src/dashboard/workflow_content.py) | 本机查询接口 |
| [src/butler/defaults.py](../src/butler/defaults.py)、[安装引导](CODEX_INSTALL.md) | 代码默认值、接入模式和本机配置生成 |

本次已通过 `test_transport.py / test_push.py / test_media_outbound.py / test_group_public_context.py / test_telegram_media_store.py / test_groups.py` 六个现有测试文件的离线验证，并检查 JSON 示例和源码链接。测试使用临时数据、假模型和假投递；本文件不包含真实 Token、用户聊天内容或真实微信发送验证。

### 管理台删除定时任务

本机管理台可向 `POST /api/jobs/delete` 提交 `{job_id, version, acknowledge:true}`，使用 JSON、同源请求及 `X-Wxbot-Job-Action: 1`。`job_id` 和 `version` 分别来自任务列表的 `job_id` 和 `delete_version`。页面先请求确认，再由 log 持服务端 Token 转发到 `POST /v1/jobs/delete`；浏览器不持有 Token。

删除停止该条 Butler 提醒的未来执行并从任务列表移除，保留删除操作记录。正在投递或版本已变化时返回 409，已删除／不存在返回 404，未确认或参数无效返回 400。取消、已发送和失败记录也可删除；已发送的微信消息不会撤回。其他调度器的旧任务需到对应调度器操作。
# 模型流式回复（2026-10-29）

`POST /v1/handle-stream` 为 Butler 的流式处理入口，沿用 `/v1/handle` 的 Bearer Token、身份校验和请求参数。
响应为 SSE，`data:` 中是 JSON 对象：`backend`（实际后端及能力）、`summary_delta`（公开摘要）、
`tool`（工具进度）、`answer_delta`（正文增量）、`error`（中止）；最终 `result` 事件的 `result` 字段
为原完整处理接口的响应对象。没有正常最终结果的连接按中断处理，不能自动重新提交模型请求。

`answer_delta` 只有显式 `sendable=true` 才可作为提前发送正文；摘要和工具进度不进入发件队列。
Butler 需要补发拼接、旧行动标记处理或无法预先固定群提及身份时，会等最终结果再输出正文。
原 `/v1/handle` 继续返回完整 JSON，兼容原调用方。

管理台 `GET /api/workflow-stream?id=<批次ID>&after=<游标>` 只读本地持久化公开事件；
它不生成回复或恢复请求。字段及微信三种回复方式见 [LOG_DASHBOARD.md](LOG_DASHBOARD.md#回复方式)。
