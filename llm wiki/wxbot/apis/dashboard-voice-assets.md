---
type: api
module: dashboard
summary: 音色资产 CRUD、参考音预览与会话 contact_refs 绑定
coverage: core
last_verified: 2026-11-03
sources:
- path: src/dashboard/routes.py
  line: 57
  anchor: '("GET", "/api/voice-assets", voice_assets.list_assets),'
- path: src/dashboard/api/voice_assets.py
  line: 15
  anchor: 'def list_assets(ctx):'
- path: src/dashboard/voice_admin.py
  line: 14
  anchor: 'from wxbot.voice.assets import MAX_UPLOAD_BYTES, VoiceAssetStore, default_assets_dir'
- path: web/src/views/VoiceAssetsView.vue
  line: 228
  anchor: '<section id="pane" class="voice-assets" aria-labelledby="voice-assets-title">'
- path: web/src/components/ContactDialog.vue
  line: 354
  anchor: '回复音色'
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
---
# 管理台音色资产与绑定 API

## 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/voice-assets | 列表 + limits（preview=
egistered_reference） |
| GET | /api/voice-assets/preview | 返回已注册参考 WAV 字节 |
| GET | /api/voice-bindings | enabled/modes/contacts/contact_refs/assets |
| POST | /api/voice-assets | register/rename/delete/bind；需 X-Wxbot-Voice-Action |

均纳入 dashboard BUSINESS 门（外部接入时本机不承担）。

## 前端

- Tab「音色」→ [[modules/web]] VoiceAssetsView
- 会话设置「回复音色」→ ContactDialog，与回复模式同区

## 相关

- [[concepts/voice-asset-binding]] [[symbols/voice-asset-store]] [[modules/dashboard]]
- 变更：[[raw/changes/2026-11-03-feat-voice-003-voice-assets]]
