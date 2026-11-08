# 文字处理器

文字处理器读取同一 outbox 的 text 项，使用既有剪贴板、草稿保护、提及与气泡确认契约。调度和状态见 [统一发件](delivery-pump.md)，回复分句见 [文字发件](outbox-text.md)。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 文字处理器

实现：`src/wxbot/delivery_handlers/text.py` 的 TextDeliveryHandler。

启动正文输入与群聊提及，处理流式增量、封口提交及取消后的草稿清理。
用新出现的自身气泡确认发送，保留引用证据和无引用时的文字降级。
与图片处理器共用 bubble.py 中的目标、草稿、提交前复核和确认时限。
