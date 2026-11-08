# 定时提醒

提醒由 Butler 业务存储和 ReminderScheduler 管理，到期经 Butler 推送交给 wxbot，不由模型或 UI 线程拥有提醒状态。运行与投递约束见 [Butler 业务功能](butler-functions.md)，工具身份与允许功能见 [身份与工具](identity-tools.md)。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 定时提醒

管理定时提醒，在约定时间触发提醒投递。
