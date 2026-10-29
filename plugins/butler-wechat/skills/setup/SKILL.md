---
name: butler-wechat-setup
description: 安装或检查 Butler/wxbot 项目与本插件的本地连接。
metadata:
  butler:
    tags: [butler-setup]
---
# 安装引导
1. 使用者需要 Windows、已登录的微信、Git、Python 3.14+；本机 Codex 接入需要本人账户。
2. 克隆提供本插件的 Git 仓库，进入仓库；以仓库 README 的快速开始为准。
3. 运行 scripts/setup.ps1 安装项目并进入 `python -m butler setup` 向导。确认脱敏摘要后生成配置，无需复制模板。
4. 选择 Codex、Hermes、OpenClaw、Cursor、DeepSeek、已有 Butler 或自定义 Chat Completions／Responses。只有本机 Codex 需要运行 `.venv/Scripts/python -m butler login`，在机器人独立目录登录本人账户。
5. 运行 `.venv/Scripts/python -m butler doctor`；检查按 local/external/direct 模式执行，不打印认证文件，也不验证真实模型连接。
6. 在 log 管理共享目录的微信昵称、监听名单、联系人和群昵称；本机 Codex 模式可绑定角色及允许的 Skill，然后运行 `python -m butler start`。
7. 现有配置先备份再运行 `python -m butler migrate`，核对稳定身份和监听范围；`python -m butler init` 是非交互、幂等初始化，不覆盖已有配置，也不代替迁移。
直接模型接入不提供 Butler 记忆、提醒或业务工具；外部 Butler 的权限由对应服务管理；本机管理台不管理远端账户、记忆和心跳，请使用远端自己的管理台。
不要复制别人的配置、认证或聊天数据库。向导不启动服务；没有明确授权，不发送微信测试消息、不停止或重启正在运行的服务。
