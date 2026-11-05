---
type: concept
module: wxbot
summary: 自动回复语音须绑定；授权网页预设音频包独立提供参考音
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/wxbot/voice/policy.py
  line: 112
  anchor: 'def has_usable_binding(self, contact: str) -> bool:'
- path: src/wxbot/voice/policy.py
  line: 123
  anchor: 'def delivery_mode_for(self, contact: str) -> str:'
- path: src/wxbot/voice/policy.py
  line: 132
  anchor: 'def queued_media_path(self) -> str:'
- path: src/wxbot/voice/policy.py
  line: 143
  anchor: 'def resolve_queued_media_path(policy) -> str:'
- path: src/wxbot/delivery.py
  line: 86
  anchor: media = resolve_queued_media_path(policy)
- path: src/wxbot/delivery.py
  line: 215
  anchor: has_binding = getattr(policy, 'has_usable_binding', None)
- path: src/wxbot/queue_worker.py
  line: 117
  anchor: delivery_mode = getattr(policy, 'delivery_mode_for', None)
- path: src/wxbot/queue_worker.py
  line: 120
  anchor: voice_media = resolve_queued_media_path(policy)
changes:
- raw/changes/2026-11-03-indextts-enqueue-media
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-group-auto-voice
depends_on:
- modules/wxbot
---
# 音色资产绑定与出站门控

## 规则

1. 语音出站仍要求全局 `voice.enabled` 且联系人 mode ∈ {replace, coexist}（FEAT-VOICE-001）。
2. **自动回复与旧主动推送**额外要求可用绑定：webui 使用精确会话的默认网页预设；离线 indextts/显式 fixture 使用 contact_refs 上有效 `asset_id` 或可解析的 `ref_wav`。
3. 上述自动路径无绑定 → 只回文字；不调用 TTS、不走 RALT；即使 mode 为 replace/coexist。
4. 改绑/清绑 **不** 自动改 mode；清绑 **不** 把 mode 置 off。
5. 失败回退仍按 FEAT-VOICE-001 真值表，本概念不重开。
6. 入队 `outbox.media_path`：仅 `tts_provider=fixture` 写入 `fixture_wav`。`indextts` 以及其他投递时才合成的提供者留空，`DeliveryPump._prepare_voice_audio` 因此调用 `source.prepare`，而不是 `load_wav_file`。无可用绑定时仍不入语音条。
7. [[apis/index-tts]] 是显式授权例外：网页预设已经提供参考音，完整生成后以带 package_id/media_id 的 WAV 包入队，media_path 来自鉴权缓存；不检查管理台绑定、不再次合成，仍要求 voice.enabled 与联系人 mode。原第 6 条仅适用于原自动路径。此例外由 [[raw/changes/2026-11-04-index-tts-skill]] 追加，不改写旧 raw。

## 相关

- [[modules/wxbot]] [[apis/dashboard-voice-assets]] [[symbols/voice-asset-store]] [[symbols/model-worker]] [[tables/queue-outbox]]
- 变更：[[raw/changes/2026-11-03-indextts-enqueue-media]]、[[raw/changes/2026-11-03-feat-voice-003-voice-assets]]


## 群聊采集与自动语音复核（2026-11-05）

自动语音的真实 WebUI 默认、配置热读、streaming 缓冲、daemon 合成和录音前准确预设复核见 [[concepts/automatic-voice-reply]]；当前面板与会话选择前的越屏恢复见 [[concepts/capture-viewport]]。保持未知发送方快照与原模型权限/重试合同，不改数据库或外部 API。来源 [[raw/changes/2026-11-05-group-auto-voice]]。
