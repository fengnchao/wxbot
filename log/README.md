# 微信管家日志（wechat-inbox）

只做一件事：**把微信机器人收到的消息，按发送人分组记下来。**

不看思考过程、不看工具调用、不看 token 和成本——只看谁发了什么、什么时候发的。

所有数据库一律只读；写接口只维护用户分组、心跳角色策略配置文件，不动任何数据库。

## 快速开始

```
双击 start.bat
```
或
```
cd D:\bot\log
python server.py                 # http://127.0.0.1:8788
python server.py --port 9000
```
打开 http://127.0.0.1:8788/

## 页面

- **顶部**：发送人数 / 收到消息总数 / 时间范围
- **左侧发送人列表**：称呼、uid、收到条数、字数、近 7 天条数、最后活跃、最后一条内容预览
  - 称呼来自 `butler_profiles`（管家档案 `answers["0"]`），没档案的标「无档案」并只显示 uid
- **（已撤）** 原「收件流水」标签页于 2026-10-10 撤除：iLink 收件通道已退役，页面只保留 wxbot 通道与定时任务
- **排序**（开关，默认倒序）：倒序 = 最新在上；正序 = 最早在上
- **附带机器人回复**（开关，默认关）：打开后每条「收到」下面显示机器人**真实发出去**的蓝色气泡，并标注投递状态
- **搜索**：按消息内容过滤
- **导出**：全部 / 单人，格式 `.jsonl`（机器可读）或 `.md`（人看）

## 定时任务（第二个标签）

顶部「定时任务」标签，把当前所有 cron 任务做成卡片，**按归属分组**（用户 / 全局任务 / 系统无归属）。

「已完成」的任务**默认隐藏**（一次性提醒跑完就挪走，不刷屏）：右上角「显示已完成」按钮可切换，
侧栏会提示「隐藏已完成 N」，整组都是已完成时右侧显示提示。

左侧是归属列表（每项显示任务数 / 活跃 / 暂停 / 出错），点一下只看那一组；右侧每组标题下是卡片网格。

每张卡片显示：

| 字段 | 说明 |
|---|---|
| 任务名 + 状态徽章 | 运行中(绿) / 已暂停(灰) / 已完成(蓝) / 出错(红) |
| 计划 | `every 30m`、`0 9-18 * * 1-5` 之类 |
| 下次跑 / 上次跑 | 上次跑后面带 `· ok` / `· error` |
| 投递到 | `weixin:<uid>` 或 `local`；推出来的归属在后面括号标注来源 |
| 类型 | `agent` / `no_agent` / `script <名字>`，以及重复次数 `forever`、`1/1` |
| 推送 | 有线索时显示 `type=1 单发 · messageType=1（新闻消息）` 等 |
| 错误 | 有 `last_delivery_error` / `last_error` 时红字展示原文 |
| prompt 摘要 | 折叠，最多 600 字符 |
| 页脚 | job id + 所属 profile |

归属规则（按优先级，前一条推不出才看下一条）：

1. `deliver` 里的 `weixin:<uid>`
2. 所属 Profile 名反推：`wxbot-<uid>`（查 wxbot_channel.json）或 `wechat-<uid>`
3. **脚本同名 json**（`{HERMES_HOME}/scripts/<script名>.json`，no_agent 脚本约定）：
   `type=1` → 归 `contact` 指定的用户；`type=2` → **全局任务**（群发，收件人由「用户分组」字典按 messageType 决定）
4. **脚本文本内置目标**：`TARGET = "101"`（Hermes 生成的提醒 wrapper），或 `"wxbot-101"` 字面量（butler_reminder_* wrapper）
5. **prompt 里的 `--contact X` / `--to X`**（agent 任务实际执行的命令行）

都推不出来 → 「系统 / 无归属」（例如看门狗任务）。

分组按 **bare uid 小写** 归一，所以 `deliver` 里带 `@im.wechat` 的和 Profile 反推出来的会合并成同一个人。

## wxbot 通道（第一个标签，默认打开）

顶部「wxbot 通道」标签，展示 **wxbot 那条通道真实聊天窗口** 的收发流水：

- 谁（联系人）在什么时候**收到**了什么、机器人**回复**了什么
- 这一轮 **调用 agent 的耗时**（= 该轮 agent 会话首末消息时间差，秒，保留 1 位小数）；
  超过 **300s 标红并加「慢」徽章**
- 这一条外发**对应哪个任务**：外发时间 ±90 秒内有 cron 执行记录 → 标该任务名 + `job id` + **「推断」**；
  没有 → 「管家 / 手动推送」（**推断不当确定事实**）
- agent 侧明细：`session id` / API 调用次数 / 工具调用次数

倒序（最新在上）为默认；左侧按联系人过滤；右上下拉可只看「收发」「外发」「慢轮(>300s)」。
状态徽章：`ok` / `超时`（该轮出现 `Hermes API 调用失败: timed out`）/ `出错`。

数据源（全部只读）：

| 内容 | 来源 |
|---|---|
| 聊天窗口流水 | `cache/wxbot.log`（**逐行**先 utf-8 再 gbk 解码；多行正文接上一条事件；traceback/logging error 块整体跳过） |
| agent 耗时 | `profiles/wxbot-*/state.db` 的 `sessions`/`messages`（只读 URI）；收到时刻 ±15s 内的会话即那一轮 |
| 任务归属 | `cron/jobs.json` + `profiles/*/cron/jobs.json`，以及 `cron/output/<job_id>/*.md` 标题；执行记录在 `cron/executions.db` 与 `profiles/*/cron/executions.db` |

## 用户分组（第三个标签）

展示并维护 **推送分组字典**：`messageType（1=新闻消息 2=问候消息 3=其他）→ 绑定的用户（微信窗口标题）`。

- 列表每行一个类型，**点行头展开/收起**，展开后显示绑定的用户（chip，带 ✕ 可解绑）
- 绑定：从下拉选一个已绑定联系人，或直接输入窗口标题，点「绑定」
- 左侧可只看某一类型；底部显示字典文件路径与更新时间
- 字典文件默认 `{HERMES_HOME}/cache/butler_groups.json`（可用 env `BUTLER_GROUP_FILE` 覆盖），
  与 butler 侧一致：butler 收到 `type=2`（群发）的推送时，按此字典逐条转发

## 心跳与角色（第四个标签）

按 Butler 配置中的私聊联系人绑定 Hermes 角色 skill、多选运行时允许的 skills，并单独开关该用户的心跳。
角色 skill 自动加入白名单。Butler 普通私聊下一轮开始应用新策略；策略变化会切换 Hermes 会话 id，避免旧会话中残留已加载的角色或技能。

心跳由 Butler 进程内调度，每轮随机等待配置的间隔（默认 180–360 分钟），随机选一名心跳开启用户。
Hermes 心跳请求限制为只读工具与已选 skills，只能返回「无事」或一条建议；Butler 不执行建议中的操作，只通过微信私聊发给该用户。

配置文件默认 `{HERMES_HOME}/cache/butler_heartbeat.json`，由 `[heartbeat].config_file` 覆盖；调度时间默认在
`{HERMES_HOME}/cache/butler_heartbeat_state.json`。Hermes 技能目录由日志服务使用 Butler 配置中的 API 地址和密钥在服务端读取，密钥不会返回浏览器。
若 Butler 配置不在项目根目录 `config.butler.toml`，启动日志服务时设置 `BUTLER_CONFIG` 指向实际配置文件。

## 数据来源

| 内容 | 来源 |
|---|---|
| 收到的消息 | `messages` 表，`role='user'` 且 `sessions.source LIKE '%eixin%'` |
| 跨库合并 | `$HERMES_HOME/state.db` + `$HERMES_HOME/profiles/*/state.db`，共 4 个库 |
| 同一人归一 | `user_id` / `session_key` 去掉 `@im.wechat` 后缀，历史会话与新会话自动合并 |
| 称呼 | `$HERMES_HOME/butler_profiles/{uid}.json` 的 `answers["0"]`；其次 `{uid}_user.json` 的 `name` |
| 机器人发出的消息 | `delivery_obligations` 表（网关**真实外发队列**，`state='delivered'` 才是真送达），比从 assistant 文本里猜准确 |

## 去重

同一人跨库的消息按 `(uid, 时间戳, 内容 md5)` 去重，避免旧绑定和现有绑定重复记账。
系统注入的伪 user 消息（`[IMPORTANT: You are running as a scheduled cron job...`）会被过滤掉。

## HTTP 接口

```
GET /api/health
GET /api/jobs                               定时任务（按归属分组：用户/全局/无归属；?uid= 过滤）
GET /api/wxbot                              wxbot 通道流水：收到/回复/外发 + 这一轮 agent 耗时 + 任务归属
GET /api/groups                             用户分组字典（messageType → 绑定用户）
POST /api/groups  {type, action: bind|unbind, user}   增删绑定（写字典文件）
GET /api/heartbeat-config                   私聊联系人与已保存策略（不含密钥）
GET /api/heartbeat-status                   下次计划时间和最近心跳事件
POST /api/heartbeat-trigger {contact}       立即触发指定联系人的心跳
GET /api/skills?contact=<窗口标题>           经日志服务读取所选 Profile 的 Hermes 技能目录
POST /api/heartbeat-config                  保存联系人角色、skills 白名单和心跳开关
```

「心跳与角色」页显示下次计划时间和最近执行记录。审计文件默认位于
`{HERMES_HOME}/cache/butler_heartbeat_audit.jsonl`，可用 `[heartbeat].audit_file` 覆盖。
用户面板的「立即触发此用户」会绕过自动心跳开关，但要求已保存该联系人的角色和 Skill 配置；若已有一轮心跳在执行，会提示稍后重试。

深链接：`http://127.0.0.1:8788/?tab=wxbot&kind=slow&worder=asc`（wxbot 通道）
或 `http://127.0.0.1:8788/?uid=<uid>&order=asc&reply=1&q=关键词&tab=jobs`（定时任务）

## 运维

服务挂了不用管，也不会丢消息：

```bash
# 看门狗（健康时静默无输出；掉线则自动拉起）
python D:\bot\kmg\wechat_inbox_watchdog.py --status
python D:\bot\kmg\wechat_inbox_watchdog.py

# 改了 server.py 后重启（杀端口进程 → 看门狗拉起）
python D:\bot\log\wechat_inbox_restart.py
```

- 开机自启：`启动` 文件夹里的 `Hermes_WeChatInbox.vbs`（隐藏窗口）
- 看门狗定时任务：`微信收件日志-看门狗`，每 5 分钟，`no_agent`，**deliver=local 永远不会给你推消息**

## 导出目录

```
D:\ai\hermes\logs\wechat-inbox\
    {uid}.jsonl    每行一条：time / ts / uid / name / content / session_id / profile
    {uid}.md       人看的版本，按时间倒排的引用块
```

## 坑 / 注意

- **只读**。连接一律 `file:...?mode=ro`，别改成写库——网关正在跑，有锁冲突风险。
- 「附带机器人回复」依赖 `delivery_obligations`，这张表**会被清理**。所以早期的收到消息可能查不到回复记录（例：8-07 那批就没有），这是正常现象，不是 bug。
- 回复的配对规则：某条「收到」之后、下一条「收到」之前发出的所有消息，都算对这条的回复。
- 「收到」的条数 **≠ 微信里真实收到的条数**：只有走完 agent 处理流程的消息才会落库。网关层被拦掉的（重复消息、被过滤的）不在这里。
- 想做到「秒级实时」要接 Hermes shell hook（`hermes hooks`），当前是手动/自动刷新轮询。
