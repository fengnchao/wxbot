# 完整回复分句与收发调度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for the recommended native execution, or superpowers:subagent-driven-development if the user chooses per-task agents. Steps use checkbox syntax for tracking.

**Goal:** Butler 完整整理回复后分句；wxbot 支持不同用户并发等待、界面串行收发和按用户轮流发送分句。

**Architecture:** Butler 负责最终正文和分句协议、有效会话及 Profile 资源锁。wxbot 以纯数据 Reply 连接后端与 SQLite，固定数量后台请求线程处理模型，UI 主线程每次完成一次采集或一句发送确认。SQLite 持久化分句、整轮状态和服务次序。

**Tech Stack:** Python 3.14、标准库 sqlite3/threading/dataclasses、既有 requests/uiautomation/Pillow/pytest；不新增第三方依赖。

**Spec:** `docs/superpowers/specs/2026-10-18-complete-reply-parts-design.md`（用户已确认）。

## Global Constraints

- Hermes 仍完整生成一轮回复。Butler 整理最终正文后分句，一次返回全部分句。
- wxbot 的界面操作串行：一次收件采集或一次完整句子的键入、回车及确认。等待模型不占用微信界面。
- 不同用户的请求可以并发等待，同一会话不并发开始两轮处理。默认最多 2 个模型请求，超过上限继续留在持久化就绪队列。
- 闲时只读检查，不主动激活/滚动；保留 Unicode 键盘输入、5 字/0.5 秒、输入校验和新增自己的气泡确认。
- 本阶段不接入 Hermes 流式输出，不自动重试结果不确定的模型或发送任务，不自动重启任何服务，不提交 Git。
- 保留私聊/群提及过滤、成员区分、3 秒安静合并/10 秒上限、角色和白名单，以及非 Butler 后端、独立窗口和主动推送的单条兼容语义。
- 继续在当前用户工作区实施，保留既有未提交改动和已删除的 tracked pyc；不得在用户真实队列上试验迁移或运行发送测试。
- 产品代码的实施须在本计划审阅后开始；交付后由用户停旧版、手动重启 Butler 和 wxbot，Hermes 无需为本功能重启。

## Review Focus

1. 旧运行锁、旧库只读查询、DDL 中途失败及全局自增高水位：不能在旧进程运行时迁移，失败不能留半张表（Task 3）。
2. 空/坏分句、完整响应标志及请求 ID 不匹配：不能发送半份回复或另一请求的正文（Tasks 1、4）。
3. 同 UID 窗口别名、角色策略、reset、delegate 与同 Profile 补发/本地文件：不能绕过身份锁、重复认领或跨用户（Task 2）。
4. 新用户迟到、某句话异常、人工确认/跳过/重试及重启：不能越过本用户旧句，不能提前完成整轮，也不能重发已确认句（Tasks 3、6）。
5. 回复在采集中到达、消息在回车前到达、空闲无任务：必须完成当前操作后切换，保留入库检查点并保持闲时被动（Task 6）。

## 文件与接口决策

| 文件 | 职责 |
|---|---|
| 新增 `butler/reply.py` | 最终正文的纯分句函数 |
| 新增 `butler/concurrency.py` | 会话/资源可重入锁注册表；注册表锁不覆盖网络或子进程 |
| `butler/core.py`、`hermes.py`、`pending.py`、`contacts.py`、`skills.py`、`server.py` | 完整响应、统一会话作用域、认领和本地资源保护 |
| 新增 `wxbot/reply.py` | 纯数据 `Reply(text, parts)`，无 HTTP/UIA 依赖 |
| 新增 `wxbot/queue_schema.py` | 新库初始化与旧库事务迁移 |
| `wxbot/queue_store.py`、`queue_admin.py` | 分句持久化、公平领取、整轮重算与管理访问模式 |
| `wxbot/processor/*` | 完整字符串兼容、结构化回复、请求关联和带会话类型的 reset |
| `wxbot/queue_worker.py`、`inbox.py`、`delivery.py`、`config.py` | 有界请求并发和 UI 收发交替 |

### 统一命名

- `request_id` 是 wxbot 内部的批次 ID；HTTP 请求字段继续使用现有 `msg_id`，响应回显 `meta.msg_id`。
- outbox 既有 `seq` 保持全局自增；新增 `part_seq` 为从 1 开始的句内序号，唯一键为 `(batch_id, part_seq)`。
- outbox `id` 就是稳定分句 ID：旧行 ID 原样保留，新模型分句为 `f"{batch_id}:{part_seq}"`；无 batch 的主动推送继续使用独立 UUID。
- 新批次增加 `reply_text`、`reply_complete`、`part_count`；旧批次根据既有发件映射为一条，旧静默批次为零条。
- 新增 `delivery_turns(contact PRIMARY KEY, last_turn)`；发送确认或人工终结一句时在事务内更新递增服务次序，重复终结同一句不再次更新。
- `[queue].max_model_requests = 2`；验证为正整数，拒绝 bool。无额外分句配置开关。

---

## Task 1：Butler 最终分句与完整响应协议

**Files:** 新增 `butler/reply.py`、`tests/test_reply_parts.py`；修改 `butler/core.py`、`tests/test_pipeline.py`、`tests/test_transport.py`、`butler/README.md`。

**Interfaces:**

- `split_reply(text: str | None) -> list[str]`。
- `Result.as_dict() -> dict` 保留原字段，新增 `reply_parts`，`meta.reply_complete` 为 True；不破坏既有 `Result(reply, actions, meta)` 位置参数。
- `Butler.handle(..., msg_id=None, channel_type="dm") -> Result` 的全部返回路径统一收尾，提供 msg_id 时均回显。

- [x] 写失败用例 `test_split_preserves_terminal_runs_and_closers`：`真的吗？！”下一句。尾巴` 得到三句，句尾连续标点及右引号不独立成句。
- [x] 写参数化失败用例：空白/None 为 `[]`；无标点尾巴保留；逗号/ASCII 点不拆；URL 查询中的 `?!`、行内代码和代码围栏内的标点/换行不拆；保护区外的换行分段。

```python
assert split_reply("真的吗？！”下一句。尾巴") == ["真的吗？！”", "下一句。", "尾巴"]
assert split_reply("链接 https://example.test/a?x=1! 结束。尾巴") == ["链接 https://example.test/a?x=1! 结束。", "尾巴"]
assert split_reply("试试 `a?!b`。好。") == ["试试 `a?!b`。", "好。"]
assert split_reply("版本3.14，见example.test。尾巴") == ["版本3.14，见example.test。", "尾巴"]
```

- [x] 写 `test_complete_reply_contract_on_all_handle_paths`：普通、空消息、静默、`/new`、Hermes 错误均保留 reply，数组完整，complete=True，并回显请求 ID。
- [x] 写 `test_reply_parts_are_computed_after_actions_and_pending`：行动标记不泄漏，已拼接的补发及行动文本参与分句；直接 reset 也返回完整协议。
- [x] 跑红：`.\.venv\Scripts\python -m pytest tests/test_reply_parts.py tests/test_pipeline.py tests/test_transport.py`，确认失败来自缺失分句/协议。
- [x] 实现保护区识别后扫描句尾；仅对最终 compose 结果分句，统一所有提前返回的收尾，不增加模型调用。
- [x] 跑绿同一命令；更新 Butler 文档中的增量响应格式及旧 reply 兼容规则。

## Task 2：Butler 会话并发与补发归属保护

**Files:** 新增 `butler/concurrency.py`、`tests/test_butler_concurrency.py`；修改 `butler/core.py`、`hermes.py`、`pending.py`、`contacts.py`、`skills.py`、`server.py`、`tests/conftest.py`、`tests/test_transport.py`。

**Interfaces:**

- `RuntimeLocks(endpoint: str)` 的 `session(contact, *, session_kind="chat")` 与 `profile(profile)` 返回可重入上下文管理器。
- `HermesClient.session_guard(contact, *, skill_policy=None, session_kind="chat")`；Core 与实际 HermesClient 使用同一组会话锁。
- `HermesClient(cfg, log=None, *, locks=None)`、`PendingQueue(hermes_root, log=None, *, locks=None)` 注入 Butler 构造的同一个 RuntimeLocks；直接单独构造时创建自己的注册表，旧位置调用兼容。
- `ContactMap.is_sole_profile_owner(contact: Contact) -> bool`。
- `PendingQueue.take_and_claim(contact: Contact, *, allow_unowned=False) -> list[dict]`。
- `Ctx` 末尾追加 `skill_policy: dict | None = None`、`runtime_locks: RuntimeLocks | None = None`；delegate 原样透传 policy，本地执行使用该资源锁；`Butler.reset(contact_name, *, channel_type="dm") -> Result`。

- [x] 写 Event/Barrier 用例：A 假模型阻塞时 B 已进入；同有效身份的窗口别名、reset 在 A 的模型/行动结束前不能进入；使用超时上界防测试挂死，不用 sleep 猜顺序。
- [x] 写别名 reset 测试：映射同一实际 Profile/key 的两个名称共享 canonical session-id 状态；HTTP 会话头的初始稳定值保留，测试通过 `session_id()` 而非旧内部字典键断言。
- [x] 写角色/群聊测试：delegate 使用相同 policy 和作用域；群 reset 与 group handle 同步，heartbeat 保留独立 kind/read_only 语义。
- [x] 升级假补发脚本，让 flush 真正标记/移除条目；写原子认领、共享 Profile 不同用户、同 uid 别名、唯一显式归属、未知 fallback 和字段冲突测试。
- [x] 写失败/超时用例：只返回已确认认领成功项；后项失败不丢已成功前项；缺 key、无法理解归属的项不 flush。
- [x] 写本地资源并发测试：同 Profile 的 reminder.create/list/cancel 串行；该资源锁不挡住其他用户进入模型，kind=hermes 的 delegate 不持 Profile 文件锁。
- [x] 跑红：`.\.venv\Scripts\python -m pytest tests/test_butler_concurrency.py tests/test_pipeline.py tests/test_transport.py`。
- [x] 实现会话锁：基于实际 endpoint/Profile 和稳定身份 key，不能用窗口名称或会随 reset 变化的当前 SID。锁覆盖整轮 handle/行动与 reset；存储的 canonical session scope 另包含 policy 指纹和 kind，保留已有 wire SID 派生规则。
- [x] 实现认领：Profile 锁仅覆盖读取/归属核对/flush；明确支持字符串 contact、uid、user_id，所有提供的身份必须一致，无法理解或冲突的收件信息留存；无归属项仅 allow_unowned=True 可认领，未知 fallback 不视为唯一显式用户。
- [x] 本地 action 的 Profile 资源锁覆盖完整读改写/子进程；主模型、delegate 不持该资源锁。此锁不宣称解决 Hermes/cron 外部进程写文件问题。
- [x] 跑绿同一命令，确认锁注册表只持短锁，心跳调度锁未扩大为全局模型锁。

## Task 3：SQLite 多句迁移、整轮状态和公平领取

**Files:** 新增 `wxbot/queue_schema.py`、`tests/test_queue_migration.py`；修改 `wxbot/queue_store.py`、`queue_admin.py`、`tests/test_queue_store.py`、`test_queue_admin.py`、`test_delivery_queue.py`。

**Interfaces:**

- `QueueStore(path, *, access="runtime")`，access 仅 runtime/readonly/admin。
- `finish_batch_parts(batch_id, parts: tuple[str, ...], *, now, delay=0, reply_text=None)` 原子落全部句；既有 `finish_batch(str|None)` 包装为单句兼容。
- `has_ready_delivery(*, now) -> bool`、`claim_delivery(*, now) -> Delivery | None` 共用同一候选规则。
- `Delivery` 追加默认值 `part_seq=1`、`part_count=1`；原位置参数保留。
- `_recompute_batch(db, batch_id, *, now)` 被 finish/retry/resolve/recover 共同使用。

- [x] 用人工旧 schema fixture 写迁移测试，参数化 pending/sending/confirming/sent/blocked/uncertain/skipped，逐字段验证旧 ID、全局 seq、正文、baseline、submitted_text、error 和全部时间原样保留，part_seq=1。
- [x] 写锁/只读/回滚测试：旧 `.lock` 被占用时，runtime 构造在任何连接或 DDL 前失败；readonly 的 status/list 成功且 schema/version 不变；admin 拒绝旧 schema；中途 DDL 失败全部回滚；自增高水位高于 MAX(seq) 时仍保留。
- [x] 写多句事务测试：A 三句全部一次落库；中间句插入失败无半份发件；重复完成同一模型批次被拒绝；零句完成静默批次。
- [x] 写公平测试，核心断言为 `A1, B1, 重启, A2, B2, A3`；B 迟到在当前 A 句后获得服务，未就绪的 B 不使 A 空等。
- [x] 写整轮/恢复测试：首句发送不能 done；一异常仅挡本用户；sent/skip/retry 某一句后重新计算所有句，剩 pending/异常不能释放下一轮；已确认句不重发，逐句使用各自 baseline/submitted_text 恢复。

```python
assert delivery_text_order == ["A1", "B1", "A2", "B2", "A3"]  # 中途关闭/重开数据库
assert store.get_batch(a_id)["state"] == "waiting_delivery"  # 仅 A1 已确认时
assert migrated_row["id"] == legacy_row["id"]
assert migrated_row["baseline"] == legacy_row["baseline"]
assert migrated_row["submitted_text"] == legacy_row["submitted_text"]
```

- [x] 跑红：`.\.venv\Scripts\python -m pytest tests/test_queue_migration.py tests/test_queue_store.py tests/test_queue_admin.py tests/test_delivery_queue.py`。
- [x] 实现访问模式：runtime 构造先持有既有 `.lock`，再连接/迁移；acquire_runtime 保持幂等。readonly 使用 mode=ro、不设置 WAL、不 DDL/recover；admin 使用 mode=rw且只接受当前 schema。连接/迁移失败必须释放连接及运行锁。
- [x] 实现迁移：一个 BEGIN IMMEDIATE 事务逐条 execute，不能用会隐式提交的 executescript；重建 outbox 去掉 batch_id UNIQUE，显式复制旧全部列及全局 seq，缺 submitted_text 才填 NULL，保留 sqlite_sequence 高水位；事务末尾写 schema 版本。
- [x] 实现多句及轮转：各会话仅最早未完成句可领取，按 `COALESCE(last_turn,0), outbox.seq` 选择；终结一句时事务内递增 last_turn。整批全 sent/skipped 才 done，否则 uncertain 优先于 blocked，其余 waiting_delivery；未得到完整模型结果的 processing/uncertain 不伪装完成。
- [x] CLI status/list 走 readonly，旧库读取映射单句默认值；retry/sent/skip 走 admin，显示分句 ID、序号/总数、整轮进度，不触发旧库迁移。更新恢复文档，跑绿同一命令。

## Task 4：wxbot 回复数据与 Butler 适配

**Files:** 新增 `wxbot/reply.py`、`tests/test_reply_adapter.py`；修改 `wxbot/processor/base.py`、`router.py`、`butler.py`、`openai_compat.py`、`ollama.py`、`tests/test_processor_queue_errors.py`。

**Interfaces:**

- 纯数据 `Reply(text: str | None, parts: tuple[str, ...])` 与 `Reply.from_text(text) -> Reply`。
- `Processor.handle_reply(contact, text, *, request_id=None) -> Reply` 默认仅调用原 handle 一次；`Router.handle_reply(contact, text, *, context="", request_id=None) -> Reply`。
- `ButlerProcessor.handle_reply` 发送 msg_id；原 handle 继续返回完整 str/None。
- 各 Processor 的 `reset(contact, *, channel_type="dm")` 保留旧位置调用；主窗口 Router 从群 context 传递 group，HTTP reset 支持并校验可选 channel_type。

- [x] 写新协议用例：完整 reply 和三句保留，msg_id 请求/回显关联；缺少新字段的老 Butler 只返回一条；非法数组整份退回完整 reply，不能发半份。
- [x] 写安全用例：显式回显另一 msg_id 或明确 reply_complete=False 必须抛协议异常；合法静默为零句，非空 reply 搭配空/坏数组不得吞回复。
- [x] 写兼容用例：Echo/OpenAI/Ollama 和本地命令只执行一次并返回单句；independent handle 返回原完整字符串；群 reset 进入 group 会话，角色 context 不进入命令正文。
- [x] 跑红：`.\.venv\Scripts\python -m pytest tests/test_reply_adapter.py tests/test_processor_queue_errors.py tests/test_transport.py`。
- [x] 实现统一数据边界及 Router 复用命令/context 逻辑，不在 wxbot 二次分句。Butler 单次 HTTP 解析共用，协议异常交由队列保留 uncertain；保留旧独立模式的错误文案兼容行为。
- [x] 对 request_id 缺省的旧调用保留兼容；字段缺少/格式损坏回退完整 reply 时留简洁协议日志，不打印身份头或密钥。
- [x] 跑绿同一命令。

## Task 5：有界后台请求与等待标记

**Files:** 修改 `wxbot/queue_worker.py`、`inbox.py`、`config.py`、`config.wxbot.example.toml`、`tests/test_queue_worker.py`；新增 `tests/test_queue_concurrency.py`。

**Interfaces:**

- `ModelWorker(..., max_concurrency=2)`：固定数量 daemon 请求线程，共享 stop Event；`process_once()` 继续可用于离线单步测试。
- worker 调用 `Router.handle_reply(..., request_id=batch.id)`，再调用 Task 3 的 finish_batch_parts；每个模型批次只能领取一次。
- `stop(timeout=1) -> bool` 使用同一 monotonic 截止时间 join 全部线程；未全部停止时仍保留 store/运行锁直到进程退出。

- [x] 写 Event 用例：A 阻塞时 B 已进入假 Router；上限=2 时 C 留在 ready；同 A 的第二批在旧批全部分句完成前不进入。
- [x] 写异常/停止用例：A 超时 uncertain 不重跑，B 正常；stop 在统一时间预算内返回且不新认领 C，不使用会在退出时等待网络的 ThreadPoolExecutor。
- [x] 写配置用例：省略默认2，1有效，0/负数/非整数/bool拒绝；直接注入 cfg 的 MainInbox 也验证。

```python
assert a_entered.wait(2) and b_entered.wait(2)
assert not c_entered.is_set()  # A/B 的释放 Event 均未打开
assert calls_for_second_a == []  # A 的旧分句尚未全部完成
```

- [x] 跑红：`.\.venv\Scripts\python -m pytest tests/test_queue_concurrency.py tests/test_queue_worker.py tests/test_processor_queue_errors.py`。
- [x] 实现固定 daemon 线程和事务领取，不将 UIA/截图对象放进 worker。状态日志明确区分 ready=待提交、processing=等待模型、waiting_delivery=完整回复就绪，携带 batch ID。
- [x] 网络调用不持 SQLite 锁；停止后不主动开始新批次，已返回结果可安全持久化。更新示例配置及等待状态说明，跑绿同一命令。

## Task 6：一次界面任务与逐句交替发送

**Files:** 修改 `wxbot/inbox.py`、`delivery.py`、`tests/test_main_window.py`、`test_delivery_queue.py`、`README.wxbot.md`、`README.md`、`PROJECT_MEMORY.md`；新增 `tests/test_multipart_flow.py`。

**Interfaces:**

- `MainInbox.poll(*, allow_switch=False)` 仅被动发现/登记及读取当前面板；`_receive_one() -> bool` 完整尝试一次待采集会话并返回。
- `DeliveryPump.start_next() -> bool` 闲置时只开始一句，准备阶段已 blocked 也算一次调度尝试；`tick(*, allow_start=True)` 保留既有直接调用兼容。
- MainInbox 内存 `_next_ui` 从 receive 开始；收发都积压时交替选择，只有完成一次采集或一句键入/确认才推进轮次。

- [x] 写交替用例：积压时事件严格为收/发/收/发；一次采集后其它待收件仍保留，不能一次 for-loop 扫完所有待收对象才回发。
- [x] 写时序用例：A 回复在 B 采集期间到达，事件为 B采集开始/B事务完成/A发件开始；typing 和 confirming 全期间不切会话，但可登记角标及读取当前窗口。
- [x] 写完整链路用例：假 Butler 返回 A 三句/B 两句，发送交错且内部顺序不变；A 首句确认后仍标等待，最后一句才结束；第二轮用户消息继续落库并等待。

```python
assert ui_events == ["receive", "send", "receive", "send"]
assert race_events == ["B_capture_start", "B_capture_commit", "A_send_start"]
assert pending_texts == ["回车前刚到的新问题"]  # before_enter 读取后已入库，无需下一次 poll
```

- [x] 保留并适配现有回归：空闲无激活/移动/滚动，群非 @不进入模型，同名/类型变化阻断，Unicode/代理对/0.5秒/草稿校验，回车前新消息先入库，旧不确定正文恢复不重发。
- [x] 跑红：`.\.venv\Scripts\python -m pytest tests/test_main_window.py tests/test_delivery_queue.py tests/test_multipart_flow.py tests/test_typing.py`。
- [x] 实现调度：active 发件只调用 tick(allow_start=False) 直到整句终结；空闲按照 `_next_ui` 和待收/可发状态选择一次任务。准备发件的目标采集、切换前捕获和 before_enter 捕获仍属于当前发件的安全准备，不递归领取其它任务。
- [x] 失败采集保留任务，下一次尝试遵守轮询间隔，避免每0.05秒反复抢同一个不可用窗口；准备失败也让另一类积压获得机会。
- [x] 发送日志含分句 ID 和 n/total；HTTP 主动推送仍单条，waiter 只在自身发送确认后完成。更新文档与项目记忆，明确停止旧版后迁移、手动重启两个进程及 Hermes 网关无需改动。
- [x] 跑绿目标命令，再运行完整 `.\.venv\Scripts\python -m pytest`、`git diff --check`、修改文件语法解析和示例 TOML 读取；准确记录数量及边界，不将离线结果当真实微信验证。

## 执行与审查交接

- 推荐 **当前会话直接实施（Native）**：六项按顺序执行、逐项红绿，最后由一个独立代理做全量只读审查。已完成的两项并行检查仅用于本计划，不替代最终审查。
- 若用户选择分任务代理，再使用 subagent-driven-development 的逐任务实现/审查；不得让不同代理同时修改共享队列/适配器接口。
- 用户审阅本计划并确定方式后开始产品代码。实施时在独立进度台账记录每任务、验证结果和必要 ruling；不自动提交 Git。
- 完成后交付改动摘要、离线验证结果、已知 UIA 范围限制，以及由用户自行重启 Butler/wxbot 的步骤；本轮全过程不发送真实微信测试消息。

## 计划自检记录

- 设计的协议、分句、身份隔离、数据迁移、并发等待、界面顺序、公平发件及恢复均已映射到上述任务与测试。
- 物理 `part_seq` 与全局 `seq`、request_id 与 HTTP msg_id 的映射已统一；任务消费的 Reply、存储、worker 和 UI 接口签名一致。
- 两项独立只读检查覆盖 Butler 和 wxbot 的既有代码；发现的提前返回缺关联 ID、补发非原子、delegate 漏 policy、迁移先于运行锁、整批过早 done 及退出等待风险均已纳入任务。
- 实施记录：六项已完成，最终完整离线测试 **200 passed in 18.29s**；44 个修改/新增 Python 与示例 TOML 文件解析通过，`git diff --check` 通过。最终独立审查通过，未发现剩余 Critical/Important。未操作真实队列迁移、真实微信发送或服务重启；未提交 Git。

## 执行与最终审查记录

- 六项均先取得缺失接口或行为失败证据，再完成实现及目标回归。保留当前工作区和原有修改，无自动提交/合并；Windows 使用本地台账替代 Bash 辅助脚本。
- 最终审查修复：停止信号不再等待队列锁，所有 join 共用入口截止时间；停止与领取竞态中尚未调用后端的批次安全退回 ready。
- 最终审查修复：补发逐项校验字典和非空字符串正文；坏项不 flush，也不隐藏有效项。未支持的收件字段（含 CamelCase、复合和嵌套形式）保留未认领，不能按无归属旧记录投递。
- 最终审查修复：内联代码使用匹配长度的反引号；围栏关闭长度不得短于开启长度；独立句尾标点合入相邻正文。另修复 URL 后中文句号分句和恢复时完成时间丢失。
- Ruling：整轮原本仅含“！？”等标点时保留为一条完整回复；不由分句制造独立标点消息，不额外删改模型原始表达。
- Ruling：Hermes `allowed_skills` 与 Butler 固定本地行动 `CATALOG` 沿用原有两层边界，本轮修复 delegate 策略透传，不猜测不同命名空间的技能映射。
- 审查者复读修复并使用纯内存桩验证 8 个场景通过。交付保留现有工作区，用户先停止旧 wxbot，再自行重启 Butler/wxbot；Hermes 无需为本功能重启。
