# 表情处理器

表情项由独立处理器发送，统一调度与回执仍归 DeliveryPump。配置未校准时沿用文字回退；实现和历史依据见 [统一发件](delivery-pump.md) 与 [微信 UI](wechat-ui.md)。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 表情处理器

实现：`src/wxbot/delivery_handlers/emoji.py` 的 EmojiDeliveryHandler。

调用原 send_sticker 并保存 sent、blocked 或 uncertain 状态。
目标窗口核对与失败诊断保持原行为，点击后无法确认时不自动重复点击。
与文字、图片、语音共用同一张 outbox 和统一调度器。
