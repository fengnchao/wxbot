---
type: symbol
module: wxbot
summary: 本地 WAV 音色资产清单与文件存储
coverage: core
last_verified: 2026-11-03
sources:
- path: src/wxbot/voice/assets.py
  line: 80
  anchor: 'class VoiceAssetStore:'
- path: src/wxbot/voice/assets.py
  line: 163
  anchor: 'def register(self, *, name: str, data: bytes) -> VoiceAsset:'
- path: src/wxbot/voice/assets.py
  line: 18
  anchor: 'MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MiB raw WAV'
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
depends_on:
- modules/wxbot
- concepts/voice-asset-binding
---
# VoiceAssetStore

本地目录（默认 data/voice-assets/）保存参考 WAV + manifest。约束：仅 WAV、≤2MiB、时长 0.5–60s。供 policy 物化 sset_id→路径，及管理台注册/改名/删除/预览。

## 相关

- [[concepts/voice-asset-binding]] [[apis/dashboard-voice-assets]] [[modules/wxbot]]
- 变更：[[raw/changes/2026-11-03-feat-voice-003-voice-assets]]
