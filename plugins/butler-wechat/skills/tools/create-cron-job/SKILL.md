---
name: create-cron-job
description: 用户要求提醒、定时通知、查询或取消提醒时使用。
metadata:
  butler:
    tags: [butler-tool]
    tools: [reminder_create, reminder_list, reminder_cancel]
---
# 微信提醒
使用 Butler MCP 的 reminder_create / reminder_list / reminder_cancel。
时间格式：in 2m、in 1h、带时区的 ISO 时间，或五段 cron 表达式。
cron 按运行电脑的本地时区计算。缺正文、时间或重复规则时直接问用户。
工具不接收收件人；服务端自动绑定当前用户或群，不能指定其他联系人。
先得到成功结果，再按绑定角色简短确认时间、内容和任务 ID。
到点由 Butler 投入微信队列；不要调用终端、直接操作微信或创建外部 Cron。
