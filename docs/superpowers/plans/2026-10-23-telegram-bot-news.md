# Telegram 已收件转为新闻投递

用户要求：已入库消息继续按新闻格式交给 Butler，并说明在哪里看。

实施：
- 新增 telegram_bot/news.py，格式化文字、图注、实体链接和频道来源，媒体未发送时明确标注，跳过机器人命令及纯媒体。
- 在 relay.sqlite3 增加 news_plan/news_delivery，幂等展开已 received 的消息；既有收件也纳入。
- 新增独立新闻线程，读取 groups["1"]，使用已有 push_news(type=1,messageType=1) 对订阅者逐个投递。收件、微信等待互不阻塞。
- 请求之前持久化 sending；未确认不重发，进程重启恢复为 uncertain。同条消息后续分段等待前段成功。
- status 增加计划和逐人投递结果；已提交消息沿用 Butler 外发日志及 wxbot 队列在 log 展示。

检查：静态 Python 语法检查通过；只读确认现有 Butler inbox 有 2 条记录。未运行收发测试，未触发微信发送，未启停服务。用户需自行重启 Telegram 接收器加载改动。
