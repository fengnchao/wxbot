# 管家（butler）— 独立启动的编排层

微信侧的"管家"从 wxbot 里拆出来，成为一个**能独立启动的 Python 项目**。
wxbot 只负责把消息从微信拿出来/发回去；管家负责"投递给 Hermes → 判断要不要调别的 skill → 出最终文案"。

## 请求流转与 Hermes 过程记录（2026-10-18）

- `/v1/handle` 在等待会话锁之前记录 `butler_received`，控制台立即打印关联的联系人和 `msg_id`。阶段事件写入现有流水日志路径加 `.events.jsonl`，由 log 页面只读展示。
- 普通消息仍走 `/v1/chat/completions`，保留两个 Hermes 会话头与原 `skill_policy`。Butler 内部请求 `stream=true, hermes_final_response=true`，记录工具名称、调用 ID、开始/结束及接口耗时；不记录模型内部推理、工具参数、预览 label 或工具返回内容。
- Butler 只使用 `event: hermes.final_response` 中同一 completion ID 的最终正文，并等待正常结束及 `[DONE]`，之后才解析行动标记、整理补发和返回完整 `reply/reply_parts`。中间 content 会被丢弃，防止把最终稿已经撤回的行动交给执行器。
- Hermes 返回普通 JSON 时仍兼容，但明确失败/不完整的结果被拒绝；过程流缺少最终正文、ID 错配或中断均不把半截内容当回复，不自动重试。旧 Hermes 需更新并重启以提供新增事件，其他客户端默认不接收该事件。

## 三个进程，两条边

```
                ① 用户消息
   微信客户端  ──────────────►  wxbot（项目目录）
   （UI 自动化）                      │  自己的内部逻辑：读窗口 / 判发送方 / /命令
                                     │
                                     │  ② POST http://127.0.0.1:8770/v1/handle
                                     │     {contact, text, msg_id?, ts?}
                                     ▼
                              管家 butler（本项目）
                                     │  ③ 投递：POST /p/<profile>/v1/chat/completions
                                     │     X-Hermes-Session-Key / X-Hermes-Session-Id
                                     ▼
                              Hermes 网关（大模型 + skill 运行时）
                                     │  ④ 模型结果
                                     ▼
                              管家 butler
                                     │  ⑤ 拿着结果**判断是否调用其他 skill**（调 / 不调）
                                     │     需要时执行本地 skill 脚本，或再问一次 Hermes
                                     │
                                     │  ⑥ 返回 {"reply": "..."}   ← 同步回复
                                     │  或 POST http://127.0.0.1:8765/send  ← 主动推送（提醒）
                                     ▼
                              wxbot ──⑦ UI 发给用户
```

## 职责边界（谁拥有什么）

| 关注点 | 归属 | 说明 |
|---|---|---|
| 聊天窗口定位、读消息、判发送方、发送 | **wxbot** | UI 自动化的一部分，不外移 |
| `/ping` `/reset` 这类通道级命令 | **wxbot** | 与业务无关 |
| 联系人 → Hermes Profile / uid 映射 | **管家** | 是业务身份，不是传输知识 |
| 身份注入（让模型知道 user_id 归到哪） | **管家** | 档案归档的正确性由管家负责 |
| 会话连续性（`X-Hermes-Session-Id`） | **管家** | 一条人 = 一段对话 |
| 补发队列（漏发的提醒） | **管家** | 认领 + 拼装，保证不丢 |
| 静默判定（不回复） | **管家** | |
| **skill 决策与执行** | **管家** | 本项目存在的理由：把"要不要调 skill"从提示词搬进代码 |
| 大模型调用、skill 的提示词内容 | Hermes | 管家只决定"调哪个"，不写提示词 |

## 接口契约

管家侧（wxbot 调它）：

```
GET  /health                     → {"ok":true,"hermes":{"wxbot-101":true,...},"contacts":[...]}
POST /v1/handle                  → {"reply":"完整文本"|null, "reply_parts":[...], "actions":[...], "meta":{...}}
     {"contact":"101","text":"...","msg_id":"...","ts":"...","channel_type":"dm|group"}
POST /v1/reset  {"contact":"101","channel_type":"dm|group"} → {"reply":...,"meta":{"reset":true,...}}
POST /v1/heartbeat/trigger {"contact":"101"} → 立即为该联系人执行一次心跳
POST /v1/push   {"contact":"101","text":"...","type":1,"messageType":1}
                                 → {"reply":null,"meta":{...}}   # 主动推送（不走模型）
     type: 1=指定用户发送（用 contact，缺省即 1）/ 2=群发（按 messageType 查「用户分组」字典，忽略 contact）
     messageType: 1=新闻消息 2=问候消息 3=其他（群发时必填；type=1 时仅记录）
```

`channel_type` 可选，缺省为 `dm`；群聊消息传 `group`，Hermes 身份注入会说明这是共享群会话，并将 `member_id` 解释为发言者标签。群聊与私聊的 Session Key 分开。两个请求都要求 `Authorization: Bearer <server.token>`；只绑 127.0.0.1。

### 完整回复与分句

Butler 等 Hermes 返回完整结果，执行行动并拼入已认领补发后才分句，一次返回全部内容：

```json
{"reply":"你好。今天怎么样？","reply_parts":["你好。","今天怎么样？"],"actions":[],"meta":{"msg_id":"wxbot批次ID","reply_complete":true}}
```

按 `。？！!?` 和代码区外的换行分句；连续句尾标点、右引号保留在前一句，拆分后的独立标点合入相邻正文；若整轮本来只有标点则保留原表达。逗号、ASCII 点、URL 查询符、行内代码和代码围栏不拆。静默返回空数组；全部 handle 路径均回显传入的 `msg_id`。旧客户端可继续只读完整 `reply`，无流式或迟到分句。

同一实际 endpoint/Profile/稳定会话 key 的整轮处理和 reset 串行，窗口别名共享 SID；不同身份可以并发。角色策略指纹与 heartbeat kind 继续隔离 SID。补发读取、归属过滤和认领在 Profile 锁内完成，锁不覆盖模型等待。支持字符串 `contact`、`uid`、`user_id`，提供的字段须全部匹配；旧无归属补发只允许明确且唯一属于该用户的 Profile，别名相同 UID 算同一用户。归属不明或认领失败的条目留存。

本地提醒文件操作共享 Profile 资源锁，delegate 透传当前角色和白名单；锁只协调当前 Butler 进程，不能协调 Hermes/cron 等外部进程写文件。

白名单边界沿用现有设计：`skill_policy.allowed_skills` 管理 Hermes 的 skill 目录和执行；Butler 自己的 `reminder.create` 等行动由固定 `CATALOG` 管理，两者名称不作隐式映射。本轮没有新增本地行动的动态权限配置。补发出现不支持的 recipient/receiver/to/target/user 等归属字段时保留未认领，不能按旧无归属记录投递。

用户分组字典（`{hermes.root}/cache/butler_groups.json`，`[groups].file` 可覆盖）：
`messageType → 绑定的联系人（微信窗口标题）`，群发按它逐条投递；log 看板 8788「用户分组」页
可视化管理（butler 每次推送现读文件，改完即时生效）。

## 联系人角色、skill 白名单与心跳

log 看板 8788「心跳与角色」页可为每个 Butler 私聊联系人选择 Hermes 角色 skill、多选允许使用的 skills，
并独立开关该用户的心跳。角色 skill 会自动并入白名单；普通消息每次动态读取配置并发送给 Hermes。
Hermes API 会按活动 Profile 校验 skill 名称，并在当前请求的 `skills_list` / `skill_view` 入口强制白名单。
未配置策略的联系人维持旧行为。策略改变后使用新的会话 id，长期身份 `X-Hermes-Session-Key` 不变。

策略文件默认 `{hermes.root}/cache/butler_heartbeat.json`；心跳状态文件默认
`{hermes.root}/cache/butler_heartbeat_state.json`，执行审计默认
`{hermes.root}/cache/butler_heartbeat_audit.jsonl`。可在 `[heartbeat]` 配置中覆盖路径与随机间隔。
审计记录包括调度启动/下次计划、被选用户与角色、Hermes 结果、建议推送状态和错误；不会记录普通聊天内容或密钥。
心跳调度随 Butler HTTP 服务启动，在进程内随机等待（默认 180–360 分钟），每次随机选择一位开启者。
心跳 Hermes 请求仅开放只读文件/会话/网页检索与 skills 查看工具；结果必须是 JSON 的 `none` 或 `suggestion`。
Butler 只把建议私聊给目标用户，不执行建议或 `butler:action` 指令。

推荐配置：

```toml
[heartbeat]
config_file = ""              # 默认 {hermes.root}/cache/butler_heartbeat.json
state_file = ""               # 默认 {hermes.root}/cache/butler_heartbeat_state.json
audit_file = ""               # 默认 {hermes.root}/cache/butler_heartbeat_audit.jsonl
min_interval_minutes = 180
max_interval_minutes = 360
```

wxbot 侧（管家推给它）：`POST http://127.0.0.1:8765/send` `{contact,text,wait:true,timeout}`，
退出语义沿用现有三态（0 已发出 / 1 通道不可用已入补发 / 2 该 Profile 没接 wxbot）。

## 行动指令协议（管家 → 模型 → 管家）

决策层要模型"说出来想干什么"，用的是**带外标记**，用户看不到：

```
<<butler:action {"skill":"reminder.create","args":{"text":"喝水","at":"2026-10-11 15:00"}}>>
<<butler:silent>>
```

管家收到回复后：剥掉这些块 → 按 `skills.py` 的白名单执行 → （可选）把执行结果再交给模型组织成人话。
模型不发标记 = 行为与今天完全一致（纯文本回复），所以协议是**增量**的，不会因为模型不配合而坏掉。
让模型发出标记的那段提示词，由 Hermes 侧 skill 提供（见 `skills.py` 的 `HERMES_HINT`）。

## 启动

```bash
python -m butler init                 # 从代码默认值初始化；保留已有配置
# 新安装选择接入方式请用 python -m butler setup，见 ../docs/CODEX_INSTALL.md
python -m butler.server --config config.butler.toml # 前台，本机模式
python -m butler.server --status                    # 探活 + 各 Profile 通不通
```

wxbot 侧切过来（**一行配置，可回退**）：

```toml
[model]
backend = "butler"                # 原来 hermes_butler → 现在走管家

[butler]
url = "http://127.0.0.1:8770"
token = "<server.token>"
timeout = 660
```

回退：`backend = "hermes_butler"` + 重启 wxbot。

## 目录

```
src/butler/       编排层 Python 包（wxbot ⇄ Hermes 之间那一层）
  config.py     配置读入（tomllib）      contacts.py  联系人 → Profile/uid + 身份模板
  hermes.py     Hermes 客户端（会话语义、存活探测）
  pending.py    补发队列（认领式）        router.py    决策层：/命令、静默、行动标记解析
  skills.py     可调 skill 白名单 + 执行器 core.py      编排：把上面几块按顺序串起来
  server.py     HTTP 接口（stdlib，无第三方依赖）
kmg/          看门狗（看门狗=kmg）：wxbot_watchdog.py / wechat_inbox_watchdog.py / sidecar_spawn.py
src/dashboard/          日志服务（8788 管理台）：server.py + web/（Vue 构建产物）+ 启动/重启 + launchers/
scripts/      运维脚本：投递（wxbot_deliver）/ 提醒（butler_reminder_*）/ 栈启停（wechat_stack_*）
              / wxbot 启停与自启 / wxbot_channel.json（投递映射）
tests/        conftest.py（夹具）+ test_pipeline.py（主流程不变量）+ test_transport.py（线格式/HTTP）
```

整个 `D:\bot` 树都可以整体搬走：脚本里对自身位置一律**自定位**（`__file__` 往上推），
只有"数据根"（`$HERMES_HOME`，即档案/补发队列/日志所在）和 cron 入口是写死的。

**cron 入口为什么要留在 Hermes 那边**：调度器只允许执行 `$HERMES_HOME/scripts/` 里
resolve 得进来的脚本（`hermes-agent/cron/scheduler.py::_run_job_script`，符号链接也会被
resolve 掉），所以 `$HERMES_HOME/scripts/` 里保留了 `wxbot_watchdog.py` /
`wechat_inbox_watchdog.py` 两个**转发 shim**（8 行 runpy），真身在 `kmg/`。

测试（唯一命令，全离线；真机探活用 `--status`）：

```bash
cd D:\bot && python -m pytest
```

## 还没做（下一步，按需要再动）

- `skills.py` 目前只落地了 `reminder.*`；`wechat-learn` / `wechat-quiz` 先以"再问一次 Hermes"
  的形式登记在册（决策在代码里，执行暂借 Hermes 的 skill）。
- 旧后端的 skill 脚本从已配置的 Hermes scripts 目录调用；等接口稳了再把
  `butler_*.py` 整体搬进本项目 `scripts/`，Hermes 侧只留它自己的东西。
- 行动标记那段提示词还需要写进各 Profile 的 SOUL / wechat-butler skill（否则模型不会发标记）。
