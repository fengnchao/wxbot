---
type: api
module: dashboard
summary: 音色资产 CRUD、参考音预览与会话 contact_refs 绑定
coverage: core
last_verified: '2026-11-05'
sources:
- path: web/src/styles/voice-assets.css
  line: 7
  anchor: .workspace main:has(> .voice-assets)
- path: src/dashboard/routes.py
  line: 59
  anchor: ("GET", "/api/voice-assets", voice_assets.list_assets),
- path: src/dashboard/api/voice_assets.py
  line: 15
  anchor: 'def list_assets(ctx):'
- path: src/dashboard/voice_admin.py
  line: 14
  anchor: from wxbot.voice.assets import MAX_UPLOAD_BYTES, VoiceAssetStore, default_assets_dir
- path: web/src/views/VoiceAssetsView.vue
  line: 229
  anchor: <section id="pane" class="voice-assets"
- path: web/src/components/ContactDialog.vue
  line: 519
  anchor: 自动回复音色
changes:
- raw/changes/2026-11-03-voice-assets-polish
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-policy-save
- raw/changes/2026-11-05-group-auto-voice
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
- 会话新增 IndexTTS 授权与说明见 [[apis/index-tts]]：网页预设不要求资产绑定，自动回复仍要求。模式单独变更只提交 mode，资产未变不提交 asset_id；重命名则把当前模式/资产复制给新键。语音读取失败不以空值回写，保存失败保留弹窗并告知部分完成；接口本身保持原 schema。

## 相关

- [[concepts/voice-asset-binding]] [[symbols/voice-asset-store]] [[modules/dashboard]]
- 变更：[[raw/changes/2026-11-03-feat-voice-003-voice-assets]]

## 音色页展示约束（2026-11-03 核对）

- `web/src/views/VoiceAssetsView.vue:229` 的音色页是单内容区，不含联系人侧栏；`web/src/styles/voice-assets.css:7` 通过限定到 `.voice-assets` 的选择器覆盖共享双栏布局，并兼容 `list-open` / `list-collapsed` 偏好。保持说明、上传表单、资产清单顺序，未修改共享导航。
- 专用样式复用 `theme.css` 中 `--fg2` / `--fg3` / `--line` / `--line-strong` / `--wx`，不再引用未定义的 muted/border/accent。页内 header 取消共享 header 的定位、底色与边框；文件控件与操作保持原生键盘行为。
- `load()` 并行读取 assets/bindings，成功后调用 shell 的 `markRefreshed()`；加载首屏显示静态骨架，读取失败不显示“还没有音色”，表单成功/失败仍由既有服务结果驱动。窄屏保留表格 DOM 与表头，用 `data-label` 展示字段标签。
- 接口不变：`GET /api/voice-assets` 的 `assets[].id/name/created_at/duration_seconds` 与 `limits.max_bytes` 来自 VoiceAdmin.list_assets / VoiceAsset.as_dict；绑定列仍从 `GET /api/voice-bindings` 的 `contact_refs[contact].asset_id` 反查。POST register/rename/delete 的请求体、确认流程及 `X-Wxbot-Voice-Action` 请求头不变；preview 仍只读取参考 WAV。
- 仅 UI 与现有状态投影变更，不涉及数据库、迁移、音色文件内容、配置写入或新异步任务。参考 [[raw/changes/2026-11-03-voice-assets-polish]]。


## 联系人语音配置核对

[[raw/changes/2026-11-04-contact-index-tts]]：新增会话授权控件与原接口消费，源码位置已核对；后端契约保持。


## 联系人语音配置核对

[[raw/changes/2026-11-04-webui-preset-binding]]：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [[apis/index-tts]]。


图谱契约说明来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]。


## 策略保存复核（2026-11-05）

ContactDialog 新增未安装技能的可见勾选项和保存中提示；IndexTTS 会话授权、网页预设和音色绑定协议不变。联系人策略的锁等待修复及严格目录校验见 [[apis/dashboard-contact-policy]]。来源 [[raw/changes/2026-11-05-contact-policy-save]]。


## 群聊采集与自动语音复核（2026-11-05）

自动回复的 webui 默认推导、实时语音策略、流式缓冲、daemon 合成及录音前准确预设复核见 [[concepts/automatic-voice-reply]]；旧媒体包/离线提供者合同保留。自动 webui 的录音前失败终结并仅回退一次文字，不让 blocked 重试重复投递，无数据库迁移。来源 [[raw/changes/2026-11-05-group-auto-voice]]。
