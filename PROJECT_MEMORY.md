# 项目要点记忆

> 面向后续维护会话的速查文档。扫描日期：2026-10-14。以代码和配置模板为准；密钥、真实联系人和本机私有配置不记入本文。

## 项目定位

Windows 上的个人微信机器人，Python 项目，拆成两个本地进程：

- `wxbot/` 是 UI 收发层：默认通过 Windows UI Automation 扫描微信主窗口全部会话，采集后入 SQLite 队列，后台调用处理器、主线程模拟发送；兼容独立窗口模式。
- `butler/` 是对话编排层：提供 HTTP API，按联系人映射 Hermes Profile/uid，处理补发、会话、行动标记、提醒和主动推送。
- Hermes 网关提供模型与既有 skill runtime；默认地址/端口见 `config.butler.example.toml`（本地 8642）。
- 可选 `log/` 看板提供日志、任务和分组管理；`heartbeat/` 看门狗检查/重启进程；`scripts/` 提供启动、投递和提醒运维入口。

主要链路：微信主窗口 → `wxbot` SQLite 收件/合并 → 模型工作线程 `POST /v1/handle`（butler 8770）→ Hermes → butler → SQLite 发件 → wxbot UI 主线程回复。主动提醒链路为脚本/Hermes → butler `/v1/push` → wxbot 外发服务（8765）→ 发件队列 → 微信窗口。

## 关键边界和协议

- 窗口定位、轮询、消息差分、发送和 `/ping` 等通道命令属于 wxbot；联系人身份、Hermes Profile/uid、会话 id、补发、静默和 skill 决策属于 butler。
- wxbot 通过 `wxbot/processor/butler.py` 把消息发给 butler；仍支持 `echo`、Hermes/OpenAI 兼容和 Ollama 后端，路由见 `wxbot/main.py`。
- 主窗口默认无需绑定列表，群聊根据右侧人数标签识别；独立窗口/限定范围用 `[bot].bound_groups`。通过 `[bot].mention_names` 配置机器人昵称；仅处理包含 `@昵称` 的其他成员文字消息。WeChat UIA 不暴露群昵称，wxbot 用左侧头像感知哈希生成 member_id，可在 `[wechat.group_sender.member_names]` 配真实昵称；每批消息携 speaker/member_id 标签进入同一群聊会话。
- butler HTTP 接口都要求 `Authorization: Bearer <token>`：`GET /health`、`GET /v1/catalogue`、`POST /v1/handle`、`POST /v1/reset`、`POST /v1/push`。默认仅绑定 loopback。处理接口形状见 `butler/server.py`。
- Hermes 调用同时传 `X-Hermes-Session-Key`（长期身份/记忆归属）和 `X-Hermes-Session-Id`（同一段对话连续性）。只传前者可能每轮派生新会话。`/new` 或 `/重置` 会轮换会话 id。
- 模型行动标记 `<<butler:action {"skill":"...","args":{...}}>>` 由 `butler/router.py` 去除并交 `butler/skills.py` 白名单执行；未知 skill 失败留痕。现有 catalog：`reminder.create/list/cancel`（本地实现）、`learn.card`、`quiz.next`（再委派 Hermes）。`<<butler:silent>>` 等标记用于静默。
- 每条消息开始先认领补发队列，再调用模型；模型失败或静默时仍应送出已认领内容。队列 schema 复用 Hermes Profile 下的 `pending_delivery.py`。
- 主动推送不调用模型且不改会话。`type=1` 指定联系人；`type=2` 按 `messageType` 从 groups JSON 逐人发送。分组文件默认在 Hermes root 的 `cache/butler_groups.json`，可由配置覆盖，每次推送重新读取。

## 重要路径

- `butler/core.py`：主流程、补发、Hermes 调用、行动执行、出站推送。
- `butler/server.py`：HTTP 路由、Bearer 校验和状态探活。
- `butler/config.py`、`contacts.py`、`hermes.py`：配置、身份映射和 Hermes wire/session 语义。
- `butler/router.py`、`skills.py`、`pending.py`：路由/标记协议、skill 白名单、补发。
- `butler/groups.py`、`push.py`、`flowlog.py`：分组推送与流水日志。
- `wxbot/main.py`、`state.py`、`wechat/chat_window.py`：主轮询、消息差分、窗口读写。
- `wxbot/outbound.py`：接收主动推送的 HTTP 队列服务；`wxbot/processor/` 是各后端适配器。
- `log/server.py`、`log/index.html`：看板服务和前端；看板直接读取配置/日志/任务数据。
- `scripts/wechat_stack_ctl.py`：栈启停状态；`scripts/butler_reminder_*.py`：提醒创建/投递；`heartbeat/`：进程监控。
- `tests/`：离线测试，包括主流程不变量、HTTP/Hermes 传输、消息状态、分组、推送和任务归属。

## 配置与运行

- 根目录单一 `pyproject.toml` / `requirements.txt` / `.venv`。项目声明 Python 3.14+；依赖主要是 `uiautomation`、`requests`、`pillow`，开发测试用 pytest。锁文件为 `uv.lock`。
- 从 `config.butler.example.toml`、`config.wxbot.example.toml` 复制生成本地配置；两者分开且含 token/key 的本地配置不要提交。
- 启动 butler：`\.venv\Scripts\python -m butler.server --config config.butler.toml`；`--status` 做配置和 Hermes 探活。
- 启动 wxbot：`\.venv\Scripts\python -m wxbot.main`。默认保持微信主窗口打开；独立模式需打开绑定窗口。UI 自动化要求窗口可见、不遮挡，机器不能锁屏。控件变化时用 `tools/probe.py` 检查校准。
- 测试命令：`\.venv\Scripts\python -m pytest`（全离线）；此轮扫描未运行测试。
- butler 的本地提醒执行器从 `[dispatch].script_dir` 调 `butler_reminder_create.py`；补发程序从 `{hermes.root}/profiles/<profile>/skills/messaging/wechat-reminder/scripts/pending_delivery.py` 复用 Hermes 队列。

## 维护注意

- 服务启停偏好（2026-10-21）：Butler、wxbot 和 log 均由用户在 IDE 中手动启动。Codex 不代为启动或重启；改动需要重启时明确告知用户。
- 此仓库的 UI 自动化是非官方方式，存在账号风险；当前发送使用每 5 字、间隔 0.5 秒的 Unicode 模拟按键，绕过输入法转换，仍依赖窗口焦点。
- `config.*.example.toml` 是安全文档/示例来源；运行时配置可能含真实密钥，不要在日志、记忆或提交里复制秘密。
- `butler/README.md` 的示例含旧机器路径和过期目录/文件名（例如旧的根目录、`config.example.toml`、`kmg/`），实际操作请以根目录 README、当前代码和 `config.*.example.toml` 为准。
- `butler/skills.py` 的 `HERMES_HINT` 提供行动协议，但 README 记录提示词仍需由 Hermes Profile 的 SOUL/skill 引导模型发标记。
- `reminder.cancel` 直接更新 Hermes Profile 下 `reminders.json`，再原子替换 cron `jobs.json`；维护时注意提醒记录与调度任务要保持一致。

## 扫描时工作区状态

扫描时 `git status --short` 显示大量已修改、删除和未跟踪文件，涉及根目录重组（原 `wxbot/`、`wxbot-util/` 内容移至根目录布局等）。这些改动属于当时工作区现状，本次只新增本记忆文档；后续编辑前先检查 git diff，避免覆盖或误认为这些变化是新产生的。

## Butler 用户角色技能与心跳

- 日志服务「心跳与角色」页按 Butler `[[contacts]]` 配置私聊联系人，可设置 `role_skill`、`allowed_skills` 和 `heartbeat_enabled`。
- 策略默认存于 `{HERMES_HOME}/cache/butler_heartbeat.json`。log 服务只在服务端使用 Butler 配置中的 Hermes API key 查询技能目录，不把 key 返回浏览器。
- Butler 普通私聊每轮重读策略，并把 `skill_policy` 发送到 Hermes。Hermes 校验当前 Profile 中的 skill 名称，在执行线程作用域内限制 `skills_list` / `skill_view`；无策略请求保留既有行为。
- Butler 会话 id 根据角色与白名单指纹隔离；长期 session key 不变。群聊按群窗口名读取明确绑定的群策略，不继承成员的私聊角色策略。
- 心跳在 Butler 服务进程内调度，默认随机等待 180–360 分钟，每轮只随机选择一名开启者；下次触发时间存于 `{HERMES_HOME}/cache/butler_heartbeat_state.json`。
- 心跳请求单独会话，并在 Hermes 侧收窄为只读文件/历史/网页检索及 skill 查看工具。只接受 `{"action":"none","text":""}` 或 `{"action":"suggestion","text":"..."}`；Butler 只把建议私聊给目标用户，不执行建议。
- 代码改动后需要由用户自行重启 Butler、log 服务和 Hermes API 服务，使调度、UI/API 和 Hermes 运行时白名单生效；本次不会替用户重启。

## 微信主窗口监听（2026-10-17）

- wxbot 默认 `[wechat].mode = "main"`，从 `mmui::MainWindow` 的 `session_list` 读取会话行。行 `AutomationId` 形如 `session_item_<会话名>`，行 Name 的元数据 `[N条]` 是未读数，`[有人@我]` 是群提及提示；不能把消息正文里的数字当未读数。
- `wxbot/wechat/main_window.py` 负责功能栏聊天入口、列表分页扫描、选中会话、右侧标题校验；`wxbot/inbox.py` 负责每会话快照、未读任务、群提及过滤和回复。群聊根据右侧 `current_chat_count_label` 或标题末尾人数括号识别。
- `listen_all = true` 默认自动发现全部会话；false 时只处理现有 bound_users/bound_groups。群聊仍须配置 mention_names；已知群没有「有人@我」时保留未读并暂不切换。
- 当前打开会话即便没有角标也检查新消息。外发前保存未读任务，避免点击收件人清掉角标后漏收；回复后不覆盖收件快照；离开会话前再次读取当前面板，把模型等待/键入期间直接被微信标为已读的新消息加入下轮任务。
- 主窗口读控件深度默认 32。文字/头像识别与每 5 字、间隔 0.5 秒的发送复用 ChatWindow；每批输入和发送前核对聊天标题、前台窗口及输入焦点。已有绑定独立窗口兼容读取；mode=independent 可回退。
- 第一版只处理已加载且可判发送方的消息，不自动补读更老的未读历史；列表扫描最多 max_scan_pages（默认20）页。改动需用户自行重启 wxbot；不重启 Butler 或 Hermes。

## 主窗口持久化队列（2026-10-17，初版记录，后续行为以末节为准）

- `queue_store.py` 管 SQLite；`queue_worker.py` 单后台线程调用模型；`inbox.py` 只在 UI 线程采集和调度；`delivery.py` + `wechat/typing.py` 逐步发送并确认。UIA 控件不跨线程。
- 默认数据库 `cache/wxbot_queue.sqlite3`；消息、快照、未读任务、批次与发件均持久化，运行目录/数据库文件已 Git 忽略。消息和快照原子提交；点击前先保存未读任务，切换前再采集当前聊天。
- `[queue]` 默认 quiet_seconds=3、max_wait_seconds=10、confirm_timeout=5；模型队列1线程。连续同会话同成员文本合并，命令与其他群成员发言形成边界；未知成员不合并。已知有未采集未读时暂缓该会话成批。
- 同一会话旧批次直到回复确认送达才释放；执行期间的补充进下一批。不同会话按就绪顺序处理，不相互混合。打字间隔仅只读扫描可见列表、采集当前面板，不滚动/切会话。
- 回车后的新增自己气泡才算 sent，确认不依赖旧的已发正文缓存。模型异常/中断及未确认发件保留 uncertain，不自动重放。main 模式处理器透传网络异常，independent 保留原错误回复。
- 消息列表暂不可读必须报失败，不能用空列表覆盖锚点；明确未读且正文快照相同用未读尾部补采，无重叠但有未读时也优先采集可读取尾部。没有未读信号的完全相同有界快照仍无法可靠区分。
- 同名列表行依据同页重复或不同 UIA RuntimeId 检测，存在歧义拒绝选择；既有会话类型固定，模型发件从原批次 inbox 派生类型，每批键入/回车前核对。输入框内容不可读视为 blocked，不清空草稿。
- `python -m wxbot.queue_admin status/list` 查询不改变运行中任务；`retry ID [--delivery] --acknowledge`、`sent 发件ID`、`skip ID [--delivery]` 只恢复异常任务。已有发件的批次不能重跑模型。Butler 尚无幂等保证，显式重试前应核对工具是否执行过。
- OS 文件锁阻止同数据库重复 UI 实例；本次不改 Butler/Hermes 业务协议。仅需用户自行重启 wxbot，不自动重启任何服务。

## 主窗口与输入修复（2026-10-18）

- 根因：旧空闲轮询 `sessions(scan=True)` 会 SetActive + Wheel，读取当前会话又经 `_receive` 重选；现在闲时只读 UIA 暴露的全部行，`passive_window` 限定前台微信后用 `read_from_window`，不激活/移动鼠标/滚动。未暴露的屏外行不为闲时轮询主动补扫；有明确待采集或发件时才选择目标。
- `TypingSession` 正文改 `charMode=True`，避免输入法把汉字替换成前一个标点；非 BMP 字符拆 UTF-16 代理对。默认 5 字/0.5 秒，每批读回前缀、回车前验证全文；错误或输入不可读保留草稿，不自动清空/重打。
- 回车前 `before_enter` 纯读取当前面板，将新消息先通过 `_capture` 入库，再更新确认 baseline 和实际输入 `submitted_text`；随后再次检查对象、焦点和全文。被动收件也必须经过 `desktop.matches` 的同名歧义守卫。
- outbox 自动迁移 nullable `submitted_text`，原模型 `text` 保留。旧不确定任务仅用户明确确认已发后可登记实际正文，状态不变；新版本启动后按 baseline + 实际正文核对新增自己的气泡，确认后释放后续消息，不做模糊匹配或重发。
- 验证：全套离线测试 123 passed in 15.19s，语法/TOML/空白检查通过；独立只读审查通过。本轮没有操作真实微信收发或重启服务，实机行为待用户自行重启 wxbot 后观察。

## 完整回复分句与界面调度（2026-10-18）

- Butler 在行动/补发整理后调用纯函数 `butler/reply.py:split_reply`，HTTP 新增 `reply_parts` 和 `meta.reply_complete=true`，全部 handle 路径回显 `msg_id`；保留完整 `reply`。Hermes 继续完整生成，不接流式。
- `butler/concurrency.py` 按 endpoint/Profile/稳定 key/kind 提供可重入会话锁，Core 整轮和 reset 串行；Hermes SID 状态另按 policy 指纹隔离，别名共享实际身份状态。心跳独立 kind。Profile 锁覆盖补发 take/filter/flush 和本地 reminder 文件/子进程操作，不覆盖模型或 delegate 等待；delegate 透传策略。锁仅限当前 Butler 进程。
- 明确字符串 contact/uid/user_id 必须全部匹配；无归属旧补发仅明确唯一 Profile 用户可认领，同 UID 别名算一人；归属/认领不明的保留。假脚本已实际移除认领项以验证并发去重。
- wxbot 使用不可变 `Reply(text,parts)` 连接后端和队列。Butler 适配器一次请求读取全部数组，坏数组整体退回完整正文；明确未完成或请求 ID 错配抛异常并保留 uncertain。其他后端/命令/主动推送保留单条，独立模式返回完整正文；群 reset 传 channel_type=group。
- `[queue].max_model_requests` 默认2，须正整数且不接受 bool；固定 daemon 线程只处理纯数据，停止使用统一 join 截止时间，未停止不关闭 store/运行锁。同会话整轮所有分句终结前不提交下一批。
- `queue_schema.py` 在 runtime 取得 OS 锁后事务升级：outbox 去除 batch_id 唯一，增加 part_seq，与 batch_id 联合唯一；保留全局 seq/高水位、旧 ID/全部值。batches 增 reply_text/reply_complete/part_count；delivery_turns 持久化最近服务次序。旧发件映射单句，不重新拆。
- 新分句 id 为 `批次ID:part_seq`。每用户仅领取最早未终结一句，按 last_turn/global seq 公平轮转，确认或人工终结才推进次序；A3/B2 可交错 A1/B1/A2/B2/A3。完成一句不提前结束整轮；recover/retry/sent/skip 共同重算全部句状态，重复终结不重复推进。
- MainInbox.poll 默认被动；`_receive_one` 每次一个会话，失败按轮询间隔重试；收/发均积压时交替，一句 typing/confirming 期间只读登记角标、采集当前面板，不切换。发送目标捕获/切换前捕获/回车前捕获属于当前发送安全准备。
- CLI status/list 使用 mode=ro，无迁移/recover/WAL设置，兼容旧库；恢复命令 mode=rw 仅接受新版 schema，list 显示句序/总数和整轮进度。模型/发送不确定均不自动重跑，已确认分句不重发。
- 最终审查补充：停止 Event 立即生效，不等待数据库/领取锁；已领取但尚未调用模型的批次遇停止退回 ready。补发正文逐项校验，坏项不认领；未知 CamelCase/复合/嵌套收件字段保留。代码围栏按实际长度匹配，拆句产生的纯标点合入相邻正文；整轮仅标点仍保留原表达。Butler 固定本地行动 CATALOG 与 Hermes allowed_skills 保留两层权限边界。
- 当前离线验证：**200 passed in 18.29s**；44 个 Python/示例 TOML 文件解析、空白检查及最终独立审查通过，无剩余 Critical/Important。未访问真实队列迁移、未发送微信测试消息、未重启服务、未提交 Git。交付后用户先停止旧 wxbot，再自行重启 Butler 和 wxbot；Hermes 无需为此功能重启。

## log 收发队列与全部配置（2026-10-18）

- 用户已自行解决重复补采问题，本轮不再修改接收循环。新消息停在「等待连续消息合并」的只读诊断结果为：101 的旧发件 blocked，同会话顺序保护阻止新批次提交 Butler；不自动清理、跳过、重试或标记已发。
- log 新增 `?tab=queue`（收发队列）与 `?tab=configuration`（全部配置），对应 GET `/api/queue`、`/api/configuration`。支持会话/状态筛选、每类50条分页、配置搜索及可选15秒刷新。队列显示收件、模型批次、分句进度、阻塞ID/原错误和恢复命令文本；命令不由页面执行。
- `log/queue_view.py` 直接用 SQLite mode=ro、同一读事务读取统计/列表/原因，兼容旧schema；不实例化运行期 QueueStore，不执行迁移/recover/DDL，不创建运行锁。缺失数据库不创建。队列默认路径由 wxbot 配置相对项目根目录解析。
- `log/config_view.py` 展示 wxbot/Butler 全部文件值、默认值、固定输入规则、角色/Skill/心跳、分组及 log 来源。文件内容与其他进程已加载值明确区分；log 与 Butler 动态文件路径不同时分别展示并提示。错误路径或坏配置按来源隔离，不连带隐藏可读的队列。
- 凭据在服务端移除，包括敏感祖先、headers 列表、URL userinfo/query/fragment；无法解析的疑似 URL 整段隐藏。HTTP响应不包含原始key/token；读取错误只返回异常类别，不复制配置原文。前端转义所有配置/队列内容，旧标签页的迟到请求不得覆盖新页。
- 验证使用临时配置/数据库及临时预览服务：**214 passed in 18.56s**，5个Python文件AST与 `git diff --check` 通过，浏览器检查队列/配置搜索和布局，最终独立审查无 Critical/Important。临时预览已关闭；真实队列状态未改，未重启服务，未提交Git。
- 本轮功能仅需用户自行重启 **log** 后刷新浏览器；wxbot、Butler、Hermes 无需为这次看板改动重启。

## 消息端到端流转记录（2026-10-18，后续生效要求以本节为准）

- 本次只读检查时，101 有41条未成批收件，被旧发件 `0491097107174a2f8522c2e6087c8dc6` 的 blocked 状态阻止提交 Butler；原因为输入校验失败、未回车、草稿保留。真实队列未跳过/重试/清理，旧阻塞不会因加日志自动解除。
- 用户批准新增 wxbot 收件 → 合并/阻塞 → 请求 Butler/确认收到 → Hermes 接受/工具进度 → 完整结果/发件入库 → 微信分句状态。log「wxbot 通道」默认附消息流转卡片，可选「只看消息流转」，深链接 `?tab=wxbot&kind=flow`。`GET /api/flow` 支持 contact/limit/offset，`/api/wxbot` 附 flow；旧聊天日志保留。
- `common/flow_trace.py` 提供线程安全追加事件、ContextVar 请求作用域与字段白名单；不含 UI/业务依赖。wxbot 事件文件由数据库路径替换后缀成 `.flow.jsonl`；Butler 使用原 flow_log_path 加 `.events.jsonl`。错误写盘不导致业务失败/重放，控制台同时打印阶段。
- `ModelWorker` 把批次ID作为 msg_id 贯穿 `ButlerProcessor` 与 Butler；Butler handle 在等待会话锁前立即记录接收，HermesClient记录请求、接口接受、工具名/调用ID/状态和耗时。新事件不保存消息正文、reasoning、label、工具参数/结果或原始异常；旧正文流水仍按原功能保留。
- `log/flow_view.py` 用 mode=ro 读队列，精确按 contact+批次ID 关联两端事件，每文件只读末尾4MB并标记截断/缺失。未成批显示未提交，历史缺阶段显示未确认；不依据 reply_complete 推断发件成功，避免旧人工skip迁移记录误报。发送结果取持久发件状态，工具completed只显示执行结束。
- Butler 内部订阅 Hermes SSE，仍完整返回 wxbot，不流式发送微信。新增 `hermes_final_response=true` 请求标记；Hermes 原 Chat Completions 路由可选发送 `hermes.final_response`，含同一completionID、canonical最终content、completed/partial/failed。默认关闭，不改其他客户端、会话头、角色/skill_policy 路径。
- 必须用 canonical 最终正文，不能拼接普通content流（其中可能含中间稿、插件改写前稿及被撤回的行动标记）。Butler 校验 completionID + 最终事件 + stop + [DONE]；缺事件/错ID/断流/不完整均不使用半截稿、不自动重跑。缺事件的错误码 missing_final_response 会在看板提示更新并重启Hermes。普通JSON回包仍兼容，明确partial/failed/非stop拒绝。
- Hermes 增量位于 `D:/ai/hermes/hermes-agent/gateway/platforms/api_server_openai_routes.py`，新增opt-in真aiohttp假agent测试及API文档。该文件原已有角色策略改动，未覆盖其余未提交内容；两个仓库均未提交Git。
- 最终验证：wxbot项目全套 **233 passed in 22.76s**；Hermes标准 `scripts/run_tests.sh` 定向新增两项 **2 passed**；16个Python文件AST、两仓库相关diff空白检查及独立审查通过。浏览器仅使用临时队列/假事件查看布局和过程，截图 `.superpowers/message-flow-preview.png` 为演示数据。未操作真实微信收发、未重启任何服务。
- Hermes标准测试环境最初被既有pilk发布时间/依赖解析问题阻塞；改用独立venv通过pth只读复用已安装Hermes依赖和wxbot pytest，再经标准runner隔离执行。没有更改运行venv。临时服务已关闭；临时venv `.superpowers/hermes-flow-test-env` 的递归及逐文件删除均被自动安全审查以 blocked by policy 拦截，保留无运行进程的10个文件，后续不要自动反复尝试清理。Hermes全套未运行。
- 生效由用户操作：先停旧 **wxbot**，重启更新后的 **Hermes、Butler、log**，再启动 **wxbot**。用户要求不得自动重启 wxbot/Butler；本轮也未自动重启 Hermes/log。旧 blocked/uncertain 仍需用户核对实际微信/草稿后按队列页命令处理。

## 标点与丢字：分批粘贴修复（2026-10-18）

- 只读诊断：旧 101 发件的模型 `text` 标点正确，而实际 `submitted_text` 中标点后的汉字被替换为前一个标点，不能通过删除重复标点修复。启用 Unicode 键盘后仍有输入校验失败。此前「Unicode 键盘即可避免」的判断不成立，确切系统输入层成因尚未确认。
- 用户明确批准改为每5字分批粘贴、间隔0.5秒、全文校验后只回车一次；短暂使用剪贴板，离线验证、不发送微信测试消息。`wechat/typing.py` 改为字面 Unicode 剪贴板文本 + Ctrl+V，不再逐字模拟正文，也不擅自删除原正文中的重复标点。新增每批粘贴前的前缀复核，保留每批后及回车前的校验。
- `wechat/clipboard.py` 通过消息窗口持有剪贴板；备份可安全复制的原格式，按 UTF-16 字节数分配含 emoji 的文本内存。恢复时传入备份的副本，部分格式恢复失败仍保留完整备份；持锁记录自身修改的序号，后续用户复制的新内容优先。无法安全备份或输入不符即停止，不回退键盘正文输入、不清草稿。
- UI 主窗口 tick、独立模式轮询、发送结束及退出均尝试清理；Ctrl+C 等 BaseException 也做资源清理后继续抛出。独立窗口补上标题/前台窗口/输入焦点守卫。外部持续占用剪贴板到退出时只做最后一次尽力恢复并告警，强制终止无法保证恢复；不延长为无限退出等待。
- `log/config_view.py` 同步只读固定输入规则；运行日志显示「开始分批粘贴（每5字/0.5秒）」。未改 Butler/Hermes 协议、队列状态或发送确认策略，未重启服务、未提交Git。旧 blocked/uncertain 与残留草稿需另行核对恢复；没有自动跳过新阻塞任务。
- 验证：最终全套 **256 passed in 23.21s**，12个Python文件AST与 `git diff --check` 通过；独立只读审查无剩余 Critical/Important。新剪贴板边界测试使用假原生API，新增全局夹具阻止未注入替身的测试创建真实剪贴板对象。未发送真实微信测试消息，实际微信与原生粘贴兼容性待用户自行重启观察。
- 本次发送方式修复只需用户自行重启 **wxbot**，Butler/Hermes 不需要重启。若要刷新 log 的「全部配置」说明，需重新加载 log 服务；不影响 wxbot 实际发送方式。不要自动重启用户启动的服务。

## 阻塞恢复与 Hermes 重载（2026-10-18）

- 用户报告101被 `38ecdb3a1e6a4fdb89978bf99366ade6:1` 阻塞。只读核对为14:45生成的兜底道歉，输入校验失败、submitted_at为空；通过既有 queue_admin skip --delivery 跳过，旧批次done，后续批次 `207599e6f2634406be19d44577d7142b` 开始处理。
- 后续请求已到Butler且HTTP200，但日志报 Hermes missing_final_response，又生成19字兜底道歉。Hermes进程10:52启动，API路由源码13:44更新，运行时尚未重载。沿用用户先前「可以重启Hermes，别的项目别重启」授权，使用 `D:/ai/hermes/bin/hermes.cmd gateway restart`，新PID145032，16:34启动；8642已由新PID监听，GET /health HTTP200。没有重启wxbot/Butler/log，也未更改Hermes代码。
- 当前Hermes已采用PM管理启动器，旧 `D:/ai/hermes/hermes-agent/venv/Scripts/python.exe` 已不存在；不要继续使用仓库老bat中的venv路径。Hermes status曾显示已注册计划任务，通过gateway restart正常排空并重启。
- 新发件 `207599e6f2634406be19d44577d7142b:1` 停在「目标会话尚不可用，未键入」，submitted_at为空。用户确认微信已展开、101可以正常打开；显式重试这条未尝试回车的发件一次，仍在同阶段blocked，无键入/回车。未反复重试、未跳过这条新任务、未重跑模型。
- 微信与wxbot进程均在Windows会话3；四个wxbot.main相关PID实际是debugpy/venv启动链，并非已证明多个UI实例。当前工具禁用微信原生界面读取，已向用户请求本次失败前后10行wxbot控制台日志，用于区分重名守卫/标题匹配/输入框缺失；根因未定，不要声称发送恢复。Hermes最终正文事件还未用新的真实模型请求验证。

## 当前会话主动点击未读行（2026-10-18）

- 用户指出：消息来自右侧当前已打开的联系人时，程序只激活窗口，未主动点击会话列表头像，未读角标一直保留。源码确认 `MainWindow.select` 在 matches 为真时直接 SetActive + return。
- 新增显式 `click_current` 选择参数，仅 `_receive` 处理 unread_count>0 的任务时从 `MainChatWindow.available` 传到 select，绕过已选中会话/独立窗口快捷返回，主动点击一次对应会话行，随后照旧核对标题与消息区。独立窗口存在时先点击主列表，再激活并核对该独立窗口；保留同名拒绝、切换前采集、pending持久化、消息入库与类型守卫。
- 增加日志「已主动点击未读会话行」。空闲轮询和发送中的被动采集不传该参数，保持不点击/不切换；未@的已知群仍不主动打开。仅调整既有两个测试替身的 available 关键字兼容性，未新增或运行测试；四个Python文件语法解析与差异空白检查通过，实际角标清除待用户重启观察。
- 独立只读审查无新增Critical/Important/Minor。主动点击也适用于发送准备或启动恢复核对时捕获目标的明确未读任务；不会在typing期间的被动读取里点击。旧「目标会话尚不可用」的实机根因尚未确认，本次不能据代码审查声称已解决。
- 未操作真实微信、未清理或重试队列、未重启任何服务。仅需用户自行重启wxbot，本次不涉及Butler/Hermes/log运行代码。

## 持续阻塞与剪贴板提交版本修复（2026-10-18）

- 用户以101收件序号108再次报告被 `207599e6f2634406be19d44577d7142b:1` 阻塞。确认是15:18旧兜底道歉，未键入/回车；通过queue_admin skip --delivery结束这条旧任务，旧批次done。持久化blocked不会因重启或改代码自动重置；同会话存在未终结发件时，prepare不提交新模型批次。
- 新批次 `ed2be95ce47249f0b530c74ddc6623c9` 成功经Butler/Hermes得到109字、4句完整回复，证明Hermes重载后的canonical最终事件链路已用于真实请求。第1句在粘贴前被「对象、焦点或剪贴板变化」拦截；不继续跳过新回复。
- 先拆分诊断为目标/前台窗口、输入焦点、剪贴板三个类别，记录不含正文的剪贴板写入/关闭后/检查时序号。用户自行重启后，仅恢复保留的第1句一次，取得实机证据：写入时158，关闭后161，检查时161，未粘贴/回车。根因是把关闭前记录的版本当成写入完成版本，导致合法提交后的版本变化被误拦截；没有证据表明该次是微信目标或焦点问题。
- `WindowsClipboard.owned_sequence`用GetClipboardOwner在版本读取前后确认仍由本进程消息窗口持有；ClipboardLease在关闭写入后仅接纳仍属自己的完成版本，粘贴和恢复前同时核对版本与所有者。用户期间复制新内容导致所有者改变时不接纳、不粘贴、不用旧备份覆盖。异常恢复仅在确实尝试了自身恢复操作时更新提交版本，打开失败不盲目改版本。
- Win32所有权依据：[Microsoft剪贴板所有权说明](https://devblogs.microsoft.com/oldnewthing/20210526-00/?p=105252)。未通过直接原生工具操作微信/剪贴板；实机证据来自用户运行的wxbot及其持久化任务。未重启wxbot/Butler/Hermes/log；本轮wxbot两次重启均由用户完成，先加载诊断，再加载修正。
- 沿用已批准的分批粘贴离线验证，新增关闭后提交/用户复制竞态/写失败/部分恢复重试等回归，先观察3项失败再修正；全套 **264 passed in 21.28s**，4文件AST和diff空白检查通过，独立增量审查无Critical/Important。
- 用户再次确认自行重启修正版后，仅恢复 `ed2be95ce47249f0b530c74ddc6623c9:1`，不重跑模型。最终4句均sent、批次done；下一批 `e1c42a34c1d0409d9a553d4c9f73092e` 已waiting_delivery。收件108仍待前面积压批次依次完成，不能声称108已经发送。未删除收件/快照、未提交Git，也未更改全局blocked自动重试规则。

## 发送失败期限与页面人工核对（2026-10-18）

- 用户要求新增发送失败日志、失败最多阻塞3分钟后丢弃并留记录，并明确批准 log 页面 **重试 / 确认已发 / 立即丢弃** 按钮和离线验证。此前只有折叠的恢复命令；新入口为 log → 收发队列 → 选择用户 → 异常任务旁按钮，下方为最近50条失败/人工核对记录。
- 队列版本3新增 outbox.failed_at / resolution 和 delivery_events。首次失败时间持久保存，重试/重启不重置；旧 blocked/uncertain 按 finished_at→submitted_at→created_at 补记。仅 runtime 在运行锁内迁移；log查询与CLI查询仍只读兼容旧库，管理写入要求新版库。
- DeliveryPump 每秒巡检：只有发件 blocked/uncertain 从首次失败满180秒才标 skipped / timeout，保留原文、原原因和审计，只结束该句并重算整轮、释放后续。pending/sending/confirming 不被超时打断；未产生发件的模型异常不自动丢弃或重试。此规则取代上文发件永久等待人工核对的旧行为。
- [发送失败] ERROR 记录阶段、任务ID、可读取的预期/实际会话、类型、前台句柄、焦点、输入字数、是否尝试回车及剪贴板序号；不记录剪贴板/草稿正文或无关应用标题。[发送超时丢弃] WARNING 保留原因；详细审计与状态在同一短事务写入。
- 新 POST /api/queue-action 只操作服务器配置的现有库，不操作UI、不调用shell、不recover或迁移；要求JSON、自定义请求头、明确确认、可信Host/同源、联系人+状态+失败时间快照。模型批次另校验执行次数，防同状态再次失败后旧页面误操作。已有发件的批次不能重跑模型；批次无“确认已发”。
- 新回归覆盖180秒边界、重试重启期限、逐句保留、旧v2迁移、自动超时与人工动作并发、模型快照ABA、HTTP跨站/Host重绑定拒绝、失败元数据、前端转义/异步切页。全套 **291 passed in 21.54s**；10个Python文件AST、示例TOML和git diff空白检查通过。独立审查提出的模型快照与Host校验问题均已修复。
- 使用临时配置和临时SQLite启动独立log预览，浏览器确认三个按钮、倒计时、失败记录可见，随后关闭预览并删除临时助手；未访问真实微信或更改真实队列、未重启任何服务、未提交Git。用户需自行重启 **wxbot → log**；旧失败任务如已超过180秒会自动丢弃。Butler/Hermes无需重启。实际微信发送结果待用户观察，不据离线验证声称已修复焦点变化根因。

## log 配置编辑（2026-10-18）

- 用户明确批准全部实际配置可编辑、中文名称/用途/保存、生效提示、注释保留、备份和版本冲突检查、密钥仅显式替换/清空，以及临时配置离线验证。覆盖wxbot/Butler/联系人/角色Skill心跳/分组/log启动参数；运行事实、推导路径与机制说明只读。Hermes地址指Butler调用目标，不更改Hermes进程监听配置。
- 新增log/config_editor.py、config_schema.py、settings.py；GET /api/configuration输出类型/字段路径/生效方式/来源版本，POST按来源+版本+字段patch保存。可信Host/Origin、自定义header和明确确认保护；400为参数错误、409版本冲突、503文件/技能目录不可用。服务器登记写入路径，客户端不能指定任意文件。
- tomlkit保留TOML注释和未改项；合作文件锁、版本复核、原文件旁备份、临时文件fsync后原子replace。密钥/备份/锁文件已Git忽略；嵌套JSON隐藏会话模板按原name或唯一稳定身份保留，联系人合并歧义拒绝猜测，名称禁止首尾空格/重复，uid须ASCII。角色/工具变更继续验证Hermes目录和butler-role标签。
- 值脱敏与协议元数据分开，服务端未脱敏catalog用于字段授权；密钥恰好为timeout/butler/integer/ok不能改写字段路径、来源ID、版本或编辑器类型。含隐藏凭据的URL修改后若仍含星号占位则拒绝，要求完整新值，防止把真实token覆盖成***。
- 表单有来源级内存草稿、保存/取消/恢复默认，切分类/tab及自动刷新保留草稿；密钥新值不入HTML、确认文案或localStorage，明确保持/替换/清空。只显示当前分类来源保存区，额外保留其他来源草稿/消息，按钮仍绑定正确来源索引。
- 新配置wechat.typing.chunk_size默认5（1–100），chunk_interval默认0.5（0.05–10秒）；queue.failure_discard_seconds默认180（1–86400秒），QueueStore实例TTL保留首次failed_at，重启后已有失败任务也用新期限；log倒计时读取文件值并注明未核验运行参数。保留输入/目标/焦点校验、仅一次回车与不确定不自动重发。
- log自身配置为config.log.toml（LOG_CONFIG可覆盖），模板config.log.example.toml；命令行与既有环境变量优先。start.bat改用server.py --open，默认读取保存值，不再硬编码home/port。tomlkit依赖已加入requirements并通过uv安装到共享.venv（pip模块缺失）。未创建或更改用户当前真实配置。
- fresh验证 **374 passed in 23.21s**，11个Python AST、3个示例TOML与diff空白检查通过。独立审查发现的URL占位、元数据脱敏、联系人模板串号/歧义与strip冲突均有RED→GREEN回归并修复，最终无剩余P1/P2。临时log浏览器预览确认Hermes地址/Key/模型/超时及保存区可见；临时服务器自动结束，未发送微信、未写真实队列、未重启任何服务、未提交Git。
- 使用新页面需用户自行重启log；更改wxbot参数后自行重启wxbot，更改Butler文件参数（Hermes调用地址等）后自行重启Butler。动态角色/白名单/心跳开关和分组在后续读取生效；不要自动重启用户管理的服务。

## 持续 OSError 发送失败诊断（2026-10-19）

- 用户贴09:06–09:55的101发送记录：多个批次每句均“分批粘贴失败（OSError）”，phase=paste_guard、characters_entered=0、enter_attempted=false，满180秒逐句丢弃。只读查询真实队列事件确认相同事实；未更改任务状态或恢复已丢弃任务。
- 不能据此认定剪贴板具体占用者/格式/系统调用：paste_guard旧阶段同时包含输入前缀检查、ClipboardLease备份/写入、目标/焦点复核、Ctrl+V；typing异常处理只保留type(exc).__name__，原OSError消息被丢弃，stdout也未持久化单独异常日志。0字符计数表示尚无成功完成的输入批次，不足以证明Ctrl+V从未尝试。
- 本次只补诊断：clipboard固定错误附clipboard_operation/clipboard_error/clipboard_format/os_error_code；区分OpenClipboard、格式枚举/备份/大小/复制、内存写入、恢复等失败。恢复失败保留结构化原因供后续pending阻断透传。typing细分clipboard_acquire/paste_key阶段，错误追加固定原因；异常类型/安全数值进入队列审计白名单，不记录剪贴板正文或任意异常str。
- 未调整剪贴板保留、输入/焦点守卫、等待、自动重发或失败丢弃策略；没有证据可声称发送根因已修复。3文件AST与diff空白检查通过；本轮用户只要求排查，未添加或运行测试。未操作真实剪贴板/微信、未改实际配置、未重启服务、未提交Git。
- 需要用户自行重启wxbot以加载诊断并发一条新消息，取得更具体失败原因后再修实际根因；原已超时丢弃的句子不会自动重发。log原进程若未重载新白名单，错误原因文本仍可看到，新增现场字段需重启log才完整显示。
