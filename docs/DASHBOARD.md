# 微信管家日志（wechat-inbox）

**当前界面说明：[管理页面说明](LOG_DASHBOARD.md)**。
管理台由 Vue 3 前端提供，挂在 `http://127.0.0.1:8788/app/`；根路径 `/` 会 302 到 `/app/`，保留原有 `?tab=` 参数。
实现与构建说明见 [web/README.md](../web/README.md)，改 `web/src` 后执行 `npm run build` 刷新即可，无需重启服务。
默认首页为「实时工作流」，每秒读取真实队列与阶段事件，按用户 UID／群成员查看当前位置、动态连线、工具进度和失败倒计时。「消息流转」独立页面已移除，旧链接自动打开实时工作流；更新后刷新浏览器即可。

实时工作流中的节点和消息列表统一显示前 20 个字，超出部分用“…”省略。点选消息后按需读取正文与完整回复，保留换行，不受 240 字预览限制；正常轮询不重复下载未变化的全文。切换消息或离开页面后，旧请求不会覆盖当前详情。全文查询使用只读接口 `GET /api/workflow-content?id=消息标识`，微信与 Telegram 的数据库路径均来自服务端配置。
2026-10-21 起采用左侧分组导航、分类配置与独立队列分页，并增加模型失败自动恢复（未提交安全重试、未知结果到期放行）。下方按日期保留历史实现记录；
旧的“全部配置”“心跳与角色”入口现在分别是“配置管理”“角色与心跳”。
Hermes 专属数据路径和重启说明仅适用于显式启用的旧后端。

展示微信通道流水、定时任务、用户分组、角色心跳，以及收发队列和配置总览。

展示消息、请求阶段与工具名称/执行状态；不记录模型内部推理、工具参数/结果、token 和成本。

查询接口只读数据库。写接口维护配置、用户分组和心跳角色策略文件；队列人工核对接口在明确确认后修改指定异常任务并记录审计，不操作微信界面。

## 消息流转记录（2026-10-18）

历史实现记录：该独立页面已于 2026-10-28 移除；`?tab=wxbot&kind=flow` 旧链接现在打开「实时工作流」。底层日志、只读查询接口和队列数据继续保留。

- 从 SQLite 中已持久化的 wxbot 收件开始显示，即使消息还未合并、尚未到 Butler，也能看到。旧任务阻塞时显示阻塞 ID、原因；log 查询不自动恢复或跳过，wxbot 运行时会按下述3分钟规则结束失败发件。
- 按 `contact + msg_id`（队列批次 ID）关联 wxbot 请求、Butler 接收/会话等待、Hermes 接受/工具开始与结束、完整结果、发件入库及微信发送状态。多条消息合并为一轮时列出收件序号；不使用时间接近来推断本轮阶段成功。
- 显示时间、耗时、HTTP 状态、工具调用 ID 与异常类型。工具 `completed` 仅表示执行结束。历史没有阶段记录时显示「未记录 / 未确认」，尚未成批的消息后续阶段显示「未提交」。发送状态来自队列，不把生成回复当成已发微信。
- wxbot 事件默认追加到队列数据库旁的同名 `.flow.jsonl`；Butler 事件追加到 `[log].flow_file` 解析后的路径加 `.events.jsonl`。例如 `cache/wxbot_queue.flow.jsonl`、`{hermes.root}/cache/wxbot.log.events.jsonl`。「全部配置」可看推导路径。看板只读这些文件，每个文件最多读取末尾 4MB，并标明截断/缺失/读取失败。
- Butler 内部订阅 Hermes SSE 工具事件，仍等待完整结果后一次返回 wxbot。请求添加 `hermes_final_response=true`，只接受同一 completion ID 的 `hermes.final_response` 最终正文，并验证正常结束和 `[DONE]`；不拼接中间稿，不记录 reasoning/工具参数/工具返回正文，不因断流自动重跑模型。
- 旧 Hermes 没有最终正文事件时会明确报错，不能用半截稿降级回复。首次安装流转功能时需用户先停 wxbot，自行重启更新后的 **Hermes、Butler、log**，再启动 **wxbot**。模型异常任务仍需人工核对；发件异常适用下述超时规则。

只读接口：`GET /api/flow?contact=&limit=50&offset=0`。`GET /api/wxbot` 同时附带 `flow` 数据，支持 `flow_contact` / `flow_offset` 分页参数；历史聊天流水保留。

## 收发队列 / 全部配置（2026-10-18）

- **收发队列**：打开 `http://127.0.0.1:8788/app/?tab=queue`。按会话、状态筛选，查看待合并消息、模型批次和回复分句；每类每页最多50条。顶部统计为全队列数量，列表按当前筛选显示。
- 每个会话明确显示当前等待原因及阻塞任务ID。例如旧发件 `blocked` 时，后面的新消息会保留等待，不会提交给 Butler。异常任务旁直接显示 **重试 / 确认已发 / 立即丢弃** 按钮，操作前弹窗确认；对应恢复命令仍可展开复制。只处理该句，原文和记录保留。人工重试前需核对微信实际结果并清理残留草稿。
- 发件 `blocked` / `uncertain` 从首次失败起按 `queue.failure_discard_seconds`（默认180秒）由 wxbot 巡检自动丢弃，页面显示倒计时。首次失败时间持久保存，重试/重启不会重置；待发送和正在输入、确认的任务不会被超时流程打断。模型结果不确定的批次不自动丢弃。倒计时按文件配置计算，修改后需重启wxbot，页面未核验进程已加载的值。
- 页面下方 **发送失败与人工核对记录** 显示最近50条失败、超时、重试、确认已发和人工丢弃记录；可展开失败现场信息。旧页面快照不能更改已更新的任务。
- **全部配置**：打开 `http://127.0.0.1:8788/app/?tab=configuration`。编辑 wxbot / Butler 的文件参数及默认值、联系人、角色/Skill/心跳策略、用户分组和log启动设置。每项有中文名称、用途、原键名、来源和生效提示，支持分类和搜索；运行事实、推导路径和机制说明只读。
- 文件值、代码缺省值、固定规则、log运行参数分别标注；**文件内容不代表运行中 wxbot / Butler 已加载的配置**。页面不会查询/重启它们以确认生效。
- API key、token、Authorization、密码以及URL内凭据在服务端脱敏；浏览器只收到隐藏状态。密钥默认保持不变，可明确替换或清空；含隐藏凭据的URL修改时需输入完整新值，星号不能写回配置。读取错误不回显文件原文。来源文件不存在时会标出，明确保存才创建。
- URL 无法解析时整段隐藏。log 与 Butler 的 home / 分组来源不同时分别展示并提示，避免把看板当前维护的文件误认为 Butler 已加载的文件。
- 顶部「自动刷新」可开启15秒刷新，默认关闭；倒计时每秒更新。GET 查询只读，不恢复/迁移队列、不创建运行锁。人工操作接口只修改异常任务状态，不执行shell命令、不操作微信，待发送的重试任务由 wxbot 正常调度。
- 队列路径读取 `WXBOT_CONFIG` 指定文件，缺省为项目 `config.wxbot.toml`；队列相对路径与 wxbot 一样按项目根目录解析，默认 `cache/wxbot_queue.sqlite3`。支持查询旧版磁盘队列；内存队列无法从另一个进程读取。
- 发送失败规则和按钮需由用户自行重启 **wxbot → log**。仅 wxbot 运行时执行版本3迁移，log 对旧库保持只读并提示先升级。旧失败发件按已有失败时间补记，超过180秒会自动丢弃。Butler / Hermes 无需为本次改动重启。

新增接口：`GET /api/queue?contact=&state=active&limit=50&offset=0`、`GET /api/configuration`。
队列接口返回同一SQLite读事务中的统计、会话原因和分页行；`state=all` 含历史完成任务，`active` 只显示未完成任务。队列视图为独立 `queue_view.py`，配置视图及脱敏为 `config_view.py`，HTTP层不持有UI对象。

人工核对：`POST /api/queue-action`，JSON包含 `id`、`kind=outbox|batches`、`contact`、`action=retry|sent|skip`、`expected_state`、`expected_finished_at`、`acknowledge=true`，模型批次还须 `expected_attempts`；请求头 `X-Wxbot-Queue-Action: 1`。校验同源、联系人和任务快照，只允许 `blocked` / `uncertain`；模型批次只支持重试/丢弃且必须没有发件结果。只操作服务器配置的队列文件，状态更新与审计处于同一事务。

批量删除：`POST /api/queue-delete-unsent`，请求体仅为 `{"acknowledge":true}`，沿用 `X-Wxbot-Queue-Action: 1`、JSON 和同源校验。队列路径来自服务端配置。删除微信与 Telegram 全部未成功记录，在写锁内先保存可恢复备份；返回两端 `deleted_messages`、`deleted_deliveries`、`protected_active`，微信还返回需清理草稿的会话数及 `protected_reads`（尚未实际采集的读取任务数，包含于保留总数）。正在输入、确认或提交的任务保留；已发送成功的记录保留。某一通道失败时，响应明确说明已处理的数量，不能把部分清理展示成全部成功。

## 配置编辑与生效

- 左侧选择分类，例如 **Butler · hermes**，修改 API 地址、API Key、模型或超时后点击 **保存此文件**。同一文件的多个分类共用一份草稿；切分类/标签页和自动刷新会保留草稿。重新载入或取消更改会放弃相应草稿，刷新整个浏览器会丢失未保存草稿。
- 整数/数值、布尔、文本及JSON使用对应输入控件；列表、联系人与映射支持JSON编辑。联系人名称须无首尾空格且唯一，uid须ASCII。隐藏会话模板按原名称或唯一稳定身份保留，身份合并有歧义时要求明确新值。角色与工具修改会检查Hermes技能目录与butler-role标签，白名单不能加入角色Skill。
- 每次仅保存一个来源文件，保留TOML注释和未改项。先校验类型、范围和关联参数，再在原文件旁生成 `原文件名.config-backup-时间-随机ID`，临时文件写好后原子替换。备份与配置含凭据，已加入Git忽略。版本过期返回409，原文件不被覆盖；校验失败返回400。保存动作不会调用模型或发送微信。
- `wxbot` 文件参数需自行重启wxbot；`Butler` 文件参数（包括Hermes调用地址）需自行重启Butler；角色/工具白名单/心跳开关与分组在后续读取时使用。心跳间隔仍由Butler启动配置控制。不会自动重启任何服务。
- log自己的设置保存在项目 `config.log.toml`，由 `python -m butler setup`／`init` 从代码默认值生成，也可在 **log · 启动配置** 页首次保存创建。修改后自行重启log；`LOG_CONFIG`可指定其他位置。命令行 `--host/--port/--home`、环境变量 `HERMES_HOME/WXBOT_CONFIG/BUTLER_CONFIG/BUTLER_GROUP_FILE` 优先于文件，运行参数区可查看当前值。`scripts\dashboard.bat`使用保存的默认设置，不再硬编码端口/home。
- 新增运行参数：`wechat.typing.chunk_size`（1–100，默认5）、`wechat.typing.chunk_interval`（0.05–10秒，默认0.5）、`queue.failure_discard_seconds`（1–86400秒，默认180）。失败期限始终从首次failed_at计算，已失败任务在重启后也使用新的期限。
- 保存接口为 `POST /api/configuration`：请求头 `X-Wxbot-Config-Action: 1` 与JSON；请求体 `{source, version, changes:[{path:[实际键路径], op:set|clear|default, value}], acknowledge:true}`。仅允许服务器已登记来源/字段，浏览器不能指定任意写入路径；受可信Host、同源与文件版本检查保护。`clear`只适用于敏感项，`default`只适用于有默认值的项。协议标识不参与值脱敏，防密钥恰好等于字段名称时改写保存路径。
- 配置编辑依赖 `tomlkit`，统一依赖清单已包含。更新后用户自行重启log显示新页面；使用新的输入/失败参数前需自行重启wxbot。Hermes进程自身监听端口由Hermes启动配置管理，本页的Hermes地址是调用目标。

## 快速开始

从仓库根目录启动（任选一种）：

```
scripts\dashboard.bat            # 读取 config.log.toml，成功后自动开浏览器
```

```powershell
.\.venv\Scripts\python.exe -m dashboard.server            # http://127.0.0.1:8788
.\.venv\Scripts\python.exe -m dashboard.server --port 9000
```

打开 http://127.0.0.1:8788/app/ 。服务只读运行数据、写配置文件，不启动或重启 wxbot、Butler。

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

深链接：`http://127.0.0.1:8788/app/?tab=wxbot&kind=slow&worder=asc`（wxbot 通道）
或 `http://127.0.0.1:8788/app/?uid=<uid>&order=asc&reply=1&q=关键词&tab=jobs`（定时任务）；
使用旧地址 `http://127.0.0.1:8788/?...` 会被 302 到对应 `/app/` 页面。

## 运维

服务挂了不用管，也不会丢消息：

```bash
# 看门狗（健康时静默无输出；掉线则自动拉起）
python heartbeat\wechat_inbox_watchdog.py --status
python heartbeat\wechat_inbox_watchdog.py

# 改了 src/dashboard/server.py 后重启（杀端口进程 → 看门狗拉起）
python scripts\restart_dashboard.py
```

- 开机自启：`scripts\launchers\wechat_inbox_autostart.vbs`（隐藏窗口）
- 看门狗定时任务：`微信收件日志-看门狗`，每 5 分钟，`no_agent`，**deliver=local 永远不会给你推消息**

## 导出目录

```
<Hermes 根目录>/logs/wechat-inbox/
    {uid}.jsonl    每行一条：time / ts / uid / name / content / session_id / profile
    {uid}.md       人看的版本，按时间倒排的引用块
```

## 坑 / 注意

- **只读**。连接一律 `file:...?mode=ro`，别改成写库——网关正在跑，有锁冲突风险。
- 「附带机器人回复」依赖 `delivery_obligations`，这张表**会被清理**。所以早期的收到消息可能查不到回复记录（例：8-07 那批就没有），这是正常现象，不是 bug。
- 回复的配对规则：某条「收到」之后、下一条「收到」之前发出的所有消息，都算对这条的回复。
- 「收到」的条数 **≠ 微信里真实收到的条数**：只有走完 agent 处理流程的消息才会落库。网关层被拦掉的（重复消息、被过滤的）不在这里。
- 想做到「秒级实时」要接 Hermes shell hook（`hermes hooks`），当前是手动/自动刷新轮询。
