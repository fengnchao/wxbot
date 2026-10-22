# Telegram News Relay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将用户账号已加入的 `@zaobaosg` 新文字原文转发给当前新闻分组的微信接收人。

**Architecture:** 独立的 Butler Telegram 服务通过 Telethon 采集文字，将扫描游标和收件记录事务落库。单独的转发循环生成逐人逐段任务，经既有 `/v1/push` 提交并保存确认状态。Telegram 会话、收件状态与 RSS 日报隔离。

**Tech Stack:** Python 3.14、SQLite、requests、Telethon 1.45 系列可选依赖、pytest。

**Spec:** `docs/superpowers/specs/2026-10-22-telegram-news-relay-design.md`

## Global Constraints

- 使用安装者自己的 Telegram 账号；来源为 `@zaobaosg`，运行时绑定稳定数字 ID。
- 新闻接收人读取 Butler 配置解析的 `group_file_path()` 的 `groups["1"]`。
- 首次从最新消息开始，不补发此前历史；后续断线补收，事务记录扫描游标。
- 只接收文本和媒体附带文字，不下载媒体、不 OCR、不调用模型、不向 Telegram 回复。
- 发送只使用现有 Butler `/v1/push`，wxbot 独占微信 UI 和发送队列。
- 已确认和不确定记录不自动重发；先记 sending，未知结果保留 uncertain。
- 不重启现有服务；离线验证使用临时数据和假客户端，不发真实微信测试消息。
- 保留现有未提交改动，只提交本任务文件或本任务补丁，不纳入其他业务修改。

## Review Focus

- 初始化与事件交错：初始化边界之后到达的消息不能因通知乱序而遗漏（Task 4）。
- 数据库提交失败：游标不能越过未成功落库的一页（Task 2）。
- 配置热变更：取消订阅者不能继续领取未提交分段（Task 5）。
- HTTP 成功但协议损坏：不能误报 sent，也不能重复提交未知结果（Task 3、5）。
- 源账号/用户名更换：不能静默消费新账号或同名不同 ID 的来源（Task 2、4）。

## 文件和接口划分

- `butler/telegram/config.py`：配置验证、路径、可选代理；不创建会话、不输出密钥。
- `butler/telegram/store.py`：数据库、账号/来源绑定、扫描事务、逐人逐段状态与只读汇总。
- `butler/telegram/formatting.py`：带时区的消息数据及保留完整 URL 的文本分段。
- `butler/telegram/client.py`：延迟导入 Telethon、交互登录、来源解析、通知和按 ID 递增扫描。
- `butler/telegram/service.py`：采集/展开/投递循环、状态、单实例生命周期。
- `butler/telegram/__main__.py`：login/run/status 参数、退出码和无密钥错误报告。
- `butler/push_client.py`：通用的逐人新闻推送 HTTP 契约；RSS 原模块保持不变，以协议兼容测试校验。
- `tests/test_telegram_*.py`：对应边界的离线验证。
- `config.telegram.example.toml`、`docs/TELEGRAM_NEWS.md`：空凭据模板和使用说明。
- `.gitignore`、`pyproject.toml`、`uv.lock`、`README.md`、`tools/release.py`：可选安装及安全分发。

### Task 1: 严格配置与文本格式

**Files:** Create `butler/telegram/__init__.py`, `config.py`, `formatting.py`, `config.telegram.example.toml`, `tests/test_telegram_config.py`, `tests/test_telegram_formatting.py`; Modify `.gitignore`。

**Interfaces:** `load(path, *, butler_config=None) -> TelegramConfig`；`TelegramConfig` 包含 enabled、sources、session_path、state_path、api_id、api_hash、proxy、scan_interval；密钥字段不进入 repr。`Message(source_id, message_id, text, published_at, source_name, source_username)`；`parts(message, *, limit=500) -> list[str]`。

- [x] 写配置失败用例：相对路径按配置目录解析；布尔/整数严格校验；缺失文件、空源、非法来源拒绝；模板默认 disabled；repr 不含测试密钥。
- [x] 写格式失败用例：原文顺序、北京时间、来源链接、空白消息、长 URL 不截断、500 字目标及跨段固定标识。
- [x] 运行 `.venv/Scripts/python.exe -m pytest tests/test_telegram_config.py tests/test_telegram_formatting.py`，确认因接口不存在失败。
- [x] 实现接口及空凭据模板，增加本机配置与 session 辅助文件忽略规则；无副作用配置加载。
- [x] 重跑上述命令，全部通过后记录 Task 1 完成。

### Task 2: 持久化收件与可靠投递状态

**Files:** Create `butler/telegram/store.py`, `tests/test_telegram_store.py`。

**Interfaces:** `Store(path, *, readonly=False)`；`bind(account_id, source_id, username, baseline)` 校验既有绑定；`cursor(source_id) -> int`；`ingest(source_id, messages, cursor)` 同事务写收件和游标；`unexpanded()`；`expand(message, contacts, parts)`；`claim(allowed_contacts, excluded=()) -> Delivery | None`；`finish(id, state, reason)`；`recover()`；`status() -> dict`。

- [x] 写失败用例：同 ID 重复无新增，不同 ID 相同原文保留；账号/来源改绑拒绝；重启保留起始游标。
- [x] 注入 SQLite trigger 拒绝其中一条收件，断言整页与游标回滚。
- [x] 写任务用例：expand 原子幂等；空分组永久标记跳过；按收件人顺序；取消订阅未提交任务；sent 不重领；sending 恢复为 uncertain；uncertain/not_submitted 阻塞该收件人而不阻塞其他人。
- [x] 运行 `.venv/Scripts/python.exe -m pytest tests/test_telegram_store.py`，确认失败。
- [x] 实现独立 SQLite schema、短事务、线程锁、只读 status 和明确状态转换；readonly 不建库不迁移。
- [x] 重跑用例全部通过，记录 Task 2 完成。

### Task 3: 复用 HTTP 投递契约

**Files:** Create `butler/push_client.py`, `tests/test_telegram_push.py`。执行裁定：已有 RSS 模块属于另一个未提交改动，保持不变，避免将其整体纳入本任务。

**Interfaces:** `push_news(cfg, contact, text) -> dict[state, reason]`；支持注入/monkeypatch requests Session；RSS 既有 `push()` 返回契约保持一致，由兼容测试验证。

- [x] 写失败用例：`meta.ok is True` 且 contact 匹配才 sent；空 token 和 400/401/403/404 为 not_submitted；超时、重定向、未知 HTTP 状态、坏 JSON、列表/空 meta 为 uncertain。
- [x] 断言固定 type=1/messageType=1；禁用系统代理和重定向；认证只在 Header，错误不回显密钥/响应正文。
- [x] 运行 `.venv/Scripts/python.exe -m pytest tests/test_telegram_push.py` 确认失败。
- [x] 实现共用协议客户端，保留 RSS 原模块；以测试核对网络超时和返回契约。代价是暂时保留两个兼容的 HTTP 辅助函数。
- [x] 重跑客户端及现有新闻/推送相关测试，确认无真实请求后记录完成。

### Task 4: Telegram 授权与按游标扫描

**Files:** Create `butler/telegram/client.py`, `tests/test_telegram_client.py`；Modify `pyproject.toml`、`uv.lock`。

**Interfaces:** `TelegramSource(config)`；异步 `connect()`、`account_id()`、`resolve(username)`、`latest(source)`、`after(source, cursor)`、`close()`；`login(config)` 仅交互授权。适配器接收注入的假 Telethon 客户端工厂，便于离线验证。

- [x] 写失败用例：未授权 run 拒绝且不交互；login 交互不发送消息；源必须已加入；文本和 caption 归一化；空媒体/服务事件无文本；完整文本链接实体保留。
- [x] 写事件/扫描用例：NewMessage 只唤醒扫描，扫描按最小 ID 递增；通知重复/乱序不改变 Store 游标；断线恢复查询旧游标；source ID/account ID 改变失败。
- [x] 运行 `.venv/Scripts/python.exe -m pytest tests/test_telegram_client.py` 确认失败。
- [x] 实现 Telethon 延迟导入，NewMessage 唤醒、连接超时、有界重连、FloodWait 等待及显式取消；不提供发送或入群方法。
- [x] 添加并验证可选依赖 `telegram = ["Telethon==1.45.0", "python-socks[asyncio]>=2.7,<3"]`；在 Python 3.14 环境验证解析/导入，若实际不兼容则记录证据后选兼容版本。
- [x] 重跑离线用例，记录 Task 4 完成。

### Task 5: 单实例接收/转发服务

**Files:** Create `butler/telegram/service.py`, `tests/test_telegram_service.py`。

**Interfaces:** `Relay(cfg, butler_cfg, store, source, *, push=push_news)`；异步 `scan_once()`；同步 `deliver_once() -> bool`；异步 `run(stop)`；`instance_lock(path)` 互斥覆盖 login/run，会话同一目录不能重复使用。

- [x] 用假来源和假 push 构建失败用例：首次只设最新基线；初始化期间新增消息后续可收；重启后从 cursor 补收；事件去重；空频道正常。
- [x] 断言每次展开读取最新分组；格式坏暂停不丢收件；空组记跳过；发送前移除联系人取消；新增联系人不收到已展开旧消息。
- [x] 断言 A uncertain 阻止 A 后续任务但 B 可继续；发送阻塞时扫描可落库；终止后不领取新任务；单实例锁冲突不接触客户端；配置/存储错误不误报成功。
- [x] 运行 `.venv/Scripts/python.exe -m pytest tests/test_telegram_service.py` 确认失败。
- [x] 实现采集与投递独立循环，所有状态转换先持久化；发送前检查订阅和 stop，退出有界并保留未知提交状态；每轮只读配置，不重启服务。
- [x] 重跑服务及前面组件测试，全部通过后记录完成。

### Task 6: CLI、分发与整体验收

**Files:** Create `butler/telegram/__main__.py`, `tests/test_telegram_cli.py`, `docs/TELEGRAM_NEWS.md`；Modify `README.md`、`tools/release.py`、`tests/test_release.py`。

**Interfaces:** `main(argv=None) -> int`；login/run/status 都支持 `--config` 和 `--butler-config`；status 不连接 Telegram、不建会话、不调用 push；日志仅列经过筛选的状态/错误类型。

- [x] 写失败用例：help 在未安装 Telethon 时可用；status 空状态/现有状态只读；disabled 阻止 run；参数路径相对于指定文件解析；配置和意外异常不泄露凭据；login 不触发投递。
- [x] 运行 `.venv/Scripts/python.exe -m pytest tests/test_telegram_cli.py` 确认失败。
- [x] 实现 CLI 信号和退出码、JSON 状态、配置模板复制指引、本机授权及启动命令；不自动创建实际配置或启动服务。
- [x] 更新 release 源码白名单包含模板和说明，排除 Telegram session 及辅助文件；为打包结果增加测试断言。
- [x] 运行全部 `tests/test_telegram_*.py`、相关 RSS/分发测试，再运行完整 pytest；只在新失败/修改时扩大或重复验证。
- [x] 执行 `.venv/Scripts/python.exe tools/release.py` 验证源码分发审计，产物保留在忽略的 dist，核对无本机配置/会话。
- [x] 检查任务差异和已知限制，完成独立代码审查，将本任务改动保留在当前工作区；存在大量交叠的既有未提交代码，不自动合并提交；真实登录和持续运行需用户在本机配置，交付如实说明未真实联通部分。

## 执行与交付

用户已要求开发；建议由当前会话直接实施，各任务先失败验证再实现并核验，通过后更新勾选。当前工作区有大量相关未提交功能，执行前检查隔离技能的适用方式，禁止通过切换到旧 HEAD 遗失现有依赖；禁止提交其他任务文件。

真实 Telegram API 参数和登录验证码尚未提供。完成代码和离线验证不依赖这些信息；联通步骤由安装者本机完成授权后再进行。没有有效登录时不能报告渠道已上线。

## 验收记录

- 六个实现任务已完成，所有验证使用临时数据与假客户端。
- 审查修复：缺失新闻分组暂停而非跳过；停用来源积压不阻塞启用来源；未知回执仍阻塞该联系人；持续连接期间刷新来源身份和成员权限；完成接收人数仅统计全部分段获确认的联系人。
- 仓库既有微信窗口测试失败在开发前已复现，未修改该功能；最终测试证据保存在本任务执行记录。
- 未进行真实 Telegram 登录或微信投递，安装者须按 docs/TELEGRAM_NEWS.md 在本机配置并授权。
