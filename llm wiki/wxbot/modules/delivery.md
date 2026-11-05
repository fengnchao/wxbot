---
type: module
module: delivery
summary: 主动推送、补发、媒体与提醒归业务服务所有
coverage: overview
last_verified: '2026-11-05'
sources:
- path: src/butler/delivery/tts_presets.py
  line: 12
  anchor: 'class PresetBindings:'
- path: src/butler/delivery/push.py
  line: 19
  anchor: def push_to_wxbot(
- path: src/butler/delivery/reminders.py
  line: 5
  anchor: 'class ReminderScheduler:'
- path: src/butler/delivery/automatic_tts.py
  line: 33
  anchor: 'class AutomaticReplyTts:'
changes:
- raw/changes/2026-11-03-feat-voice-001-virtual-mic
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-group-auto-voice
---
# Butler 投递业务

## 范围与边界

`src/butler/delivery/` 负责主动推送、补发、媒体和提醒。push_to_wxbot 将主动推送交给 wxbot 外发 HTTP 服务；最终 UI 发件由 [[modules/wxbot]] 拥有，Butler 不操作窗口。

## 关系与缺口

`tts_presets.PresetBindings` 将网页动态列表和会话默认选择连接到生成服务，配置保存在 Butler data_dir 中并以内容修订保护原子修改。显式音色优先；省略音色仅可使用当前会话默认。管理台适配与状态、幂等默认快照见 [[apis/index-tts]]，不会把本地自动回复资产当作网页预设列表。

网页预设语音由 `gradio_tts.GradioTtsClient` 复用已加载的本机模型，`tts.TTSService` 在事务外生成、最后复核能力，`AudioStore` 按身份散列分区保存标准 WAV；只向 wxbot 提交媒体编号。`queue_voice_to_wxbot` 等待持久化入队，不等待全部播放，协议见 [[apis/index-tts]]；该路径不使用新闻订阅授权。

属于 [[modules/butler]]；消息处理先认领补发再调用模型，见 [[symbols/butler-handle]]。wxbot 出站持久化见 [[tables/queue-outbox]]。主动推送/媒体端点、提醒业务表和调度字段仍待完整建档；本概览不代表这些接口已完成契约巡检。

## 代码依据

- `src/butler/delivery/push.py:19` — `def push_to_wxbot(`
- `src/butler/delivery/reminders.py:5` — `class ReminderScheduler:`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

## 变更

- 2026-11-03: FEAT-VOICE-001 P1 outbox kind=voice（虚拟麦+RALT）；见 [[raw/changes/2026-11-03-feat-voice-001-virtual-mic]]


## 本次核对

[[raw/changes/2026-11-04-index-tts-skill]]：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [[apis/index-tts]]，其余已述契约未改。


## 联系人语音配置核对

[[raw/changes/2026-11-04-webui-preset-binding]]：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [[apis/index-tts]]。


图谱契约说明来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]。


## 群聊采集与自动语音复核（2026-11-05）

自动回复的 webui 默认推导、实时语音策略、流式缓冲、daemon 合成及录音前准确预设复核见 [[concepts/automatic-voice-reply]]；旧媒体包/离线提供者合同保留。自动 webui 的录音前失败终结并仅回退一次文字，不让 blocked 重试重复投递，无数据库迁移。来源 [[raw/changes/2026-11-05-group-auto-voice]]。
