---
type: api
module: delivery
summary: 授权文字与网页音色预设生成分段语音，经虚拟麦和 RALT 投递当前会话
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/delivery/tts_presets.py
  line: 12
  anchor: 'class PresetBindings:'
- path: src/dashboard/api/tts_presets.py
  line: 6
  anchor: 'def _known_contact(ctx, contact):'
- path: web/src/components/ContactDialog.vue
  line: 156
  anchor: async function loadTtsCatalogue()
- path: web/src/views/ContactsView.vue
  line: 152
  anchor: function openConversation(conversation)
- path: web/src/styles/contacts.css
  line: 28
  anchor: '#contact-index-tts input:disabled'
- path: plugins/butler-wechat/skills/tools/index-tts/SKILL.md
  line: 2
  anchor: 'name: index-tts'
- path: src/butler/agent/tools.py
  line: 127
  anchor: 'if name in (''tts_presets'', ''tts_generate''):'
- path: src/butler/agent/core.py
  line: 109
  anchor: self.tools.tts_service = TTSService(
- path: src/butler/backends/codex.py
  line: 120
  anchor: '''tool_timeout_sec'':max(30, int(self.cfg.codex_timeout))'
- path: src/butler/delivery/gradio_tts.py
  line: 15
  anchor: 'class GradioTtsClient:'
- path: src/butler/delivery/tts.py
  line: 51
  anchor: 'class TTSService:'
- path: src/butler/delivery/push.py
  line: 80
  anchor: def queue_voice_to_wxbot(
- path: src/butler/server.py
  line: 102
  anchor: 'if path.path.startswith(''/v1/audio/''):'
- path: src/common/media_bundle.py
  line: 40
  anchor: def validate_voice_items(
- path: src/common/voice_audio.py
  line: 79
  anchor: def prepare_voice_parts(
- path: src/wxbot/outbound.py
  line: 232
  anchor: 'if self.path == ''/send-voice-bundle'':'
- path: src/wxbot/queue_store.py
  line: 489
  anchor: def enqueue_voice_package(
- path: src/wxbot/delivery.py
  line: 250
  anchor: def _prepare_voice_audio(
- path: src/wxbot/wechat/chat_window.py
  line: 468
  anchor: def start_voice(
- path: src/wxbot/wechat/voice.py
  line: 17
  anchor: 'class VoiceSession:'
- path: src/wxbot/voice/playback.py
  line: 116
  anchor: 'def prepare(self) -> None:'
changes:
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-policy-save
- raw/changes/2026-11-05-group-auto-voice
depends_on:
- modules/delivery
- modules/plugin
- modules/wxbot
- modules/common
- concepts/identity-authority
---
# IndexTTS 网页预设与微信语音包

## 方法、路径与鉴权

运行时工具 `tts_presets()` / `tts_generate(text, preset?)` 必须通过 [[concepts/identity-authority]] 的能力校验及 `index-tts` 技能白名单。只读能力仅查询预设（包括当前会话 default_preset）。目标固定为上下文 contact，模型不能传身份、地址或路径；生成结束重新 verify，撤权或过期不入队。所属 [[modules/plugin]]、[[modules/delivery]]。

Butler `GET /v1/audio/<32位小写十六进制ID>` 使用既有服务 Bearer Token，返回 audio/wav、no-store；不存在 404、无效 ID/文件 400。wxbot 下载拒绝重定向、代理，大小限 2MiB 并复验 WAV。

wxbot `POST /send-voice-bundle` 仅主窗口队列模式，必须配置且匹配 X-Wxbot-Token。body 精确为 contact/items/request_id；items 是 1-50 个 `{kind: voice, media_id}`。原 `/send-bundle` text/image 契约保持不变。

## 生成与默认参数

`text` 为非空、最多 6000 字，`preset` 为准确名称、最多 256 字，可省略。显式名称优先，省略/空串时从服务端当前会话绑定解析；无绑定或失效预设失败，不猜测替代。幂等指纹以原始请求参数固定，已登记操作先返回，不因默认预设更改/清除而重放。客户端固定本机 HTTP WebUI，默认 127.0.0.1:7860，使用无系统代理的 requests Session。用独立线程会话的 Gradio queue/join、queue/data 调用刷新预设、加载参考音和 gen_single；单次简单 call API 的独立会话不能保留下拉选项更新。

从 /info 读取所有生成参数默认值，用 /config 的组件 ID 映射加载结果；只覆盖 prompt 和 text。Gradio 把空的可选 emo_ref_path 标作必填时，核对对应 Audio 组件确实为空才传 None。预设中保存的高级设置不传入生成。原始音频仅允许当前服务的 gradio_api/file 地址，拒绝跨源/重定向和超过 64MiB。

按句拆分文字，每片最多 160 字；音频转 16kHz 单声道 PCM16，超过 55 秒时寻找邻近低能量窗口切分，完整保留 PCM 帧；不足 0.4 秒拒绝。整包上限 50 条，全部准备成功才提交，不部分生成就发送。

## 响应字段与错误语义

工具结果含 status、operation_id，成功准备后含 parts。generating 表示已认领处理中；queued 表示 UI 线程数据库事务提交后收到匹配 contact/request_id 的回执；failed 表示校验、生成、授权或明确拒绝；delivery_unknown 表示提交/回执不确定，不能自动重发。

HTTP 入队在全部下载校验后交 UI 线程，等持久化确认最多 20 秒；超时返回 delivery_unknown，即使稍后可能入库也不能重发。工具调用不等多条语音全部播放，避免分钟级录音阻塞 MCP 回执。Codex tool_timeout_sec 随 codex.timeout，外层 CallDeadline 仍是总预算，能力 TTL 沿用总预算+60；后台未授权完成不能投递。

## 实现链与数据血缘

Skill → ToolService → TTSService → GradioTtsClient → AudioStore → queue_voice_to_wxbot → wxbot HTTP/BundleMediaCache → DeliveryPump.enqueue → QueueStore.enqueue_voice_package → VoiceSession/WaveOutPlayer。

operations 原表按 owner/request/call_id 固定指纹，先登记再释放事务进行 HTTP；同内容的别名 call_id 也登记指纹，完成状态同步整组别名。请求处理未知或进程中断不重新生成/投递。文件保存在 data/audio/<owner SHA256>/<opaque ID>.wav，路径不进入模型参数。

复用 delivery_packages 和 [[tables/queue-outbox]] 的 kind/media_id/media_path/package_id/part_seq，无新表、无迁移。顺序/包中断沿用已有队列规则。仍检查 voice.enabled 和联系人的 replace/coexist；网页预设已经提供参考音，故本路径不要求管理台绑定、不再次合成，不走新闻订阅授权。原自动语音绑定规则见 [[concepts/voice-asset-binding]]。

PTT 先打开并准备 CABLE Input，再按 RALT，等 250ms 后播放，录音由 CABLE Output 输入。准备失败不按键；录音期间目标变化、探测/播放异常会释放键并进入 uncertain，停止整包，不自动重录或文字回退。拒绝用户草稿/不可读输入框。正常结束仍是 ptt_release 证据，不宣称对方收听；状态见 [[concepts/delivery-state]]。播放错误清理使用可重入锁防死锁。

## 前端消费点

联系人基本资料中的会话配置 `ContactDialog.vue` 增加 indexTtsEnabled 授权开关；ContactsView.openConversation 使用 effectivePolicy 传递当前生效策略，明确不继承时保持 null。GET /api/skills 校验可用技能；未配置角色/技能不可用时不能改授权，失败可原位重试。策略未变不创建覆盖；改变时复制角色、其他技能和心跳，只增删 index-tts，沿现有 /api/contacts 的版本与确认头保存，由 ContactAdmin 服务端再次校验。

语音模式仍用 /api/voice-bindings 和 /api/voice-assets action=bind；只改 mode 不提交 asset_id，避免清掉旧 ref_wav。重命名必须将当前 mode/asset_id 写到新会话名，沿原行为保留旧键。加载未完成禁止保存，失败不写默认语音值。联系人写成功但语音写失败时显示部分保存，保持弹窗，用联系人响应的新 version 重试，成功才关闭。现有允许功能列表也保留 IndexTTS 入口。

同区现已增加「网页音色预设」下拉与刷新，明确区分自动回复音色资产。读取失败保留已绑定值、显示错误；未改不写，重命名复制给新名称，部分保存失败单独说明预设未完成。提交前固定目标/选择，并按联系人响应中稳定会话 ID 找规范化名称，所有后续保存使用该名称；保存期间禁用输入，延迟响应时也不能串到其他联系人。新控件使用现有令牌与表单样式；构建产物 web/dist 随源码发布。现有队列只读投影不变。补充与局部更正来源 [[raw/changes/2026-11-04-webui-preset-binding]]。

## 网页预设管理端契约

GET /api/tts-presets?contact=... 返回 ok/presets[]/preset/version/available/error。version 为配置内容的 SHA256 修订值；网页不可达仍返回原 preset/version，available=false 且不伪造可选项。POST /api/tts-presets 精确接收 contact/preset/version，需同源 X-Wxbot-TTS-Action，且纳入本地 BUSINESS 门。服务端用 ContactStore 完整 conversations 校验存在，含停用会话；非统一安装才用既有配置联系人。空 preset 清除绑定，非空值先查询网页；未知目标/预设 400，缺确认 403，修订冲突 409，存储 I/O 失败 503。

PresetBindings 由 Butler 持有，dashboard 仅 HTTP 适配。存储为本安装 Butler data_dir/tts-presets.json，文件 version=1 是格式版本，presets 为会话名到预设名的映射；API version 是整个内容的修订哈希。配置锁内复查版本、合并映射、临时文件 fsync 后 replace，返回本次提交值/修订；网页网络调用不持锁。不新增数据库表，不复制预设音频/高级参数。加载本次新接口/默认解析需使用者自行重启管理台和 Butler。

## 测试与风险

本地 tests/butler/test_index_tts_skill.py、test_tts_transport.py、test_tts_ptt.py 覆盖默认设置、授权、去重/别名、断流、不自动重发、格式、分段保帧、顺序、持久化、按键先于播放及异常释放。Skill 基线模拟误用预设高级设置，加入说明后纠正。真实短文本生成和经 HTTP/缓存/持久队列/PTT 实发已验证，并在目标窗口观察到新语音气泡；真实用户数据不进入本页。

服务/语音配置需使用者自行启动或重启；WebUI 未运行、权限不足、语音关闭、无 CABLE 或请求总预算耗尽均不承诺投递。回滚本次代码/技能即可停用新工具，不删历史数据。

## 修改来源

[[raw/changes/2026-11-04-index-tts-skill]]，源码路径/稳定锚点见本页 sources。


图谱契约说明来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]。


## 策略保存复核（2026-11-05）

ContactDialog 新增未安装技能的可见勾选项和保存中提示；IndexTTS 会话授权、网页预设和音色绑定协议不变。联系人策略的锁等待修复及严格目录校验见 [[apis/dashboard-contact-policy]]。来源 [[raw/changes/2026-11-05-contact-policy-save]]。


## 群聊采集与自动语音复核（2026-11-05）

自动回复的 webui 默认推导、实时语音策略、流式缓冲、daemon 合成及录音前准确预设复核见 [[concepts/automatic-voice-reply]]；旧媒体包/离线提供者合同保留。自动 webui 的录音前失败终结并仅回退一次文字，不让 blocked 重试重复投递，无数据库迁移。来源 [[raw/changes/2026-11-05-group-auto-voice]]。
