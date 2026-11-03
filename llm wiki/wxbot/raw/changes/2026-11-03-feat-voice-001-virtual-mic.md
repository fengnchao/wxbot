---
type: change
title: FEAT-VOICE-001 P1 虚拟麦语音条（可插 TTS / Right Alt）
pages:
- modules/wxbot
- modules/delivery
- concepts/delivery-state
- tables/queue-outbox
- concepts/message-pipeline
---
# FEAT-VOICE-001 P1 虚拟麦语音条（可插 TTS / Right Alt）

## 目标与背景

白名单会话按开关以微信语音条回复。P1 打通「虚拟麦 → 长按 Right Alt」投递，可插 TTS 仅假音频验收；开会话复用现网文字校准路径，不把默认 UIA 可读气泡当作前置。IndexTTS / 管理台音色另单。

## 文件与代码位置

- `src/wxbot/voice/`：`policy.py` 配置白名单与 mode；`tts.py` WAV 合同；`playback.py` 定向 WaveOut（CABLE Input）
- `src/wxbot/wechat/voice.py` + `chat_window.start_voice`：聚焦输入区后 RALT PTT 会话
- `src/wxbot/delivery.py`：`kind=voice` 发送/确认（`confirm_evidence=ptt_release`，人工验条）；replace 失败回退文字
- `src/wxbot/queue_store.py`：`finish_batch_parts(voice_mode=...)`、`enqueue_voice`
- `src/wxbot/queue_worker.py` / `inbox.py`：注入 VoicePolicy
- `src/wxbot/outbound.py`：`/send` 可选 `voice:true`；旧客户端兼容
- `src/butler/delivery/push.py`：`push_to_wxbot(..., voice=False)`
- `tools/voice-ptt-ops.md`、`tools/voice-fixtures/p1-tone.wav`

## 接口与字段

- Outbox `kind` 新增 `voice`（表字段已有，无迁移）
- `/send` body 可选 `voice: true`；需保留 `text` 作失败回退
- 配置 `[voice]` / `[voice.contacts]`：`off|replace|coexist`（AC-10 仅配置文件）

## 数据库与迁移

不涉及新表/新列；复用 `outbox.kind` 与 `media_path`。

## 前端消费点

无管理台 UI 变更（AC-10）。

## 测试与异步任务

- 离线：WAV 合同校验、VoicePolicy、`finish_batch_parts` replace/coexist/off、`enqueue_voice`/`claim_delivery`
- WaveOut 对本机 `CABLE Input` 播放冒烟
- 真机语音条：**待人工确认**（不对真人默认狂发；确认不依赖语音气泡 UIA）
- 文本/图文 bundle：未改 image/emoji 路径；`voice=false`/缺省保持原 `/send`

## 风险与回滚

- 微信主窗内容树仍可能空：验条靠 PTT 完成 + 人工
- 流式 typing 路径未挂 voice_mode（仅完整 `finish_batch_parts`）
- 需微信麦克风选 CABLE Output；虚拟麦仓外安装
- 回滚：还原本变更文件并关 `[voice].enabled`
