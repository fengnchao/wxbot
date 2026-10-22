# 安装、运行和升级

## 首次使用

要求 Windows、Python 3.14+、Git、已登录的微信和可使用 Codex 的账户。
可安装 uv，让项目自动准备 Python 环境。插件与项目使用同一个 Git 仓库地址。

```powershell
# 使用项目发布的实际 Git 地址替换 <仓库地址>
codex plugin marketplace add <仓库地址>
codex plugin add butler-wechat@butler-wechat-plugins
git clone <仓库地址> butler-wxbot
cd butler-wxbot
.\scripts\setup.ps1
.\.venv\Scripts\python.exe -m butler login
.\.venv\Scripts\python.exe -m butler doctor
```

插件也可以在克隆后用本地来源安装：

```powershell
codex plugin marketplace add .
codex plugin add butler-wechat@butler-wechat-plugins
```

安装后可调用 `butler-wechat-setup` Skill 查看引导。应用未启动、没有
身份凭证时，插件业务工具不连通是正常状态；安装引导本身不依赖这些工具。
机器人运行时按请求签发凭证；不要手动把机器人凭证写入个人 Codex 配置。

初始化不会覆盖已有配置。若提示保留了旧 Hermes 配置，请在新的克隆目录使用
Codex 版本；不要把别人的配置文件或 `data/` 复制过来。

## 设置并启动

先分别启动 Butler 和 log，浏览器访问 http://127.0.0.1:8788：

```powershell
.\.venv\Scripts\python.exe -m butler.server
.\.venv\Scripts\python.exe -m log.server --open
```

在「配置管理」设置：

- wxbot 的 `bot.mention_names`：微信中的机器人昵称；群聊只有被 @ 才处理。
- Butler 的 `contacts`：联系人或群名、唯一 uid；群可添加 `channel_type="group"`。
- 「角色与心跳」：绑定角色、允许的功能 Skill，按需开启心跳。
- `codex.model` 留空使用运行时默认模型；其他参数保存后按页面提示自行重启。

默认不绑定任何联系人、不订阅心跳。未单独绑定角色的会话使用简短的默认助理角色，
不能操作记忆或提醒；允许 `butler-memory`、`create-cron-job` 后相应工具才开放。

配置完成后再启动微信监听：

```powershell
.\.venv\Scripts\python.exe -m wxbot.main
```

或者在所有端口空闲时运行 `python -m butler start`，同时启动三个服务。
该命令不停止已有服务；Ctrl+C 只终止本次命令创建的子进程。
微信需保持可访问、电脑未锁屏。不同微信版本可能需要校准控件。

## 数据和权限

`data/business.sqlite3` 保存身份、Thread ID、记忆、提醒及运行记录；
`data/codex/` 保存机器人自己的 Codex 登录和会话；`data/cache/` 保存策略、心跳和日志。
这些目录和本机配置均不提交 Git。相对业务路径以 Butler 配置所在目录为基准。

聊天按用户／群隔离，心跳使用独立会话。角色或权限变化会切换会话范围。
所有业务工具在服务端检查身份；模型不能通过参数切换用户。
心跳没有写入权限。原生命令、浏览器、个人插件和全局记忆默认不向机器人开放。

一次性提醒可用 `in 30m` 或 ISO 时间，重复提醒使用五段 cron，按电脑本地时区计算。
提醒投递失败或进程在投递中退出时保留失败记录，不自动重发；到 log 查看后人工处理。
已进入投递的提醒不能再取消，接口会提示检查投递状态；排队中的提醒仍可取消。
调度器错过停机时间的任务在恢复后投递一次，重复任务继续下一个未来时间点。

## 环境检查及故障

`python -m butler doctor` 只检查登录文件是否存在、插件协议、端口、依赖及微信窗口／控件，
不会发送消息。文件存在不等于登录仍然有效。登录过期时重新运行 `python -m butler login`。

Windows 系统代理会传给 Codex 子进程，并绕过 localhost。也可在启动前设置
`HTTPS_PROXY`；代理凭据不要放进 Git。连接失败、超时或回复未完成时不交给微信发送。
「模型与记忆」查看工具、提醒、记忆；「wxbot 通道」查看消息流转和发送结果。

## 升级和旧部署切换

1. 备份本机配置和 `data/`，更新项目及插件；运行环境检查。
2. 插件和应用使用业务协议 v1；不兼容时启动检查明确报错。
3. 本版本不导入 Hermes 数据，旧会话和提醒不会自动转移。
4. 现有部署请另建目录初始化、登录、配置；自行停止旧 Butler/wxbot/log 后启动新版本。
5. 自行停用旧 Hermes 中的心跳、提醒及看门狗任务，避免旧任务继续推送。
6. 首次上线前先检查队列；程序不会自动清空旧队列或重新发送不确定任务。

## 验证与发布

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe tools\probe_codex.py --auth-home <已登录的Codex目录>
.\.venv\Scripts\python.exe tools\release.py
```

真实探针只在临时业务目录运行，并禁止所有微信投递；会使用指定账户的模型额度，
在该 Codex home 中保留探针会话，业务测试数据在退出时清理。
发布工具生成应用包、独立插件包并检查排除认证、配置、缓存、数据库和编译产物。
发布包不包含旧 Hermes 运维脚本，旧部署的操作说明仍保留在源码中供参考。
