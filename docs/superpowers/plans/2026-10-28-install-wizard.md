# 安装引导与共享目录实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** 删除模板与根目录编辑锁，提供可选智能体安装引导，把联系人和通道设置迁入共享数据库。
**Architecture:** 初始化用代码默认值；连接预设与协议适配分离。Butler 服务层管理共享目录，wxbot 和 log 读取投影。配置目录是所有相对运行路径的基准。
**Tech Stack:** Python 3.11、SQLite、tomlkit、pytest、PowerShell。
**Spec:** docs/superpowers/specs/2026-10-28-install-wizard-design.md

## Global Constraints

- 用户已批准实施；Grok Bot 不接入、不出现在可用选项中。
- 保留现有地址、Token、登录、稳定身份及权限；数据库迁移必须幂等，失败时原配置可恢复使用。
- 不把监听和身份授权合并，不用头像别名确认身份；未归属群的旧别名保留待核对。
- 测试使用临时数据及假投递；不发送真实微信消息。用户已允许启动、重启及测试服务。
- 不提交本机配置和数据库；保留 uv.lock；不提交 Git，保留之前清理的修改。
- 在当前用户指定工作目录实施，避免复制本机安装数据到另一个 checkout。

## Review Focus

- 新安装中断或取消：运行配置不得部分写入。
- 同名联系人、旧 uid 和现有绑定：迁移不重建或扩权。
- 从另一工作目录启动：配置、数据库和消息队列定位不变。
- 两个管理台并发保存：数据库与文件版本冲突可检测。
- CLI 或 HTTP 返回不完整结果：不投递部分回复，不执行未经授权的本机命令。

### Task 1: 共享数据库目录与迁移

**Files:** 新增 butler/directory.py、butler/migration.py、tests/test_directory_migration.py；修改 butler/config.py、wxbot/config.py、wxbot/queue_store.py、wxbot/wechat/chat_window.py 及必要收件读取点。
**Interfaces:** `directory_path(config_path, raw=None) -> Path`; `DirectoryStore(path)` 提供联系人行、通道设置、按群昵称、版本化管理与兼容投影；`migrate_installation(root) -> dict` 显式升级命令。不得依赖模型登录。
- [x] 写迁移 RED 测试：temp 配置和已有 business.sqlite3，保持监听开关、uid/session_key，二次运行不覆盖新修改，无群范围别名待核对。
- [x] 实现事务导入及迁移账本，原子删除仅成功迁移字段，统一运行时读取和昵称学习。
- [x] 验证目录测试、用户注册及原有收件测试；报告确切接口供管理台使用。

### Task 2: 协议适配器

**Files:** wxbot/processor/*、wxbot/main.py、butler/backends/*（仅确有需要）、tests/test_agent_connections.py。
**Interfaces:** `build_processor(cfg)` 由 model.backend 选择；支持原有 Butler/Hermes、OpenAI chat completions、Responses、OpenClaw 及 Cursor。安装器写入 model 字段 backend/url/api_key/model/timeout，Cursor 用 executable/work_dir，OpenClaw 用 agent。
- [x] 写 RED 契约测试：不同联系人会话隔离，HTTP 结束原因与 Responses 状态，CLI 超时/错误/审批/不完整输出拒绝，key 不在 argv。
- [x] 实现驱动和完整回复检查，固定 CLI 参数数组及专用工作目录，禁用强制执行选项。
- [x] 运行适配器测试与现有处理器回归。

### Task 3: 初始化、安装向导与运行模式

**Files:** 新增 butler/defaults.py、butler/install_wizard.py；修改 butler/setup.py、butler/__main__.py、scripts/setup.ps1、Telegram 初始化入口；tests/test_install_wizard.py。
**Interfaces:** `run_wizard(root, input_fn=input, secret_fn=getpass, output=print) -> dict`; installation.mode 置于 config.wxbot.toml，local/external/direct；Butler 配置保留为本机目录位置事实来源。
- [x] 写 RED 测试：所有供应方、URL/端口校验、取消无文件、重复不覆盖、不同目录、mask、启动模式。
- [x] 程序内默认值取代七份模板；设置相互一致的地址/随机 Token；提供迁移 CLI；保留非交互 init。
- [x] start/doctor 按模式工作，非 Codex 无 Codex 登录要求；Telegram 可选功能有初始化替代。
- [x] 验证 portable install、CLI、Telegram 测试。

### Task 4: 管理台、相对路径与编辑锁

**Files:** log/settings.py、log/config_editor.py、log/config_view.py、log/server.py、log 静态页面；tests/test_directory_dashboard.py、tests/test_config_editor.py。
**Interfaces:** Task 1 的 DirectoryStore 投影；log 设置读取返回绝对解析值，文件编辑保留相对值；锁文件位于内部缓存哈希路径。
- [x] 写 RED 测试：相对 sources 不随 cwd 改变、LOG_CONFIG、空值/绝对路径、数据库编辑版本冲突。
- [x] 管理台通道名单/联系人/昵称读写数据库；已迁移字段不写回 TOML；能力按接入模式展示。
- [x] 更新统一 config_lock 并安全清理空闲旧根锁；共享锁释放不 unlink。
- [x] 运行管理台/配置编辑回归。

### Task 5: 集成、文档与本机升级

**Files:** README.md、docs/CODEX_INSTALL.md、Telegram 文档、plugins 安装说明、docs/MESSAGE_API.md、tools/release.py、相关发布测试。
- [x] 删除全部 config.*.example.toml，移除有效安装路径对模板的依赖，更新发布白名单。
- [x] 运行针对性与整体离线测试，区分已有失败；运行 release.py 检查发布内容。
- [x] 新鲜上下文独立审查并修复重要问题。
- [x] 在现有安装运行已验证迁移，核对数量和身份未改变，改为等价相对 log sources，清理旧锁；必要时按用户授权重启相关服务。
- [x] 交付命令、结果和未验证的真实外部连接边界。

## 验证记录（2026-10-29）

- 最终回归：1017 passed, 3 deselected；三个排除项已在修改前 HEAD 源码复现（test_queue_admin multipart / test_queue_store confirmed actual text / test_typing half-second）。
- 独立审查的两个重要问题均经复现和修复测试关闭：独立窗口错误不会结束轮询；未知群成员回复与 reset 使用相同范围。
- 发布包 269 个源码文件，审计零发现；无模板、运行配置、凭据、数据库和编辑锁。
- 本机迁移：4 联系人、2 监听用户、1 群、31 昵称（11 待核对）。16 张既有业务表内容、连接/鉴权/高级配置及 log 来源目标均未变；二次迁移无操作。
- 本机 log 已启动并重启到最新代码；health / connection / configuration / queue 只读检查均 HTTP 200。Butler、wxbot 未为测试额外启动，未调用真实模型或发送真实测试消息。
- 外部 Butler 的管理操作由对端管理台维护；本地管理台只维护通道与本地设置。未执行 Git 提交或推送。
