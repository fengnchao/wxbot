# Telegram Bot → Butler 收件实施计划

**Goal:** 完成用户缩小后的第一段：Bot API 收件，经 HTTP 提交 Butler 并持久化确认。
**Architecture:** 独立长轮询进程与本地持久队列；Butler 提供幂等收件接口；本阶段不调用模型或发微信。
**Spec:** 本轮用户要求“先把机器人收到消息转到 Butler 这一关跑通”，覆盖原窗口转发设计的后半段收件能力。
**Tech Stack:** requests、SQLite、现有 Butler HTTP server。

- [x] 新增 bot 配置/命令入口，Token 本机输入；私聊发送者数字 ID 白名单，缺省不接收业务消息。
- [x] Bot API 长轮询，先入本地队列再推进 offset，按机器人 ID 隔离；独立投递循环，不因 Butler 离线停止收件。
- [x] 新增 /v1/telegram/inbox，Bearer 鉴权，按 bot_id/update_id 幂等写盘后确认；支持文字、消息实体、图片及转发来源元数据。
- [x] 加入只读 status 命令、部署步骤及配置模板，发布不含 Token。
- [x] 静态检查及临时数据联调：带中文/空格临时目录，随机端口 HTTP handler，假 Butler 对象。确认 200 received/duplicate、400 冲突/群消息拒绝、401 缺少鉴权、白名单、重开队列与持久游标；未访问真实 Telegram 或微信。
- [ ] 真实联调：等待用户本机配置 Token 与自行重启 Butler。不得声称已真实收件成功。

边界：不启停现有服务，不使用聊天中已泄露的 Token；不调用微信或真实 Telegram 发消息。图片本阶段只保存 Bot API 文件标识，不下载、不发微信。失败提交可重试仅因为接收接口有持久幂等键。现有工作区改动保留。
