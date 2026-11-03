---
type: change
title: FEAT-VOICE-003 音色资产与会话绑定
pages:
  - apis/dashboard-knowledge
  - apis/dashboard-queue
  - apis/dashboard-workflow
  - concepts/delivery-state
  - concepts/group-identity-evidence
  - concepts/message-pipeline
  - concepts/model-error-contract
  - concepts/unread-capture-retry
  - modules/dashboard
  - modules/wxbot
  - modules/web
  - tables/knowledge-vault
  - tables/queue-outbox
  - apis/dashboard-voice-assets
  - concepts/voice-asset-binding
  - symbols/voice-asset-store
---
# FEAT-VOICE-003 音色资产与会话绑定

## 目标与背景

管理台提供音色资产 CRUD（上传/注册参考 WAV、列表、改名、删除、试听已注册参考音），并把资产绑定到联系人/会话（含群）的 oice.contact_refs.<key>.asset_id。无可用绑定（无有效 asset_id 且无解析得到的 ref）时即使 oice.contacts 为 replace/coexist 也只回文字、不合成、不走 RALT。绑定与模式正交：改绑/清绑不自动改 mode。UI 禁止「训练」「微调」；试听只播放已注册参考 WAV，不触发 IndexTTS 试合成。独立 Tab「音色」；绑定 UI 挂在现有会话设置「回复音色」。

## 文件与代码位置

- src/wxbot/voice/assets.py:80：class VoiceAssetStore（WAV-only、≤2MiB、0.5–60s，manifest 于 data/voice-assets/）
- src/wxbot/voice/policy.py:103：has_usable_binding；delivery_mode_for 无绑定强制文字；sset_id→路径物化
- src/wxbot/voice/tts.py：去掉无绑定的 default_ref_wav 回退
- src/wxbot/queue_worker.py:158 / src/wxbot/delivery.py:311：出站按 binding 门控
- src/dashboard/voice_admin.py / src/dashboard/api/voice_assets.py：资产与绑定写配置（tomlkit + config_lock，确认头 X-Wxbot-Voice-Action）
- src/dashboard/routes.py:57：GET/POST /api/voice-assets、/preview、/api/voice-bindings 纳入 BUSINESS 门
- src/dashboard/http.py：大 body / 二进制预览响应
- web/src/router.js:11：Tab oice-assets「音色」
- web/src/views/VoiceAssetsView.vue:228：资产页；试听 previewAsset 拉注册 WAV
- web/src/components/ContactDialog.vue:354：会话「回复模式」+「回复音色」
- web/src/styles/voice-assets.css / web/scripts/smoke.mjs / web/dist/*：样式、烟测、构建产物

## 接口与字段

- GET /api/voice-assets → {ok, assets[], assets_dir, limits{max_bytes, formats, preview}}
- GET /api/voice-assets/preview?id= → 注册参考 WAV 二进制（非 IndexTTS）
- POST /api/voice-assets + X-Wxbot-Voice-Action: register|rename|delete|…（body 可含 base64 WAV）
- GET /api/voice-bindings → {enabled, modes, contacts, contact_refs, assets}
- POST /api/voice-assets action 保存绑定：{contact, mode, asset_id}；清 sset_id 不改 mode；改 mode 不改绑定
- 配置：oice.contact_refs.<contact>.asset_id；oice.assets_dir 可选

## 数据库与迁移

不涉及。资产落本地目录 data/voice-assets/（gitignored）+ manifest JSON；绑定写入 config.wxbot.toml。

## 前端消费点

- 导航 TABS 增加「音色」；App.vue 注册 VoiceAssetsView；外部接入模式随业务页隐藏
- 联系人/会话对话框与语音模式同区展示「回复音色」select/clear（含群）
- 文案不含「训练」「微调」；Hallmark --scope app 对新增页 0 FAIL

## 测试与异步任务

- 
pm.cmd --prefix web run build / smoke：含音色导航与资产页渲染
- 本地 Python 自测：register/rename/bind/preview/delete + delivery_mode_for 无绑定→文字
- 不重启服务；真机微信发测另授（AC-12 范围外）

## 风险与回滚

- 绑定缺失时静默文字：符合产品；运维需在管理台显式绑定
- 预览仅参考音，不能验证 IndexTTS 音色相似度（AC 明确）
- 回滚：还原本分支；删除 data/voice-assets 不影响文本通路；清 contact_refs 即可停合成
