# log Telegram 工作流与完整队列

用户明确要求在实时流转增加 Telegram，并在收发队列看到所有消息及阻塞记录。本次直接扩展既有看板，不改变业务调度。

## 已确认原因及证据

- 原 QueueView 仅查询 wxbot SQLite；Telegram 收件及新闻任务存于另一数据库，完全未接入。
- inbox 查询始终带 batch_id IS NULL，已合并收件在任何页面均不可见。前端默认 active，无全部消息入口。
- 只读查询真实 wxbot 队列：待合并 2、ready 模型 0、blocked 模型 1、pending 发件 27、blocked 发件 1。原数据存在。新 all 查询共 159 收件、144 批次、272 发件。
- Telegram 当前有 2 条 received 记录，新闻表尚未创建，说明正在使用的接收进程尚未建立新版新闻任务；不修改或迁移它的数据。
- log 默认地址当时无法连接，浏览器工具无打开页面，未声称复现实际浏览器空白根因。

## 实施

- log/telegram_view.py 只读解析配置路径、relay 状态及 Butler 实际收件回执；私密字段不返回页面，已知 Bot Token 从预览脱敏。新旧 schema 兼容。
- /api/queue 添加独立 Telegram 列表、过滤和分页。/api/workflow 添加 Telegram 节点与消息，新闻调用走同一个 Butler，不虚构模型调用。
- 收发队列默认 all，收件包含已合并；保留 active/issues/history，分页越界回到有效页，提供清空筛选。wxbot 数据缺失不隐藏 Telegram。
- 阻塞原因、前置分段任务 ID、失败详情可见；现有 wxbot 人工处理按钮保留。Telegram 展示不宣称提供未实现的恢复按钮。
- 共用 Butler 节点，侧边新增 Telegram 入口及动态连线。事件动画基于已记录状态，跨系统没有共同 ID 时独立展示。

## 检查与边界

已执行只读真实数据库投影和 Python/JavaScript 静态语法检查。未新增/运行测试套件，未启动服务，未修改运行队列或发送消息。用户需自行重启 log 并刷新页面；尚未进行运行中浏览器的视觉验收。
