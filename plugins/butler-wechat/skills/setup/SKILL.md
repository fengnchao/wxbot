---
name: butler-wechat-setup
description: 安装或检查 Butler/wxbot 项目与本插件的本地连接。
metadata:
  butler:
    tags: [butler-setup]
---
# 安装引导
1. 使用者需要 Windows、已登录的微信、Git、Python 3.14+ 和可用的 Codex 账户。
2. 克隆提供本插件的 Git 仓库，进入仓库；以仓库 README 的快速开始为准。
3. 运行 scripts/setup.ps1 安装项目，再运行 .venv/Scripts/python -m butler init。
4. 运行 .venv/Scripts/python -m butler login，在机器人独立环境登录使用者自己的 Codex 账户。
5. 运行 .venv/Scripts/python -m butler doctor；失败时显示具体检查结果，不打印认证文件。
6. 使用者在 log 页面设置微信昵称、联系人、角色及允许的 Skill，然后自行启动服务。
不要复制别人的配置、认证或聊天数据库。初始化不覆盖已存在配置。
没有明确授权，不发送微信测试消息、不停止或重启正在运行的服务。
