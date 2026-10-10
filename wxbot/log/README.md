# 微信管家日志（wechat-inbox）

只做一件事：**把微信机器人收到的消息，按发送人分组记下来。**

不看思考过程、不看工具调用、不看 token 和成本——只看谁发了什么、什么时候发的。

纯只读，不动任何现有数据。

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

顶部「定时任务」标签，把当前所有 cron 任务做成卡片，**按发送人分组**。

左侧是发送人列表（每人显示任务数 / 活跃 / 暂停 / 出错），点一下只看那个人的；右侧每组标题下是卡片网格。

每张卡片显示：

| 字段 | 说明 |
|---|---|
| 任务名 + 状态徽章 | 运行中(绿) / 已暂停(灰) / 已完成(蓝) / 出错(红) |
| 计划 | `every 30m`、`0 9-18 * * 1-5` 之类 |
| 下次跑 / 上次跑 | 上次跑后面带 `· ok` / `· error` |
| 投递到 | `weixin:<uid>` 或 `origin`（后者标「按 Profile 归属」） |
| 类型 | `agent` / `no_agent` / `script <名字>`，以及重复次数 `forever`、`1/1` |
| 错误 | 有 `last_delivery_error` / `last_error` 时红字展示原文 |
| prompt 摘要 | 折叠，最多 600 字符 |
| 页脚 | job id + 所属 profile |

归属规则：先看 `deliver` 里的 uid；`deliver` 是 `origin`/`local` 的，用**所属 Profile 名**反推
（Profile 名 = `wechat-<uid 小写>`）；都推不出来的归到「系统 / 无归属」（例如看门狗任务）。

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
GET /api/wxbot                              wxbot 通道流水：收到/回复/外发 + 这一轮 agent 耗时 + 任务归属
```

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
