---
type: concept
module: wxbot
summary: 会话须有可用音色绑定才合成/RALT；绑定与 voice.contacts 模式正交
coverage: core
last_verified: 2026-11-03
sources:
- path: src/wxbot/voice/policy.py
  line: 103
  anchor: 'def has_usable_binding(self, contact: str) -> bool:'
- path: src/wxbot/voice/policy.py
  line: 106
  anchor: 'def delivery_mode_for(self, contact: str) -> str:'
- path: src/wxbot/voice/policy.py
  line: 115
  anchor: 'def queued_media_path(self) -> str:'
- path: src/wxbot/voice/policy.py
  line: 126
  anchor: 'def resolve_queued_media_path(policy) -> str:'
- path: src/wxbot/delivery.py
  line: 74
  anchor: 'media = resolve_queued_media_path(self.voice_policy)'
- path: src/wxbot/delivery.py
  line: 312
  anchor: "has_binding = getattr(policy, 'has_usable_binding', None)"
- path: src/wxbot/queue_worker.py
  line: 159
  anchor: "delivery_mode = getattr(policy, 'delivery_mode_for', None)"
- path: src/wxbot/queue_worker.py
  line: 166
  anchor: 'voice_media = resolve_queued_media_path(policy)'
changes:
- raw/changes/2026-11-03-indextts-enqueue-media
- raw/changes/2026-11-03-feat-voice-003-voice-assets
depends_on:
- modules/wxbot
---
# 音色资产绑定与出站门控

## 规则

1. 语音出站仍要求全局 `voice.enabled` 且联系人 mode ∈ {replace, coexist}（FEAT-VOICE-001）。
2. **额外**：必须有可用绑定——contact_refs 上有效 `asset_id`（资产存在）或可解析的 `ref_wav`。
3. 无绑定 → 只回文字；不调用 TTS、不走 RALT；即使 mode 为 replace/coexist。
4. 改绑/清绑 **不** 自动改 mode；清绑 **不** 把 mode 置 off。
5. 失败回退仍按 FEAT-VOICE-001 真值表，本概念不重开。
6. 入队 `outbox.media_path`：仅 `tts_provider=fixture` 写入 `fixture_wav`。`indextts` 以及其他投递时才合成的提供者留空，`DeliveryPump._prepare_voice_audio` 因此调用 `source.prepare`，而不是 `load_wav_file`。无可用绑定时仍不入语音条。

## 相关

- [[modules/wxbot]] [[apis/dashboard-voice-assets]] [[symbols/voice-asset-store]] [[symbols/model-worker]] [[tables/queue-outbox]]
- 变更：[[raw/changes/2026-11-03-indextts-enqueue-media]]、[[raw/changes/2026-11-03-feat-voice-003-voice-assets]]
