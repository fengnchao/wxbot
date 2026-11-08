# 语音处理器

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 语音处理器

实现：`src/wxbot/delivery_handlers/voice.py` 的 VoiceDeliveryHandler。

持有音频准备 Future，选择 TTS 或已有可信 WAV，复核当前会话模式和音色绑定后启动 PTT。
沿用 ptt_release 回执，需人工核对声音是否送达；失败按原 replace/coexist 规则回退。
自动 WebUI 录音前失败只回退一次文字，关闭或删除后不使用晚到的合成结果。
后台只生成音频，窗口选择与录音在 UI 线程执行。

## 技术资料

- [管理台音色资产与绑定 API](#doc-d265cc1e47a521) · `llm wiki/wxbot/apis/dashboard-voice-assets.md`
- [自动回复网页语音](#doc-070a8b5f81ad00) · `llm wiki/wxbot/concepts/automatic-voice-reply.md`
- [音色资产绑定与出站门控](#doc-7159ca2e34cdf0) · `llm wiki/wxbot/concepts/voice-asset-binding.md`
- [VoiceAssetStore](#doc-a41b10d5400ad9) · `llm wiki/wxbot/symbols/voice-asset-store.md`
- [虚拟麦 + Right Alt 语音条操作说明（FEAT-VOICE-001 P1）](#doc-153f05bdd2f77f) · `tools/voice-ptt-ops.md`

<a id="doc-d265cc1e47a521"></a>

### 管理台音色资产与绑定 API

来源：`llm wiki/wxbot/apis/dashboard-voice-assets.md:1`。

```yaml
type: api
module: dashboard
summary: 音色资产 CRUD、参考音预览与会话 contact_refs 绑定
coverage: core
last_verified: '2026-11-06'
sources:
- path: web/src/styles/voice-assets.css
  line: 7
  anchor: .workspace main:has(> .voice-assets)
- path: src/dashboard/routes.py
  line: 60
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
  line: 387
  anchor: 自动回复音色
changes:
- raw/changes/2026-11-03-voice-assets-polish
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-policy-save
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-diary-web
```
### 管理台音色资产与绑定 API

#### 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/voice-assets | 列表 + limits（preview=
egistered_reference） |
| GET | /api/voice-assets/preview | 返回已注册参考 WAV 字节 |
| GET | /api/voice-bindings | enabled/modes/contacts/contact_refs/assets |
| POST | /api/voice-assets | register/rename/delete/bind；需 X-Wxbot-Voice-Action |

均纳入 dashboard BUSINESS 门（外部接入时本机不承担）。

#### 前端

- Tab「音色」→ [modules/web](dashboard.md#doc-aeec90dfe23cd3) VoiceAssetsView
- 会话设置「回复音色」→ ContactDialog，与回复模式同区
- 会话新增 IndexTTS 授权与说明见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)：网页预设不要求资产绑定，自动回复仍要求。模式单独变更只提交 mode，资产未变不提交 asset_id；重命名则把当前模式/资产复制给新键。语音读取失败不以空值回写，保存失败保留弹窗并告知部分完成；接口本身保持原 schema。

#### 相关

- [concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0) [symbols/voice-asset-store](delivery-voice.md#doc-a41b10d5400ad9) [modules/dashboard](dashboard.md#doc-bb47c9474691fe)
- 变更：[raw/changes/2026-11-03-feat-voice-003-voice-assets](delivery-voice.md#doc-a855357d83ac5d)

#### 音色页展示约束（2026-11-03 核对）

- `web/src/views/VoiceAssetsView.vue:229` 的音色页是单内容区，不含联系人侧栏；`web/src/styles/voice-assets.css:7` 通过限定到 `.voice-assets` 的选择器覆盖共享双栏布局，并兼容 `list-open` / `list-collapsed` 偏好。保持说明、上传表单、资产清单顺序，未修改共享导航。
- 专用样式复用 `theme.css` 中 `--fg2` / `--fg3` / `--line` / `--line-strong` / `--wx`，不再引用未定义的 muted/border/accent。页内 header 取消共享 header 的定位、底色与边框；文件控件与操作保持原生键盘行为。
- `load()` 并行读取 assets/bindings，成功后调用 shell 的 `markRefreshed()`；加载首屏显示静态骨架，读取失败不显示“还没有音色”，表单成功/失败仍由既有服务结果驱动。窄屏保留表格 DOM 与表头，用 `data-label` 展示字段标签。
- 接口不变：`GET /api/voice-assets` 的 `assets[].id/name/created_at/duration_seconds` 与 `limits.max_bytes` 来自 VoiceAdmin.list_assets / VoiceAsset.as_dict；绑定列仍从 `GET /api/voice-bindings` 的 `contact_refs[contact].asset_id` 反查。POST register/rename/delete 的请求体、确认流程及 `X-Wxbot-Voice-Action` 请求头不变；preview 仍只读取参考 WAV。
- 仅 UI 与现有状态投影变更，不涉及数据库、迁移、音色文件内容、配置写入或新异步任务。参考 [raw/changes/2026-11-03-voice-assets-polish](delivery-voice.md#doc-5f445f7abfb4d8)。


#### 联系人语音配置核对

[raw/changes/2026-11-04-contact-index-tts](index-tts.md#doc-cdb6f65d88730c)：新增会话授权控件与原接口消费，源码位置已核对；后端契约保持。


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。


#### 策略保存复核（2026-11-05）

ContactDialog 新增未安装技能的可见勾选项和保存中提示；IndexTTS 会话授权、网页预设和音色绑定协议不变。联系人策略的锁等待修复及严格目录校验见 [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)。来源 [raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)。


#### 群聊采集与自动语音复核（2026-11-05）

自动回复的 webui 默认推导、实时语音策略、流式缓冲、daemon 合成及录音前准确预设复核见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)；旧媒体包/离线提供者合同保留。自动 webui 的录音前失败终结并仅回退一次文字，不让 blocked 重试重复投递，无数据库迁移。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。

#### 本次核对

会话弹窗保留语音回复模式、本地音色资产、变更才写入以及会话改名复制资产逻辑。 来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 本次核对

新增知识事实写端点，音色资产路由和契约沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 小潮日记接入核对

复核共享路由表，音色目录、预览及绑定继续使用原处理器。 来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。
<!-- end-migrated-part: doc-d265cc1e47a521 -->

<a id="doc-070a8b5f81ad00"></a>

### 自动回复网页语音

来源：`llm wiki/wxbot/concepts/automatic-voice-reply.md:1`。

```yaml
type: concept
module: delivery
summary: 自动回复使用网页预设全文合成，流式缓冲、后台准备与录音前复核
coverage: core
last_verified: '2026-11-07'
sources:
- path: src/butler/delivery/automatic_tts.py
  line: 33
  anchor: 'class AutomaticReplyTts:'
- path: src/wxbot/voice/policy.py
  line: 30
  anchor: def resolve_tts_provider(section)
- path: src/wxbot/voice/policy.py
  line: 301
  anchor: 'class VoicePolicyReloader:'
- path: src/wxbot/voice/tts.py
  line: 250
  anchor: 'class WebUiTtsSource:'
- path: src/wxbot/queue_worker.py
  line: 46
  anchor: 'def process_once(self):'
- path: src/wxbot/delivery_handlers/voice.py
  line: 112
  anchor: 'def _prepare_voice_in_background(self, delivery, policy):'
- path: src/wxbot/delivery_handlers/voice.py
  line: 198
  anchor: 'def before_enter(self, active, audio=None):'
changes:
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-07-delivery-handlers
depends_on:
- modules/delivery
- modules/wxbot
```
### 自动回复网页语音

#### 提供者与授权来源

voice.resolve_tts_provider：显式 provider 优先；仅显式 fixture_wav 的旧配置仍视为 fixture；二者都未配置时使用 webui。fixture 是测试路径，忽略正文播放固定 WAV；webui 使用既有 IndexTTS 网页，不启动第二份模型。管理台 VoiceAdmin.bindings 复用同一推导函数，避免显示值与实际运行值不同。

自动语音由管理员开启 voice.enabled、会话 replace/coexist 及精确会话音色绑定授权；不是模型工具能力。webui 的参考音来自该会话默认网页预设，不额外要求本地音色资产；离线 indextts/显式 fixture 继续遵循原绑定规则。见 [concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)。

#### 配置与数据血缘

VoicePolicyReloader 从实际 _config_path 限量读取配置，只取 voice；按文件签名缓存，后续模型批次和录音前复核。更新无效/不可读时关闭本次语音，不沿用旧授权。默认预设文件由 Butler preset_bindings_path 按当前安装 config.butler.toml 的 agent.data_dir 或 BUTLER_CONFIG 定位，不加载其他安装、数据库或认证内容。

ModelWorker 在输出增量之前快照模式；replace/coexist 使用缓冲模式收齐正文，避免 streamed 分支绕过 voice_mode。finish_batch_parts 的模式、media_path 及 outbox.kind=voice 合同不变；无迁移。语音准备前的配置变化不会重放模型请求。

#### 后台合成与队列

Butler AutomaticReplyTts 只负责精确预设选择、按句合成、标准 16kHz 单声道 PCM16，返回字节；不写工具 operations、不主动投递、不 mint 能力。wxbot WebUiTtsSource 是 prepare(text,contact) 薄适配器；不调用含主动投递副作用的 TTSService.generate，因此不双入队。

VoiceDeliveryHandler 以单个 daemon Future 准备 WebUI 音频，准备期间 active 为空，不占微信窗口或 UI；同一待发条目不重复认领。完成后检查该行仍有效、当前开关/模式/绑定，才选择会话与录音。若 tick 恢复了录音任务，MainInbox 本轮不得继续选择其他待收会话。close 后晚到结果不录音，不阻塞进程退出。

旧的自动 fixture media_path 在当前 webui 模式下重新后台合成，不能绕过新提供者再次播放测试提示音；显式鉴权媒体包不受此替换影响。生成时使用的预设身份随音频保存，录音开始前和按键前再次核对准确预设与提供者；改变或清除绑定不继续使用旧声音。

#### 失败及限制

自动 webui 在按下录音键前失败时，该语音条终结为 skipped 并保留错误；replace 单次回退文字，coexist 保留已发送文字，不让 generic blocked 自动重试再合成/重复回退。已开始录音后的不确定结果仍 uncertain，不自动重录；显式包原有停止语义保留。详见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)。

自动路径仍有单条语音时长上限，超长明确失败回退而不截断；显式 tts_generate 的多条分段包不变。外部 Butler 只有远端预设、本地不可读时保守回文字。WebUI 需要已运行；新代码由使用者自行重启 wxbot 加载，之后语音设置用于后续请求。

#### 测试与来源

tests/butler/test_automatic_voice_reply.py 覆盖默认推导、精确预设/PCM、streaming replace/coexist、策略重读、准备期间继续采集、旧 fixture 缓存、关闭后晚到结果及失败不重试。管理台投影回归验证不改写配置。真实本机 WebUI 仅合成验证返回合规 PCM，不作为微信送达证明。

来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。


#### 发件职责拆分（2026-11-07）

统一调度见 [symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca)，文字、图片、语音、表情的准备和确认见 [symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c)。outbox 字段、语音授权、重试及流式契约保持原状，无迁移。

来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。
<!-- end-migrated-part: doc-070a8b5f81ad00 -->

<a id="doc-7159ca2e34cdf0"></a>

### 音色资产绑定与出站门控

来源：`llm wiki/wxbot/concepts/voice-asset-binding.md:1`。

```yaml
type: concept
module: wxbot
summary: 自动回复语音须绑定；授权网页预设音频包独立提供参考音
coverage: core
last_verified: '2026-11-07'
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
  line: 63
  anchor: media = resolve_queued_media_path(policy)
- path: src/wxbot/delivery_handlers/voice.py
  line: 44
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
- raw/changes/2026-11-07-delivery-handlers
depends_on:
- modules/wxbot
```
### 音色资产绑定与出站门控

#### 规则

1. 语音出站仍要求全局 `voice.enabled` 且联系人 mode ∈ {replace, coexist}（FEAT-VOICE-001）。
2. **自动回复与旧主动推送**额外要求可用绑定：webui 使用精确会话的默认网页预设；离线 indextts/显式 fixture 使用 contact_refs 上有效 `asset_id` 或可解析的 `ref_wav`。
3. 上述自动路径无绑定 → 只回文字；不调用 TTS、不走 RALT；即使 mode 为 replace/coexist。
4. 改绑/清绑 **不** 自动改 mode；清绑 **不** 把 mode 置 off。
5. 失败回退仍按 FEAT-VOICE-001 真值表，本概念不重开。
6. 入队 `outbox.media_path`：仅 `tts_provider=fixture` 写入 `fixture_wav`。`indextts` 以及其他投递时才合成的提供者留空，`VoiceDeliveryHandler._prepare_voice_audio` 因此调用 `source.prepare`，而不是 `load_wav_file`。无可用绑定时仍不入语音条。
7. [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) 是显式授权例外：网页预设已经提供参考音，完整生成后以带 package_id/media_id 的 WAV 包入队，media_path 来自鉴权缓存；不检查管理台绑定、不再次合成，仍要求 voice.enabled 与联系人 mode。原第 6 条仅适用于原自动路径。此例外由 [raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a) 追加，不改写旧 raw。

#### 相关

- [modules/wxbot](wxbot.md#doc-8508032cbe5131) [apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521) [symbols/voice-asset-store](delivery-voice.md#doc-a41b10d5400ad9) [symbols/model-worker](queue-worker.md#doc-0183b6974519f0) [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf)
- 变更：[raw/changes/2026-11-03-indextts-enqueue-media](index-tts.md#doc-29fc2d893f2889)、[raw/changes/2026-11-03-feat-voice-003-voice-assets](delivery-voice.md#doc-a855357d83ac5d)


#### 群聊采集与自动语音复核（2026-11-05）

自动语音的真实 WebUI 默认、配置热读、streaming 缓冲、daemon 合成和录音前准确预设复核见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)；当前面板与会话选择前的越屏恢复见 [concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66)。保持未知发送方快照与原模型权限/重试合同，不改数据库或外部 API。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。


#### 发件职责拆分（2026-11-07）

统一调度见 [symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca)，文字、图片、语音、表情的准备和确认见 [symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c)。outbox 字段、语音授权、重试及流式契约保持原状，无迁移。

来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。
<!-- end-migrated-part: doc-7159ca2e34cdf0 -->

<a id="doc-a41b10d5400ad9"></a>

### VoiceAssetStore

来源：`llm wiki/wxbot/symbols/voice-asset-store.md:1`。

```yaml
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
```
### VoiceAssetStore

本地目录（默认 data/voice-assets/）保存参考 WAV + manifest。约束：仅 WAV、≤2MiB、时长 0.5–60s。供 policy 物化 sset_id→路径，及管理台注册/改名/删除/预览。

#### 相关

- [concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0) [apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521) [modules/wxbot](wxbot.md#doc-8508032cbe5131)
- 变更：[raw/changes/2026-11-03-feat-voice-003-voice-assets](delivery-voice.md#doc-a855357d83ac5d)
<!-- end-migrated-part: doc-a41b10d5400ad9 -->

<a id="doc-153f05bdd2f77f"></a>

### 虚拟麦 + Right Alt 语音条操作说明（FEAT-VOICE-001 P1）

来源：`tools/voice-ptt-ops.md:1`。

### 虚拟麦 + Right Alt 语音条操作说明（FEAT-VOICE-001 P1）

#### 目标路径

打开目标会话（复用现网发文字校准路径）→ 微信麦克风选中虚拟麦录音端 → 播放假音频到虚拟麦播放端 → **长按 Right Alt** → 松手后聊天出现语音条。

本单**不**依赖默认 UIA 可读会话列表/消息气泡来验条；自动化以 PTT 完成作为发送确认，**人工确认**聊天里出现语音条。

#### 本机组件（仓外）

详见 `D:\work\tools\virtual-mic\INSTALL-NOTES-zh.md`（安装物不进 git）。

| 角色 | 设备名 |
|---|---|
| 播放端（向环回灌音） | CABLE Input（VB-Audio Virtual Cable） |
| 微信麦克风（采集） | CABLE Output（VB-Audio Virtual Cable） |

#### 微信选麦

1. 微信 → 设置 → 设备 / 音频
2. 麦克风选择 **CABLE Output**
3. 不要选本机真实麦克风，避免环境噪声

#### 配置开关（AC-10：仅配置文件，无管理台 UI）

在 `config.wxbot.toml`：

```toml
[voice]
enabled = true
fixture_wav = "tools/voice-fixtures/p1-tone.wav"
playback_device = "CABLE Input"
hold_padding_seconds = 0.3
min_seconds = 0.4
max_seconds = 60

# 白名单：仅列出的联系人/群会话名生效；未列出 = off
[voice.contacts]
"示例联系人" = "replace"   # off | replace | coexist
"示例群" = "coexist"
```

真值表：

| mode | 成功 | 失败 |
|---|---|---|
| off | 现网纯文字 | 同现网 |
| replace | 只发语音条，不另发正文 | 回退发一次文字 |
| coexist | 先文字分句，再语音条 | 文字不因语音失败重发 |

#### Right Alt

- 键码：`uiautomation.SpecialKeyNames['RALT'] == 165`
- 动作：`PressKey` 保持 → 音频播放 → `ReleaseKey`
- **不得**擅自改成其它快捷键

#### 主动推送（可选）

`POST /send` 增加可选字段 `"voice": true`（需同时有 `text` 作失败回退）。旧客户端不传该字段则行为不变。

Butler `push_to_wxbot(..., voice=True)` 透传。

#### 卸载虚拟麦

见仓外 `INSTALL-NOTES-zh.md`：管理员运行 VB-Cable Setup 卸载并重启，微信麦改回原设备。

#### TTS 输入合同（P1）

- WAV / PCM / mono / 16-bit / 16000 或 48000 Hz
- 时长默认 0.4–60 秒
- 文件路径或 bytes；同步 `prepare`
- 非法输入：不按 RALT，走文字回退
- P2 IndexTTS 另单接入同一合同

#### P2 IndexTTS

见 `tools/indextts-ops.md`。配置 `voice.tts_provider = "indextts"`；排障可改回 `fixture`。本单不改开会话/RALT/虚拟麦路径。
<!-- end-migrated-part: doc-153f05bdd2f77f -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [群聊采集与自动语音回复影响分析](#doc-b194f18a38699d) · `llm wiki/wxbot/impacts/2026-11-05-group-and-auto-voice.md`
- [FEAT-VOICE-001 连带锚点刷新](#doc-d313df34d8cc8b) · `llm wiki/wxbot/raw/changes/2026-11-03-feat-voice-001-anchor-refresh.md`
- [FEAT-VOICE-001 P1 虚拟麦语音条（可插 TTS / Right Alt）](#doc-3b7c8dcbc01ec2) · `llm wiki/wxbot/raw/changes/2026-11-03-feat-voice-001-virtual-mic.md`
- [FEAT-VOICE-003 连带复核 model-worker 锚点](#doc-2f6dcdc8d592e1) · `llm wiki/wxbot/raw/changes/2026-11-03-feat-voice-003-model-worker-drift.md`
- [FEAT-VOICE-003 音色资产与会话绑定](#doc-a855357d83ac5d) · `llm wiki/wxbot/raw/changes/2026-11-03-feat-voice-003-voice-assets.md`
- [音色资产页布局与状态打磨](#doc-5f445f7abfb4d8) · `llm wiki/wxbot/raw/changes/2026-11-03-voice-assets-polish.md`
- [修复群聊越屏采集与自动语音回复链路](#doc-264d648c9acbbe) · `llm wiki/wxbot/raw/changes/2026-11-05-group-auto-voice.md`

<a id="doc-b194f18a38699d"></a>

### 群聊采集与自动语音回复影响分析

来源：`llm wiki/wxbot/impacts/2026-11-05-group-and-auto-voice.md:1`。

### 群聊采集与自动语音回复影响分析

#### 目标与基线

修复群聊窗口越屏导致发送方无法识别、私聊语音配置未用于自动回复、群聊播放固定测试音频。
主工作树 D:/work/code/wxbot，codex/index-tts-skill，HEAD a1f40c38e120376f992d69628f0e8aec308f1d76；保留所有已有未提交工作。

#### 已核对链路与候选原因

- ChatWindow.side_scores（src/wxbot/wechat/chat_window.py:94）采最外三列为左右背景，窄黑边可触发 gutter_mismatch，_classify 标成 system；MainInbox._capture/read_bundle 对无法确认的发送方保留快照并 ReadDeferred。
- 历史日志右坐标在屏幕边缘附近，但当前窗口已处于另一位置；不能只凭旧坐标断言越屏。必须以只读实时几何/像素诊断区分边框与遮挡，不放宽宽范围遮挡判据。
- ModelWorker（src/wxbot/queue_worker.py:112-170）流式私聊有 streamed 前缀时跳过非流式语音入队分支；模式 replace/coexist 应先缓冲完整回复，再按语音策略入队。
- VoicePolicy（src/wxbot/voice/policy.py:21、:106、:215）默认 fixture，queued_media_path 写固定测试 WAV；FixtureTtsSource.prepare 忽略正文，是固定提示音的原因。
- MainInbox（src/wxbot/inbox.py:79-99）仅启动时加载语音策略，保存后的新模式/绑定无法应用到后续回复。
- 网页默认音色绑定由 Butler PresetBindings 持有，GradioTtsClient 已复用运行中的 WebUI。自动链路目前不读该绑定；TTSService.generate 含主动投递，不能在自动回复中直接复用，否则会双入队。

#### 修改范围与契约

- ChatWindow 仅修改方向像素证据处理；不猜发送方、不吞 ReadDeferred、不推进无法确认的快照，合成图测试覆盖真正遮挡。
- 新 Butler delivery 自动合成服务只返回标准 WAV，不写工具 operations、不主动投递、不伪造服务能力；薄适配器接现有 TtsSource.prepare(text,contact)。
- 新增 webui provider：未显式配置 provider 和 fixture_wav 时使用真实 WebUI，显式 fixture/旧 fixture_wav 保持测试兼容。按精确会话绑定读取预设，不猜声音，不启动第二份模型。
- Worker 在流式输出之前快照语音策略，语音模式先缓冲完整文字；保留 finish_batch_parts 的 voice_mode/media_path 入队合同。
- 从实际配置路径只热读 voice 设置，后续批次使用新策略，录音前复核总开关与会话模式；读失败保守停止语音，不把旧权限当成新授权。
- 预期涉及 voice/policy.py、voice/tts.py、queue_worker.py、inbox.py、delivery.py、新 Butler delivery 模块及对应临时数据测试。无需修改前端布局、角色、提醒、外部模型或消息协议。

#### 数据血缘与副作用

语音设置仍来自本安装配置，网页默认预设仍由 Butler 持有。模型回复正文 → 合成 → 已有 outbox.kind=voice/media_path → 虚拟麦/PTT；无新表/字段或迁移。
只对原已开启自动语音的会话生效，不新增模型工具权限。原 replace 失败单次文字回退和 coexist 不重发文字规则保留；已开始录音的不确定结果不自动重录。
不修改运行配置或生产队列，不重启服务，不发送真实测试消息。截图/实际消息/认证内容仅用于本地诊断，禁止进入本图谱。

#### 验证计划与风险

先用离线合成图和临时队列复现，再验证群聊窄边框/宽遮挡/裁剪、流式 replace/coexist、默认 provider 迁移、精确网页预设、配置重载及录音前关闭。
运行相关测试与完整离线 pytest、compileall、diff 检查。上轮全量有安装技能数量、两项队列状态、输入节奏四项失败，须区分而非静默忽略。
真实 UI 正常几何的诊断不代替历史截图；WebUI 不在线/预设缺失按原失败策略明确回退。长音频仍受既有单条时长合同约束。
回滚本次源码即可，无迁移；加载新代码仍需使用者自行重启 wxbot，自动合成服务为本地库复用既有 WebUI。


#### 最终结论与验证

只读实时几何证实历史右边界2047超出当前1920屏幕，当前入屏后原方向算法正常；未放宽gutter判据，改为采集/选择前恢复可见区域。

自动语音采用本安装网页预设，daemon合成不占UI，精确预设/提供者在录音前再核对；失败单次回退，录音开始后仍不自动重试。独立复核提出的预设重绑与同tick切换竞态已修，最后无重要遗留项。

最终完整测试1540项：1536过、4项与上轮相同的失败；相关测试和本机仅生成校验已通过。详细失败名称/限制见 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。源码编译和diff检查通过。无需为本次纯后端修改重建前端。未改生产数据、未发测试微信、未重启服务。
<!-- end-migrated-part: doc-b194f18a38699d -->

<a id="doc-d313df34d8cc8b"></a>

### FEAT-VOICE-001 连带锚点刷新

来源：`llm wiki/wxbot/raw/changes/2026-11-03-feat-voice-001-anchor-refresh.md:1`。

```yaml
type: change
title: FEAT-VOICE-001 连带锚点刷新
pages:
- symbols/model-worker
- symbols/queue-finish
- symbols/queue-store
- concepts/group-identity-evidence
- concepts/identity-authority
- concepts/model-error-contract
- concepts/unread-capture-retry
- tables/queue-batches
- tables/queue-inbox
- symbols/mention-selection
supersedes: []
```
### FEAT-VOICE-001 连带锚点刷新

#### 目标与背景

`finish_batch_parts` / inbox / chat_window / push 行号位移后，刷新未列入主变更 `pages` 的词条 `sources.line`，消除 source-drift / page-drift。语义仍以主记录 [raw/changes/2026-11-03-feat-voice-001-virtual-mic](delivery-voice.md#doc-3b7c8dcbc01ec2) 为准。

#### 文件与代码位置

仅图谱词条 frontmatter `sources.line`；无业务代码。

#### 接口与字段

不涉及。

#### 数据库与迁移

不涉及。

#### 前端消费点

不涉及。

#### 测试与异步任务

`wiki.py ingest` + `lint`。

#### 风险与回滚

低；回滚本记录即可。
<!-- end-migrated-part: doc-d313df34d8cc8b -->

<a id="doc-3b7c8dcbc01ec2"></a>

### FEAT-VOICE-001 P1 虚拟麦语音条（可插 TTS / Right Alt）

来源：`llm wiki/wxbot/raw/changes/2026-11-03-feat-voice-001-virtual-mic.md:1`。

```yaml
type: change
title: FEAT-VOICE-001 P1 虚拟麦语音条（可插 TTS / Right Alt）
pages:
- modules/wxbot
- modules/delivery
- concepts/delivery-state
- tables/queue-outbox
- concepts/message-pipeline
```
### FEAT-VOICE-001 P1 虚拟麦语音条（可插 TTS / Right Alt）

#### 目标与背景

白名单会话按开关以微信语音条回复。P1 打通「虚拟麦 → 长按 Right Alt」投递，可插 TTS 仅假音频验收；开会话复用现网文字校准路径，不把默认 UIA 可读气泡当作前置。IndexTTS / 管理台音色另单。

#### 文件与代码位置

- `src/wxbot/voice/`：`policy.py` 配置白名单与 mode；`tts.py` WAV 合同；`playback.py` 定向 WaveOut（CABLE Input）
- `src/wxbot/wechat/voice.py` + `chat_window.start_voice`：聚焦输入区后 RALT PTT 会话
- `src/wxbot/delivery.py`：`kind=voice` 发送/确认（`confirm_evidence=ptt_release`，人工验条）；replace 失败回退文字
- `src/wxbot/queue_store.py`：`finish_batch_parts(voice_mode=...)`、`enqueue_voice`
- `src/wxbot/queue_worker.py` / `inbox.py`：注入 VoicePolicy
- `src/wxbot/outbound.py`：`/send` 可选 `voice:true`；旧客户端兼容
- `src/butler/delivery/push.py`：`push_to_wxbot(..., voice=False)`
- `tools/voice-ptt-ops.md`、`tools/voice-fixtures/p1-tone.wav`

#### 接口与字段

- Outbox `kind` 新增 `voice`（表字段已有，无迁移）
- `/send` body 可选 `voice: true`；需保留 `text` 作失败回退
- 配置 `[voice]` / `[voice.contacts]`：`off|replace|coexist`（AC-10 仅配置文件）

#### 数据库与迁移

不涉及新表/新列；复用 `outbox.kind` 与 `media_path`。

#### 前端消费点

无管理台 UI 变更（AC-10）。

#### 测试与异步任务

- 离线：WAV 合同校验、VoicePolicy、`finish_batch_parts` replace/coexist/off、`enqueue_voice`/`claim_delivery`
- WaveOut 对本机 `CABLE Input` 播放冒烟
- 真机语音条：**待人工确认**（不对真人默认狂发；确认不依赖语音气泡 UIA）
- 文本/图文 bundle：未改 image/emoji 路径；`voice=false`/缺省保持原 `/send`

#### 风险与回滚

- 微信主窗内容树仍可能空：验条靠 PTT 完成 + 人工
- 流式 typing 路径未挂 voice_mode（仅完整 `finish_batch_parts`）
- 需微信麦克风选 CABLE Output；虚拟麦仓外安装
- 回滚：还原本变更文件并关 `[voice].enabled`
<!-- end-migrated-part: doc-3b7c8dcbc01ec2 -->

<a id="doc-2f6dcdc8d592e1"></a>

### FEAT-VOICE-003 连带复核 model-worker 锚点

来源：`llm wiki/wxbot/raw/changes/2026-11-03-feat-voice-003-model-worker-drift.md:1`。

```yaml
type: change
title: FEAT-VOICE-003 连带复核 model-worker 锚点
pages:
  - symbols/model-worker
```
### FEAT-VOICE-003 连带复核 model-worker 锚点

#### 目标与背景

queue_worker.py 在 FEAT-VOICE-003 中增加绑定门控后，[symbols/model-worker](queue-worker.md#doc-0183b6974519f0) 来源摘要漂移；复核并刷新锚点行号，不改变符号语义。

#### 文件与代码位置

- src/wxbot/queue_worker.py：语音绑定门控（既有 003 改动）；本记录只复核 wiki 锚点
- llm wiki/wxbot/symbols/model-worker.md：更新 sources 行号与 changes

#### 接口与字段

不涉及。

#### 数据库与迁移

不涉及。

#### 前端消费点

不涉及。

#### 测试与异步任务

不涉及；wiki.py lint 清除本词条 source-drift。

#### 风险与回滚

无运行时风险；回滚删除本 raw 与词条 changes 项即可。
<!-- end-migrated-part: doc-2f6dcdc8d592e1 -->

<a id="doc-a855357d83ac5d"></a>

### FEAT-VOICE-003 音色资产与会话绑定

来源：`llm wiki/wxbot/raw/changes/2026-11-03-feat-voice-003-voice-assets.md:1`。

```yaml
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
```
### FEAT-VOICE-003 音色资产与会话绑定

#### 目标与背景

管理台提供音色资产 CRUD（上传/注册参考 WAV、列表、改名、删除、试听已注册参考音），并把资产绑定到联系人/会话（含群）的 oice.contact_refs.<key>.asset_id。无可用绑定（无有效 asset_id 且无解析得到的 ref）时即使 oice.contacts 为 replace/coexist 也只回文字、不合成、不走 RALT。绑定与模式正交：改绑/清绑不自动改 mode。UI 禁止「训练」「微调」；试听只播放已注册参考 WAV，不触发 IndexTTS 试合成。独立 Tab「音色」；绑定 UI 挂在现有会话设置「回复音色」。

#### 文件与代码位置

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

#### 接口与字段

- GET /api/voice-assets → {ok, assets[], assets_dir, limits{max_bytes, formats, preview}}
- GET /api/voice-assets/preview?id= → 注册参考 WAV 二进制（非 IndexTTS）
- POST /api/voice-assets + X-Wxbot-Voice-Action: register|rename|delete|…（body 可含 base64 WAV）
- GET /api/voice-bindings → {enabled, modes, contacts, contact_refs, assets}
- POST /api/voice-assets action 保存绑定：{contact, mode, asset_id}；清 sset_id 不改 mode；改 mode 不改绑定
- 配置：oice.contact_refs.<contact>.asset_id；oice.assets_dir 可选

#### 数据库与迁移

不涉及。资产落本地目录 data/voice-assets/（gitignored）+ manifest JSON；绑定写入 config.wxbot.toml。

#### 前端消费点

- 导航 TABS 增加「音色」；App.vue 注册 VoiceAssetsView；外部接入模式随业务页隐藏
- 联系人/会话对话框与语音模式同区展示「回复音色」select/clear（含群）
- 文案不含「训练」「微调」；Hallmark --scope app 对新增页 0 FAIL

#### 测试与异步任务

- 
pm.cmd --prefix web run build / smoke：含音色导航与资产页渲染
- 本地 Python 自测：register/rename/bind/preview/delete + delivery_mode_for 无绑定→文字
- 不重启服务；真机微信发测另授（AC-12 范围外）

#### 风险与回滚

- 绑定缺失时静默文字：符合产品；运维需在管理台显式绑定
- 预览仅参考音，不能验证 IndexTTS 音色相似度（AC 明确）
- 回滚：还原本分支；删除 data/voice-assets 不影响文本通路；清 contact_refs 即可停合成
<!-- end-migrated-part: doc-a855357d83ac5d -->

<a id="doc-5f445f7abfb4d8"></a>

### 音色资产页布局与状态打磨

来源：`llm wiki/wxbot/raw/changes/2026-11-03-voice-assets-polish.md:1`。

```yaml
type: change
title: 音色资产页布局与状态打磨
pages:
- modules/web
- apis/dashboard-voice-assets
```
### 音色资产页布局与状态打磨

#### 目标与背景

用户指定运行中的 `/app/?tab=voice-assets`。核对页面静态产物与源码后确认运行树为 `D:/work/code/wxbot-dev`，分支 `codex/grok-setup`，基线 `1e75ab4f2386709d53d26fbab0a9fd46b5b43323`，改前工作树干净。入口聊天目录是另一个较早的工作树，未把两个版本拼接。项目授权默认 Hallmark polish，保留既有深色系统与说明/上传/清单顺序。

根因是共享 `main` 双栏网格和窄屏 `body.list-open main` 把只有一个 section 的音色页压入侧栏轨道，专用样式又引用未定义的颜色令牌。共享 header 的样式也污染页内说明区。

#### 文件与代码位置

- `web/src/views/VoiceAssetsView.vue:229`：原生文件/名称输入关联标签，读取状态、空态、失败态、按钮忙碌反馈及窄屏字段标签。
- `web/src/views/VoiceAssetsView.vue:45`：资产/绑定都成功读取才更新共享刷新时间。
- `web/src/styles/voice-assets.css:7`：限定当前页的一栏布局、共享 header 重置、现有主题令牌、44px 控件命中区、可见焦点、响应式清单和 reduced-motion。
- `web/dist/`：匹配上述源码的 Vite 产物。
- `llm wiki/wxbot/modules/web.md`、`apis/dashboard-voice-assets.md`、`coverage.md`：补齐页面布局/状态与既有字段血缘。原页已登记 App.vue/router.js/main.js，无新注册项。

#### 接口与字段

不涉及 API/DTO 增删。列表仍读取 `/api/voice-assets`、`/api/voice-bindings`；资产字段来自 VoiceAdmin.list_assets / VoiceAsset.as_dict，绑定列由 contact_refs 中的 asset_id 反查。保留 register/rename/delete 请求体、预览路径、请求头、删除确认与处理器。仅成功读取后使用已有 markRefreshed 回调。

说明文案从“注册参考音（zero-shot），供会话绑定后合成；试听播放已注册参考 WAV，不触发 IndexTTS。”改为“添加参考音后，可在联系人设置中绑定会话。试听仅播放参考 WAV，不进行语音合成。”；限制从“上限 X MiB · 格式 WAV”改为“WAV 格式 / 最大 X MiB”。“上传一段本人授权的参考 WAV 后即可绑定到会话。”原文保留。

#### 数据库与迁移

不涉及数据库、表、迁移、配置格式或音色存储格式。本轮无真实音色注册、删除、绑定或微信发送。

#### 前端消费点

仅 VoiceAssetsView 与专用 CSS；App.vue 页面注册、router.js 导航、ContactDialog 绑定消费均不变。CSS 通过 `.voice-assets` 限定，未改共享 theme.css 或其它页面。

#### 测试与异步任务

- `npm.cmd --prefix web run build`、`npm.cmd --prefix web run smoke`。
- 临时浏览器回归：四状态（加载/空/失败/有数据）× 六宽度（320/375/768/1280/1440/1920）× 两侧栏偏好，共 48 项；检查清单宽度、横向溢出、控件裁剪、错误/加载不误报空态、读取成功时间及键盘焦点。全部 API 在浏览器内拦截为假响应，禁止 POST；没有真实业务写入。脚本和截图为本次会话临时产物，不作为跨安装证据。
- Hallmark sloplint 针对两个修改源文件以 app scope 检查，并用真实 `/app/?tab=voice-assets` 渲染。页内已知焦点/边框 FAIL 修复；共享壳原有 10px 导航文字（75）与“消息监控”标题 4.29:1 对比度（40）仍属界外问题，未扩展修改。Vue 动态短按钮文案的 49 警告按实际 nowrap/浏览器布局复核为误报。
- 没有新增异步任务或定时器。读取仍并行、保留旧请求序号防护。

#### 风险与回滚

低风险纯前端变更；表格窄屏仅改变呈现，DOM 保留表头与 scope。回滚这两个源文件并恢复匹配 dist 即可，不需迁移或服务重启。未验证真实音频播放/音色写入，原处理逻辑保留。

图谱 lint 原有 `pending-change: raw/changes/2026-11-03-feat-voice-002-indextts` 尚未入库，未擅自替它完成语义审核。机械 lint 不证明所有语义正确。
<!-- end-migrated-part: doc-5f445f7abfb4d8 -->

<a id="doc-264d648c9acbbe"></a>

### 修复群聊越屏采集与自动语音回复链路

来源：`llm wiki/wxbot/raw/changes/2026-11-05-group-auto-voice.md:1`。

```yaml
type: change
title: 修复群聊越屏采集与自动语音回复链路
pages:
- modules/delivery
- modules/wiki
- modules/wxbot
- apis/dashboard-voice-assets
- apis/index-tts
- symbols/mention-selection
- symbols/model-worker
- tables/queue-outbox
- concepts/automatic-voice-reply
- concepts/capture-viewport
- concepts/delivery-state
- concepts/development-baseline
- concepts/group-identity-evidence
- concepts/message-pipeline
- concepts/model-error-contract
- concepts/unread-capture-retry
- concepts/voice-asset-binding
```
### 修复群聊越屏采集与自动语音回复链路

#### 目标与背景

修复群聊无法采集/回复、私聊语音模式仍发文字、群聊播放固定提示音。已证实历史消息区越出真实监视器导致截图补黑；当前窗口入屏后原方向算法正常。自动语音另有隐式 fixture、启动快照不更新、streaming 绕过语音三条原因。见 [impacts/2026-11-05-group-and-auto-voice](delivery-voice.md#doc-b194f18a38699d)、[concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66)、[concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)。

#### 文件与代码位置

新增 wechat/viewport.py 联合几何/工作区恢复；chat_window.py 截图前拒绝 row_offscreen 并恢复当前面板，main_window.py 选择前恢复。新增 Butler delivery/automatic_tts.py 精确预设/规范 PCM 服务；voice/policy.py 新 provider 与热读，voice/tts.py 薄适配及音频预设身份；queue_worker.py 在流式前快照语音并缓冲；inbox.py 注入 loader 及录音恢复后 UI 互斥；delivery.py daemon 合成、绑定复核、旧 fixture 缓存重合成及失败终结。dashboard/voice_admin.py 显示有效 provider，README 更新说明。准确位置见各关联页 sources/anchors；保留原有未提交修改。

#### 接口与字段

无外部 API/DTO 变更。保持 finish_batch_parts 的 voice_mode/media_path 和 outbox.kind=voice。内部 TtsAudio 新增默认 source_preset，AutomaticReplyTts.synthesize 新增可选 expected_preset，旧调用兼容。生成前后、start_voice 和 before_enter 复核准确预设/提供者。自动服务只合成，不主动投递、不 mint 工具能力或写 operations。

#### 数据库与迁移

无表/字段/迁移。配置热读只取本安装 wxbot 文件的 voice；网页绑定仍由 Butler 的本安装数据目录持有。旧自动 fixture 媒体在当前 webui 下重合成，显式媒体包不变。自动 webui 在录音前失败终结 skipped 并保留错误，replace 单次文字回退、coexist 不重复文字；录音后的 uncertain 仍不重播。未改生产队列或权限配置。

#### 前端消费点

未改 web/ 源码或构建产物，本次不涉及前端设计/构建。GET /api/voice-bindings 的 tts_provider 复用有效 provider 推导，字段/schema 不变。角色和声音选择保持管理员的已保存值。

#### 测试与异步任务

TDD 红绿覆盖越屏截图/同文缓存/窗口恢复、provider 默认、streaming 语音、热读、异步等待、准确预设变更、同 tick 录音切换及失败不重试。群聊相关39项、语音相关50项通过，另2项本机fakeHTTP传输通过。最终全量1540项：1536通过、4失败、无errors/skips。失败与上轮相同：test_portable_install.py::test_plugin_references_and_protocol_are_self_contained；test_queue_admin.py::test_multipart_cli_sent_and_retry_preserve_other_parts；test_queue_store.py::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker；test_typing.py::test_typing_steps_keep_half_second_between_batches_and_one_final_enter。compileall/diff检查通过。独立复核发现的预设身份/录音切换竞态已修并复查。真实本机WebUI仅生成验证返回16kHz单声道PCM16、6.42秒音频，不是送达证明。新增daemon Future后台准备，不占active UI，不重复认领，close后不采用晚到结果。测试用临时库/假投递/合成像素，未触碰真实剪贴板或发测试微信。

#### 风险与回滚

无法恢复窗口或监视器信息不可用时仍安全暂缓；不放宽gutter、不猜发送方。自动语音受单条时长上限，超长/WebUI离线/本地预设缺失按模式回退，不截断或猜声音。外部Butler的远端绑定不会由新增endpoint读取。新代码需使用者手动重启wxbot；现有WebUI继续复用，无第二份模型。之后语音配置用于后续批次和录音前复核。不自动重启、不改角色/音色/运行配置、不发真实测试消息。回滚本次源码/README，无迁移。保留两个原有2026-11-03待入库记录，不机械代替其语义核对。
<!-- end-migrated-part: doc-264d648c9acbbe -->
