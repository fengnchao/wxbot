# 安装、运行和升级

## 首次使用

要求 Windows、Python 3.14+、Git 和已登录的微信。可安装 uv 自动准备 Python 环境。
插件与项目使用同一个 Git 仓库地址；本机 Codex 模式使用安装者自己的 Codex 账户。

```powershell
codex plugin marketplace add <仓库地址>
codex plugin add butler-wechat@butler-wechat-plugins
git clone <仓库地址> butler-wxbot
cd butler-wxbot
.\scripts\setup.ps1
.\.venv\Scripts\python.exe -m butler doctor
```

插件也可以在克隆后通过 `codex plugin marketplace add .` 添加本地来源，再执行上述插件安装命令。
安装后的 `butler-wechat-setup` Skill 提供引导；未启动应用时业务工具不连通属于正常状态。
机器人在运行时按请求签发身份凭证；不要把机器人凭证手动写入个人 Codex 配置。

安装脚本调用 `python -m butler setup`。向导收集接入方式、机器人昵称、服务地址／端口及必要凭据，
显示脱敏摘要后确认写入。取消不会留下部分运行配置；已有配置保留，升级使用显式迁移命令。
默认配置由 [butler/defaults.py](../butler/defaults.py) 生成，不分发或复制配置模板。
自动化安装可用 `python -m butler init --directory <安装目录>`，它是非交互、幂等的本机 Codex 初始化。
不要复制其他安装的配置、认证或 `data/`。

| 向导选择 | 模式 | 配置和登录 |
|---|---|---|
| Codex | local | 可填写 API Key，或运行 `python -m butler login` 登录本人账户；登录保存在机器人自己的目录 |
| 已有 Butler | external | 填写现有 Butler 地址和 Token，本机不运行 Butler |
| Hermes | direct | 填写已运行的兼容 API 服务地址、模型及凭据 |
| OpenClaw | direct | 网关先启用 HTTP 对话端点，填写地址、凭据及 agent |
| Cursor | direct | 已安装并授权的无界面 CLI；专属工作目录、只读 `--mode ask` 和沙箱 |
| DeepSeek | direct | 填写 API 凭据及服务端实际模型名称 |
| 自定义 API | direct | 选择 Chat Completions 或 Responses，填写地址、模型及凭据 |

`local/external/direct` 写入 `config.wxbot.toml` 的 `[installation].mode`；
模型协议写入 `[model]`。非 Codex 接入不要求本机 Codex 登录。直接接入仅调用模型，
不提供本机 Butler 记忆、提醒和业务工具；外部 Butler 的能力及权限由该服务管理。外部模式仅通过配置的消息接口调用远端；
本机管理台关闭远端账户、记忆、心跳管理，请使用远端自己的管理台。
向导只写配置，不验证真实模型连接、不启动服务。

## 设置并启动

```powershell
.\.venv\Scripts\python.exe -m butler start
```

`local` 启动 Butler、log、wxbot；`external/direct` 只启动 log、wxbot。
默认管理台为 http://127.0.0.1:8788，地址以向导结果和本机配置为准。
端口占用时命令退出并保留已有服务；Ctrl+C 只终止本次启动的子进程。
也可以按模式分别运行 `python -m butler.server`、`python -m log.server --open`、`python -m wxbot.main`。

在「配置管理」维护机器人昵称、监听名单、联系人与群昵称；本机 Codex 模式在「角色与心跳」
绑定角色和允许的 Skill。默认空联系人、空绑定、关闭心跳。角色或工具未授权时不能操作个人业务数据。
配置修改后按页面提示自行重载对应服务。微信主窗口必须可访问，电脑不能锁屏；控件随版本变化可能需要校准。
监听名单与身份授权分别管理：昵称和头像观测不会自动授予身份、记忆或工具权限。

## 数据与路径

`data/business.sqlite3` 保存共享目录、稳定身份、Thread ID、记忆、提醒及业务记录。
共享目录的联系人、监听设置和按群昵称由 Butler 服务层维护，wxbot、管理台读取投影。
`data/codex/` 保存机器人自己的 Codex 登录和会话；运行缓存、队列及 Telegram 状态仍按各配置管理。
这些目录和所有实际配置均不能提交或分发。

相对运行路径以对应配置文件所在目录为基准，切换工作目录不会改变数据库或队列位置。
`config.log.toml` 的 `[sources]` 同样以该配置文件目录解析；文件中保留相对写法，管理台显示解析后的路径。
`LOG_CONFIG` 可指定 log 配置，命令行和环境变量的显式覆盖优先。
配置编辑锁使用内部缓存中的规范路径哈希位置，不再要求根目录编辑锁；共享锁释放时不删除锁文件。

业务工具在服务端验证身份和权限，模型参数、角色提示及昵称不是授权来源。
聊天按用户／群隔离，角色权限变化切换会话范围；心跳使用独立会话且无写入权限。
提醒不确定投递不自动重发，应先在 log 核对；不要通过删除队列或数据库强制重发。

## 环境检查及故障

`python -m butler doctor` 按模式检查端口、依赖、插件协议及微信窗口／控件，不发送消息。
只有本机 Codex 模式检查对应登录文件或已配置的 API Key；这是配置检查，不代表凭据已通过远端验证。使用账户登录且过期时运行 `python -m butler login`。
`--no-wechat` 可跳过微信检查。检查成功不代表外部服务、CLI 授权或真实模型连接已验证。
连接失败、超时、需要交互审批或回复不完整时，不把部分回复交给微信发送。
「实时工作流」及「收发队列」可查看进度与发送结果；记忆在「用户与记忆」管理，直接模式仅显示该模式支持的能力。

## 升级现有安装

1. 备份本机配置与完整数据目录，更新项目及插件；不要新建目录后复制其他安装的数据。
2. 在原安装运行 `python -m butler migrate --directory <安装目录>`；也可用 `--config <Butler配置路径>` 指定目录。
3. 迁移将旧配置的联系人、通道名单和按群昵称导入共享 `business.sqlite3`，保留 uid、会话和权限；迁移账本使重跑不覆盖新修改。
4. 只清理成功导入且仍匹配迁移快照的旧配置字段；导入失败保留旧字段。没有群范围的旧昵称保留待核对，不自动绑定身份。
5. 在管理台核对联系人数量、稳定身份、监听开关和群昵称；核对 `config.log.toml` 的相对 sources 指向原数据目录。
6. 按需自行重载对应服务，检查旧队列和不确定任务。程序不清空旧队列，不自动重发；旧 Hermes 数据不自动导入。

已有配置缺少 `[installation]` 时保持兼容本机模式；缺少 `agent.provider` 的旧 Butler 配置继续使用 Hermes。
`init/setup` 保留既有配置，不代替迁移。仍在运行的旧心跳、提醒或看门狗需由安装者自行核对，避免重复推送。

## 验证与发布

```powershell
.\.venv\Scripts\python.exe -B -m pytest -o addopts= -p no:cacheprovider
.\.venv\Scripts\python.exe tools\release.py
```

离线测试使用临时配置、数据库、假 UI 和假投递，不发送真实微信消息。
模型探针 `tools/probe_codex.py --auth-home <本人已登录的Codex目录>` 会消耗模型额度并在该目录保留会话，
应在明确授权后运行；探针使用临时业务数据、禁止微信投递。
发布工具生成应用包和独立插件包，包含默认值、向导和 [消息接口文档](MESSAGE_API.md)，
排除全部配置 TOML、认证、会话、缓存、数据库、编译产物和旧 Hermes 运维脚本。
真实外部连接、Telegram 转发和微信发送须另行授权验证，离线测试不能代替这些结果。
