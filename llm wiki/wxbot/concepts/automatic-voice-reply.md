---
type: concept
module: delivery
summary: 自动回复使用网页预设全文合成，流式缓冲、后台准备与录音前复核
coverage: core
last_verified: '2026-11-05'
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
- path: src/wxbot/delivery.py
  line: 283
  anchor: 'def _prepare_voice_in_background(self, delivery, policy):'
- path: src/wxbot/delivery.py
  line: 495
  anchor: def _prepare_voice_enter(self, active,
changes:
- raw/changes/2026-11-05-group-auto-voice
depends_on:
- modules/delivery
- modules/wxbot
---
# 自动回复网页语音

## 提供者与授权来源

voice.resolve_tts_provider：显式 provider 优先；仅显式 fixture_wav 的旧配置仍视为 fixture；二者都未配置时使用 webui。fixture 是测试路径，忽略正文播放固定 WAV；webui 使用既有 IndexTTS 网页，不启动第二份模型。管理台 VoiceAdmin.bindings 复用同一推导函数，避免显示值与实际运行值不同。

自动语音由管理员开启 voice.enabled、会话 replace/coexist 及精确会话音色绑定授权；不是模型工具能力。webui 的参考音来自该会话默认网页预设，不额外要求本地音色资产；离线 indextts/显式 fixture 继续遵循原绑定规则。见 [[concepts/voice-asset-binding]]、[[apis/index-tts]]、[[apis/dashboard-voice-assets]]。

## 配置与数据血缘

VoicePolicyReloader 从实际 _config_path 限量读取配置，只取 voice；按文件签名缓存，后续模型批次和录音前复核。更新无效/不可读时关闭本次语音，不沿用旧授权。默认预设文件由 Butler preset_bindings_path 按当前安装 config.butler.toml 的 agent.data_dir 或 BUTLER_CONFIG 定位，不加载其他安装、数据库或认证内容。

ModelWorker 在输出增量之前快照模式；replace/coexist 使用缓冲模式收齐正文，避免 streamed 分支绕过 voice_mode。finish_batch_parts 的模式、media_path 及 outbox.kind=voice 合同不变；无迁移。语音准备前的配置变化不会重放模型请求。

## 后台合成与队列

Butler AutomaticReplyTts 只负责精确预设选择、按句合成、标准 16kHz 单声道 PCM16，返回字节；不写工具 operations、不主动投递、不 mint 能力。wxbot WebUiTtsSource 是 prepare(text,contact) 薄适配器；不调用含主动投递副作用的 TTSService.generate，因此不双入队。

DeliveryPump 以单个 daemon Future 准备 WebUI 音频，准备期间 active 为空，不占微信窗口或 UI；同一待发条目不重复认领。完成后检查该行仍有效、当前开关/模式/绑定，才选择会话与录音。若 tick 恢复了录音任务，MainInbox 本轮不得继续选择其他待收会话。close 后晚到结果不录音，不阻塞进程退出。

旧的自动 fixture media_path 在当前 webui 模式下重新后台合成，不能绕过新提供者再次播放测试提示音；显式鉴权媒体包不受此替换影响。生成时使用的预设身份随音频保存，录音开始前和按键前再次核对准确预设与提供者；改变或清除绑定不继续使用旧声音。

## 失败及限制

自动 webui 在按下录音键前失败时，该语音条终结为 skipped 并保留错误；replace 单次回退文字，coexist 保留已发送文字，不让 generic blocked 自动重试再合成/重复回退。已开始录音后的不确定结果仍 uncertain，不自动重录；显式包原有停止语义保留。详见 [[concepts/delivery-state]]、[[tables/queue-outbox]]。

自动路径仍有单条语音时长上限，超长明确失败回退而不截断；显式 tts_generate 的多条分段包不变。外部 Butler 只有远端预设、本地不可读时保守回文字。WebUI 需要已运行；新代码由使用者自行重启 wxbot 加载，之后语音设置用于后续请求。

## 测试与来源

tests/butler/test_automatic_voice_reply.py 覆盖默认推导、精确预设/PCM、streaming replace/coexist、策略重读、准备期间继续采集、旧 fixture 缓存、关闭后晚到结果及失败不重试。管理台投影回归验证不改写配置。真实本机 WebUI 仅合成验证返回合规 PCM，不作为微信送达证明。

来源 [[raw/changes/2026-11-05-group-auto-voice]]。
