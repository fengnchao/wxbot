# IndexTTS

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### IndexTTS

图中的位置表示规划：将文字合成为音频后再交给语音发件队列。

第一步的实际自动语音路径仍是 outbox → VoiceDeliveryHandler → TTS 适配器 → 微信 PTT。
WebUI 合成在后台线程完成，期间不占微信窗口；合成结束及按录音键前复核当前语音授权。
显式 Butler tts_generate 语音包保持先生成、再入队的现有路径。

## 使用说明

- [wxbot / Butler / 微信 UI 与队列 / IndexTTS 网页预设转微信语音](#doc-037c8e3925abd7) · `README.md`

<a id="doc-037c8e3925abd7"></a>

### wxbot / Butler / 微信 UI 与队列 / IndexTTS 网页预设转微信语音

来源：`README.md:726`。

##### IndexTTS 网页预设转微信语音

在联系人「AI 设置」的允许功能中启用 IndexTTS，由使用者启动本机 IndexTTS 网页（`http://127.0.0.1:7860`）、Butler 和 wxbot。
工具 `tts_presets()` 列出网页实时保存的预设及当前会话的 `default_preset`；`tts_generate(text, preset?)` 只接收文字和可选预设名，
目标固定为当前授权会话。只使用预设的参考音频，其余语言、语速、情感和采样设置采用网页默认值。
显式预设优先；省略时使用联系人绑定，未绑定则提示选择，不自动挑第一种声音。默认值改变或清除后，重复调用仍复用原操作，不会按新绑定重发。

管理台后端的 `GET /api/tts-presets?contact=...` 读实时列表和保存值，`POST /api/tts-presets`
用原确认机制及 `X-Wxbot-TTS-Action` 保存 `{contact,preset,version}`。服务端核对完整联系人记录（含停用会话）、
网页预设及修订哈希；冲突要求刷新后重选。仅预设名称写入 Butler `data_dir/tts-presets.json`，不复制预设音频或高级参数。
网页断开时可读取旧绑定，清除默认不要求网页在线。会话弹窗已移除预设管理入口，旧绑定继续按原窗口名读取。改名后，如需继续使用旧默认音色，可通过该接口为新窗口名绑定。

文字一次提交，最多 6000 字。服务按句拆分，音频统一为 16kHz 单声道 PCM16，并在需要时按静音位置切分，
每条最长 55 秒、整包最多 50 条。Butler 的 `data/audio/<owner-hash>/` 保存生成文件，wxbot 通过鉴权编号下载到本机缓存，
按序进入既有虚拟麦与 Right Alt 长按发送链路。播放设备是 `CABLE Input`，微信录音设备应为 `CABLE Output`。

仍须开启 `[voice].enabled`，并将 `[voice.contacts]` 中目标会话设为 `replace` 或 `coexist`；
这个工具使用网页预设的参考音，不要求另绑管理台音色资产。自动回复使用 `webui` 提供者时同样按会话绑定的网页预设朗读正文；离线 `indextts` 路径仍须绑定管理台音色资产。
使用 `fixture` 提供者时沿用既有可用 fixture 文件要求。技能不修改系统麦克风设置，也不启动第二份模型。

`queued` 只代表已生成并持久化排队；不能当作微信送达回执。生成后会重新验证授权，
重复调用复用同一操作，结果未知不自动重发。语音包一条失败即停止余下部分；录音已开始后的异常记 `uncertain`，
需人工核对，不自动再次按键。Codex MCP 工具时限随 `codex.timeout`，整轮仍受模型请求总预算约束。
未显式设置 `voice.tts_provider` 和 `voice.fixture_wav` 时，自动回复默认复用本机 IndexTTS 网页（`webui`），不再播放测试提示音。显式 `fixture` 或旧 `fixture_wav` 配置仍保留测试用途；显式 `indextts` 沿用离线 worker。默认网页预设必须按会话绑定，不自动猜声音。自动路径只支持本安装可读取的预设绑定，外部 Butler 的远端绑定不可用时回退文字。

语音总开关、会话模式与绑定在后续批次和录音前重新读取；语音模式下先收齐模型正文，再后台合成，等待合成期间继续收件。自动回复仍受单条语音时长上限约束，超长或合成失败按原模式回退，不截断正文。显式 `tts_generate` 的多条分段包不变。

微信窗口越出实际监视器范围时，选择会话或采集当前面板前会尝试恢复到可见工作区；已完整可见的窗口保持原位置。无法恢复时保留快照并暂缓，不能根据屏外补黑猜发送方。

加载本次新代码需使用者手动重启 wxbot；现有 IndexTTS 网页继续复用，不自动启动第二份模型。仅新增的自动语音服务为 wxbot 导入的 Butler 库，不要求为此重启 Butler。
<!-- end-migrated-part: doc-037c8e3925abd7 -->

## 技术资料

- [IndexTTS 网页预设与微信语音包](#doc-fdc576d6ee7fbd) · `llm wiki/wxbot/apis/index-tts.md`
- [IndexTTS 安装与接入（FEAT-VOICE-002 · 仓外）](#doc-5606dd82f2b492) · `tools/indextts-ops.md`

<a id="doc-fdc576d6ee7fbd"></a>

### IndexTTS 网页预设与微信语音包

来源：`llm wiki/wxbot/apis/index-tts.md:1`。

```yaml
type: api
module: delivery
summary: 授权文字与网页音色预设生成分段语音，经虚拟麦和 RALT 投递当前会话
coverage: core
last_verified: '2026-11-07'
sources:
- path: src/butler/delivery/tts_presets.py
  line: 12
  anchor: 'class PresetBindings:'
- path: src/dashboard/api/tts_presets.py
  line: 6
  anchor: 'def _known_contact(ctx, contact):'
- path: web/src/components/ContactDialog.vue
  line: 268
  anchor: function submitPolicy()
- path: web/src/views/ContactsView.vue
  line: 153
  anchor: function openConversation(conversation)
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
  line: 104
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
- path: src/wxbot/delivery_handlers/voice.py
  line: 79
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
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-05-enable-group-binding
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
- raw/changes/2026-11-07-delivery-handlers
depends_on:
- modules/delivery
- modules/plugin
- modules/wxbot
- modules/common
- concepts/identity-authority
```
### IndexTTS 网页预设与微信语音包

#### 方法、路径与鉴权

运行时工具 `tts_presets()` / `tts_generate(text, preset?)` 必须通过 [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37) 的能力校验及 `index-tts` 技能白名单。只读能力仅查询预设（包括当前会话 default_preset）。目标固定为上下文 contact，模型不能传身份、地址或路径；生成结束重新 verify，撤权或过期不入队。所属 [modules/plugin](resident-skills.md#doc-709338d3e083eb)、[modules/delivery](butler-functions.md#doc-f61f55fe09c5e9)。

Butler `GET /v1/audio/<32位小写十六进制ID>` 使用既有服务 Bearer Token，返回 audio/wav、no-store；不存在 404、无效 ID/文件 400。wxbot 下载拒绝重定向、代理，大小限 2MiB 并复验 WAV。

wxbot `POST /send-voice-bundle` 仅主窗口队列模式，必须配置且匹配 X-Wxbot-Token。body 精确为 contact/items/request_id；items 是 1-50 个 `{kind: voice, media_id}`。原 `/send-bundle` text/image 契约保持不变。

#### 生成与默认参数

`text` 为非空、最多 6000 字，`preset` 为准确名称、最多 256 字，可省略。显式名称优先，省略/空串时从服务端当前会话绑定解析；无绑定或失效预设失败，不猜测替代。幂等指纹以原始请求参数固定，已登记操作先返回，不因默认预设更改/清除而重放。客户端固定本机 HTTP WebUI，默认 127.0.0.1:7860，使用无系统代理的 requests Session。用独立线程会话的 Gradio queue/join、queue/data 调用刷新预设、加载参考音和 gen_single；单次简单 call API 的独立会话不能保留下拉选项更新。

从 /info 读取所有生成参数默认值，用 /config 的组件 ID 映射加载结果；只覆盖 prompt 和 text。Gradio 把空的可选 emo_ref_path 标作必填时，核对对应 Audio 组件确实为空才传 None。预设中保存的高级设置不传入生成。原始音频仅允许当前服务的 gradio_api/file 地址，拒绝跨源/重定向和超过 64MiB。

按句拆分文字，每片最多 160 字；音频转 16kHz 单声道 PCM16，超过 55 秒时寻找邻近低能量窗口切分，完整保留 PCM 帧；不足 0.4 秒拒绝。整包上限 50 条，全部准备成功才提交，不部分生成就发送。

#### 响应字段与错误语义

工具结果含 status、operation_id，成功准备后含 parts。generating 表示已认领处理中；queued 表示 UI 线程数据库事务提交后收到匹配 contact/request_id 的回执；failed 表示校验、生成、授权或明确拒绝；delivery_unknown 表示提交/回执不确定，不能自动重发。

HTTP 入队在全部下载校验后交 UI 线程，等持久化确认最多 20 秒；超时返回 delivery_unknown，即使稍后可能入库也不能重发。工具调用不等多条语音全部播放，避免分钟级录音阻塞 MCP 回执。Codex tool_timeout_sec 随 codex.timeout，外层 CallDeadline 仍是总预算，能力 TTL 沿用总预算+60；后台未授权完成不能投递。

#### 实现链与数据血缘

Skill → ToolService → TTSService → GradioTtsClient → AudioStore → queue_voice_to_wxbot → wxbot HTTP/BundleMediaCache → DeliveryPump.enqueue → QueueStore.enqueue_voice_package → VoiceSession/WaveOutPlayer。

operations 原表按 owner/request/call_id 固定指纹，先登记再释放事务进行 HTTP；同内容的别名 call_id 也登记指纹，完成状态同步整组别名。请求处理未知或进程中断不重新生成/投递。文件保存在 data/audio/<owner SHA256>/<opaque ID>.wav，路径不进入模型参数。

复用 delivery_packages 和 [tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf) 的 kind/media_id/media_path/package_id/part_seq，无新表、无迁移。顺序/包中断沿用已有队列规则。仍检查 voice.enabled 和联系人的 replace/coexist；网页预设已经提供参考音，故本路径不要求管理台绑定、不再次合成，不走新闻订阅授权。原自动语音绑定规则见 [concepts/voice-asset-binding](delivery-voice.md#doc-7159ca2e34cdf0)。

PTT 先打开并准备 CABLE Input，再按 RALT，等 250ms 后播放，录音由 CABLE Output 输入。准备失败不按键；录音期间目标变化、探测/播放异常会释放键并进入 uncertain，停止整包，不自动重录或文字回退。拒绝用户草稿/不可读输入框。正常结束仍是 ptt_release 证据，不宣称对方收听；状态见 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)。播放错误清理使用可重入锁防死锁。

#### 前端消费点

会话「编辑窗口与收发设置」已移除 IndexTTS 专区及其读写请求。IndexTTS 授权统一由「AI 设置」提交现有联系人策略，详见 [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)。旧网页预设由运行时按窗口名读取；会话改名时页面不再复制预设。来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

群身份启用只推进绑定和联系人版本，未改变此处的授权或语音配置路径。来源 [raw/changes/2026-11-05-enable-group-binding](identity-tools.md#doc-6f2fac571f1610)。

本地语音模式和资产仍用 /api/voice-bindings 和 /api/voice-assets action=bind。只改 mode 不提交 asset_id；重命名时沿用按新窗口名复制本地语音设置。保存期间冻结选择，按联系人响应中的稳定会话 ID 查找目标，部分失败时用新 version 重试。见 [apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521)。

#### 网页预设管理端契约

GET /api/tts-presets?contact=... 返回 ok/presets[]/preset/version/available/error。version 为配置内容的 SHA256 修订值；网页不可达仍返回原 preset/version，available=false 且不伪造可选项。POST /api/tts-presets 精确接收 contact/preset/version，需同源 X-Wxbot-TTS-Action，且纳入本地 BUSINESS 门。服务端用 ContactStore 完整 conversations 校验存在，含停用会话；非统一安装才用既有配置联系人。空 preset 清除绑定，非空值先查询网页；未知目标/预设 400，缺确认 403，修订冲突 409，存储 I/O 失败 503。

PresetBindings 由 Butler 持有，dashboard 仅 HTTP 适配。存储为本安装 Butler data_dir/tts-presets.json，文件 version=1 是格式版本，presets 为会话名到预设名的映射；API version 是整个内容的修订哈希。配置锁内复查版本、合并映射、临时文件 fsync 后 replace，返回本次提交值/修订；网页网络调用不持锁。不新增数据库表，不复制预设音频/高级参数。加载本次新接口/默认解析需使用者自行重启管理台和 Butler。

#### 测试与风险

本地 tests/butler/test_index_tts_skill.py、test_tts_transport.py、test_tts_ptt.py 覆盖默认设置、授权、去重/别名、断流、不自动重发、格式、分段保帧、顺序、持久化、按键先于播放及异常释放。Skill 基线模拟误用预设高级设置，加入说明后纠正。真实短文本生成和经 HTTP/缓存/持久队列/PTT 实发已验证，并在目标窗口观察到新语音气泡；真实用户数据不进入本页。

服务/语音配置需使用者自行启动或重启；WebUI 未运行、权限不足、语音关闭、无 CABLE 或请求总预算耗尽均不承诺投递。回滚本次代码/技能即可停用新工具，不删历史数据。

#### 修改来源

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)，源码路径/稳定锚点见本页 sources。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。


#### 策略保存复核（2026-11-05）

ContactDialog 新增未安装技能的可见勾选项和保存中提示；IndexTTS 会话授权、网页预设和音色绑定协议不变。联系人策略的锁等待修复及严格目录校验见 [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)。来源 [raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)。


#### 群聊采集与自动语音复核（2026-11-05）

自动回复的 webui 默认推导、实时语音策略、流式缓冲、daemon 合成及录音前准确预设复核见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)；旧媒体包/离线提供者合同保留。自动 webui 的录音前失败终结并仅回退一次文字，不让 blocked 重试重复投递，无数据库迁移。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。

#### 本次核对

新事实删除端点与语音媒体端点独立，媒体与预设契约沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

已对照当前共享源码复核本词条的接口或调用位置。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。


#### 发件职责拆分（2026-11-07）

统一调度见 [symbols/delivery-pump](delivery-pump.md#doc-7ca25975c49fca)，文字、图片、语音、表情的准备和确认见 [symbols/delivery-handlers](delivery-pump.md#doc-9ba04de08ae10c)。outbox 字段、语音授权、重试及流式契约保持原状，无迁移。

来源 [raw/changes/2026-11-07-delivery-handlers](delivery-pump.md#doc-83d2ae6b4c4ac1)。
<!-- end-migrated-part: doc-fdc576d6ee7fbd -->

<a id="doc-5606dd82f2b492"></a>

### IndexTTS 安装与接入（FEAT-VOICE-002 · 仓外）

来源：`tools/indextts-ops.md:1`。

### IndexTTS 安装与接入（FEAT-VOICE-002 · 仓外）

本说明描述沙盒机仓外安装 IndexTTS、权重获取/校验、卸载，以及 wxbot 配置键。
**安装物、权重、参考音一律不进 git。**

#### 禁止未授权克隆

- 参考音必须是**你自有或已获授权**的音色素材。
- **禁止**未授权克隆他人音色用于生产或外发。
- IndexTTS 官方 `examples/` 仅可用于本机工程冒烟（合成+合同校验），不得当作生产音色资产。
- 管理台音色资产绑定属 FEAT-VOICE-003，本单不做 UI。

#### 本机路径（建议）

| 用途 | 路径 |
|---|---|
| IndexTTS 源码+uv 环境 | `D:\work\tools\index-tts\` |
| 权重（IndexTTS-2.5） | `D:\work\tools\index-tts\checkpoints\` |
| 授权参考音（自备） | `D:\work\tools\index-tts\refs\`（自建；不进 git） |
| 合成举证输出（可选） | `D:\work\tools\index-tts\proof\`（自建；不进 git） |

仓库内 worker：`tools/indextts_worker.py`（经 `uv run --directory <repo_dir>` 调用仓外环境）。

#### 安装步骤

1. 需要：Windows、NVIDIA GPU（本沙盒 RTX 4070）、驱动、`uv`、`git`。
2. 克隆（仓外）：

```powershell
New-Item -ItemType Directory -Force D:\work\tools | Out-Null
Set-Location D:\work\tools
git clone https://github.com/index-tts/index-tts.git index-tts
Set-Location .\index-tts
git rev-parse HEAD   # 本沙盒钉扎: d9e41aac89fd00b3d71497fddb287b7f24613712
```

3. 依赖（隔离环境，勿装进 wxbot `.venv`）：

```powershell
# Windows 建议不要 --all-extras（DeepSpeed 难装）
uv sync --extra webui
# 或国内镜像：
# $env:UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple"
# uv sync --extra webui
```

4. 权重（任选其一）：

```powershell
uv tool install "huggingface-hub"
hf download IndexTeam/IndexTTS-2.5 --local-dir=checkpoints
# 或 ModelScope：
# uv tool install modelscope-hub
# modelscope download --model IndexTeam/IndexTTS-2.5 --local_dir checkpoints
```

5. GPU 自检：

```powershell
uv run tools/gpu_check.py
nvidia-smi
```

6. License：阅读仓内 `LICENSE` / `DISCLAIMER`（bilibili Model Use License）。大客户条款见协议 2.2。

#### 卸载 / 回滚

1. wxbot 配置把 `voice.tts_provider` 改回 `"fixture"`（或 `enabled=false`）。
2. 删除仓外目录：`Remove-Item -Recurse -Force D:\work\tools\index-tts`
3. 如用 huggingface 缓存，可另清 `%USERPROFILE%\.cache\huggingface`（按需）。
4. 不改微信选麦 / 虚拟麦；那些属 P1 文档 `tools/voice-ptt-ops.md`。

#### wxbot 配置示例

```toml
[voice]
enabled = true
tts_provider = "indextts"   # 排障可改回 "fixture"
fixture_wav = "tools/voice-fixtures/p1-tone.wav"
playback_device = "CABLE Input"
hold_padding_seconds = 0.3
min_seconds = 0.4
max_seconds = 60

[voice.indextts]
repo_dir = "D:/work/tools/index-tts"
model_dir = "D:/work/tools/index-tts/checkpoints"
cfg_path = "D:/work/tools/index-tts/checkpoints/config.yaml"
uv_bin = "uv"
timeout_seconds = 180
use_cuda = true
use_bf16 = true
sample_rate = 16000
default_ref_wav = ""          # 可选全局参考音；生产请用授权素材
default_lang = "ZH"
worker_script = "tools/indextts_worker.py"

[voice.contacts]
"示例联系人" = "replace"

# 按联系人参考音；asset_id 预留 003，本单不做管理台
[voice.contact_refs."示例联系人"]
ref_wav = "D:/work/tools/index-tts/refs/example-authorized.wav"
asset_id = ""
lang = "ZH"
```

#### 行为真值（相对 P1）

| 条件 | 行为 |
|---|---|
| `tts_provider=fixture` | 忽略正文，播假音频（排障） |
| `indextts` + 有参考音 | 按**正文**合成合同 WAV → 既有投递 |
| `indextts` + 无参考音/无绑定 | **不合成、不按 RALT** → 文字回退 |
| OOM/超时/坏参考音/非合同/进程失败 | ValueError → 文字回退；遵守 replace/coexist |

#### P1 WAV 合同

RIFF PCM mono 16-bit；16k 或 48k；默认 0.4s～60s。非法 → `ValueError`，调用方不得按 RALT。

#### 参考音占位

若尚无授权参考音：在 `D:\work\tools\index-tts\refs\README.txt` 写明「放置自有授权 wav；禁止未授权克隆」。自动化测无参考音回退路径即可。
<!-- end-migrated-part: doc-5606dd82f2b492 -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [联系人配置中的 IndexTTS](#doc-f3a570551cedc3) · `llm wiki/wxbot/impacts/2026-11-04-contact-index-tts.md`
- [Butler IndexTTS 技能设计与影响面](#doc-f72ff421fb5c31) · `llm wiki/wxbot/impacts/2026-11-04-index-tts-skill.md`
- [联系人选择网页音色预设](#doc-b47165c49a3a7a) · `llm wiki/wxbot/impacts/2026-11-04-webui-preset-binding.md`
- [目标 / 背景](#doc-56093eafa42389) · `llm wiki/wxbot/raw/changes/2026-11-03-feat-voice-002-indextts.md`
- [IndexTTS 入队不再写入 P1 假音频路径](#doc-29fc2d893f2889) · `llm wiki/wxbot/raw/changes/2026-11-03-indextts-enqueue-media.md`
- [联系人配置中的 IndexTTS](#doc-cdb6f65d88730c) · `llm wiki/wxbot/raw/changes/2026-11-04-contact-index-tts.md`
- [网页预设文字转语音 Skill](#doc-a62e0514c7634a) · `llm wiki/wxbot/raw/changes/2026-11-04-index-tts-skill.md`
- [网页预设绑定与默认音色](#doc-14cc58d084986d) · `llm wiki/wxbot/raw/changes/2026-11-04-webui-preset-binding.md`
- [网页预设图谱契约说明](#doc-a877b64be56f43) · `llm wiki/wxbot/raw/changes/2026-11-04-webui-preset-graph-note.md`

<a id="doc-f3a570551cedc3"></a>

### 联系人配置中的 IndexTTS

来源：`llm wiki/wxbot/impacts/2026-11-04-contact-index-tts.md:1`。

```yaml
type: impact
status: verified
date: '2026-11-04'
```
### 联系人配置中的 IndexTTS

#### 需求与方案

延续已实现的文字/预设工具，在 Web 联系人的会话设置中提供可见的 IndexTTS 授权开关，和已有语音模式一起配置。保留现有页面布局、角色策略入口、音色资产绑定和所有收发字段。工具调用仍传文字与预设名，不新增联系人默认预设或隐式改变高级生成参数。

#### 文件与调用方

`web/src/components/ContactDialog.vue` 的 conversation 模式增加授权状态/加载错误/重试，复用 /api/skills 验证技能存在；`web/src/views/ContactsView.vue` 的 openConversation 传递已有生效策略，避免误用或覆盖继承策略。web/scripts/smoke.mjs 用实际构建组件验证保存请求与异常状态。样式复用现有表单和 theme.css，按 Hallmark component/app scope 原位修改。

#### 契约与血缘

现有 GET /api/skills、GET /api/voice-bindings、POST /api/contacts（X-Wxbot-Contact-Action）、POST /api/voice-assets bind（X-Wxbot-Voice-Action）保持原 schema。只有开关确实改变才更新该会话 policy.allowed_skills，并保留 role_skill/heartbeat_enabled/其他技能；继承策略转换为明确会话覆盖前给出说明。原语音模式、资产保持正交，网页预设路径不需要资产绑定。读取失败不提交对应默认值，提交成功后才关闭弹窗；多步骤部分失败必须告知已保存范围。

业务验证仍在 ContactAdmin._policy 与服务端技能目录；前端勾选不绕过权限。无新表/列/迁移，无模型后端变更，无自动服务重启，无额外真实消息发送。角色/功能原可在 AI 设置中修改，该入口保留。

#### 实施与验证计划

1. 新增实际 Vue 构建烟测：授权控件存在、保存仅改变 IndexTTS、保留其他字段、未改不写策略。
2. 实现弹窗/入口，验证加载、错误/重试、未配置角色、继承提示，防止未读完就保存。
3. npm build/smoke，Hallmark 指定 Vue 文件静态检查及可用时独立预览渲染；不重启已有服务。
4. 复核与追加 raw，更新关联图谱 source/契约并 ingest/lint。保留工作区此前功能和文档修改。

#### 风险与回滚

联系人策略和语音模式原来分属联系人数据/配置文件，不能声称跨源原子提交；遇到部分失败保持弹窗并说明已保存/待保存，使用刷新后的版本重试，不重复扩大授权。新控件默认不自动开启总语音/联系人模式或新增默认角色。回滚本次前端源与 dist 即移除新入口，已有设置继续由原入口管理。

#### 完成验证

- npm build/smoke 通过，覆盖实际 Vue 的授权保留、未改不写、技能失败重试、部分保存与真正递增的响应版本、继承来源、会话重命名复制语音模式/资产。独立审阅的重命名 P2 先复现失败、修复后闭环。
- Hallmark 静态组件/页面联检无 FAIL/WARN，既有 spacing NOTE 保留。对实际 /app/?tab=contacts 只读假数据预览运行多尺寸渲染并查看截图；新输入/复选框/下拉边缘对比度 5.16-5.80，键盘焦点 2px，375px 弹窗 clientWidth=scrollWidth=333。全页渲染仍有背景旧控件、字号、旧卡片等发现，未扩大修改。
- 新构建保存在 web/dist；未改真实用户设置/设备或自动重启服务，无额外真人消息。图谱记录 [raw/changes/2026-11-04-contact-index-tts](index-tts.md#doc-cdb6f65d88730c) 入库 6 页，lint 仅余本任务前的 4 项旧待办。
<!-- end-migrated-part: doc-f3a570551cedc3 -->

<a id="doc-f72ff421fb5c31"></a>

### Butler IndexTTS 技能设计与影响面

来源：`llm wiki/wxbot/impacts/2026-11-04-index-tts-skill.md:1`。

```yaml
type: impact
status: verified
date: '2026-11-04'
```
### Butler IndexTTS 技能设计与影响面

#### 已确认需求

- 在 `plugins/butler-wechat/skills/tools/index-tts/` 新增技能，供微信中的 Butler 通过授权工具调用。
- 生成工具只接收 `text`（文字）与 `preset`（网页保存的音色预设名称）。
- 使用当前 `http://127.0.0.1:7860` WebUI。选用预设的音色参考音频；语言、语速、情感和采样等其余参数使用 WebUI 公布的默认值。

#### 方案

由 Butler 服务端调用现有 WebUI 的 Gradio API，复用已经加载的模型。另一条路径是另起 IndexTTS Python 进程，但这会重复加载模型且偏离用户指定的网页服务，故本设计采用前者。

新增两个工具：

- `tts_presets()`：读取网页当前已保存的预设名称。
- `tts_generate(text, preset)`：使用指定预设的参考音频生成 WAV，将音频复制到 Butler 数据目录中当前身份所属的子目录，返回成功状态、音频编号和本机 WAV 文件路径。

按用户后续明确要求，生成后通过既有 CABLE Input 播放 / CABLE Output 录音、Right Alt 长按链路发送到当前微信会话。文字按句拆分，生成的音频再保证每条不超过 55 秒，整包按序持久化投递。工具返回 queued 只表示持久化排队，不表示微信气泡已确认。

#### 权限与失败行为

沿用 `ToolService.issue/verify/definitions/call`。管理员须将技能加入对应联系人的允许技能，服务端验证当前身份与技能授权；只读/心跳上下文仅可查询预设。

URL、身份和输出目录由服务端确定，模型不能指定联系人、文件路径或任意远端地址。Gradio 请求仅连接本机并绕过系统代理。

使用现有 `operations` 表的 owner/request_id/call_id/fingerprint/result 记录幂等状态；提交生成前先登记，耗时 HTTP 调用在数据库事务外执行。重复工具调用复用记录；提交后超时或断流不自动再次生成。

未知或空预设、缺少参考音频、网页不可连接、接口不兼容和无效音频均返回明确失败，不能宣称已生成。通过刷新接口读取预设，不把 `/config` 中启动时的下拉快照当作实时预设列表。

#### 文件、调用方与契约

- 新增技能 `plugins/butler-wechat/skills/tools/index-tts/SKILL.md`，声明 `tts_presets/tts_generate`。
- 修改 `src/butler/agent/tools.py` 的工具定义、参数校验与分发，保留已有工具语义。
- 新增 `src/butler/delivery/gradio_tts.py`，负责 Gradio 队列/SSE、默认参数和音频下载。
- 新增 `src/butler/delivery/tts.py`，负责身份归属、幂等状态与生成文件存储。
- 使用 `SkillCatalogue` 现有工具分类、会话白名单与 MCP/原生工具后端，无需新增模型后端或修改 WebUI。
- 配套更新 README 与受影响图谱词条、追加 raw 记录并 ingest/lint。保留主目录原有未提交修订。

源码依据：`src/butler/agent/catalogue.py:8`、`src/butler/agent/tools.py:51`（能力校验）、`:99`（分发）、`src/butler/business.py:44`（operations 表）。实施后以实际位置更新来源。

#### 数据、前端与验证

不新增数据库表或迁移；扩展 operations.result 的本工具状态内容。没有 Vue 页面、字段或交互改动，也不改另一仓库的 WebUI 源码。

补充影响面：`common/media_bundle.py` 新增独立语音包校验（原图文 schema 不变）；`common/voice_audio.py` 做 PCM 转换、重采样和分段；Butler 新增鉴权音频 GET；`wxbot/outbound.py` 增加 `/send-voice-bundle` 和持久化回执；`queue_store.py` 复用 delivery_packages/outbox.kind/media_id/media_path/part_seq；`delivery.py` 用已准备音频绕过参考音绑定和再次合成，仍检查语音全局开关及联系人模式。语音包不走新闻订阅校验，也不在失败后重复发文字。`voice/playback.py` 修复启动错误清理时重入锁死锁，`wechat/voice.py` 确保先按 RALT 再开始灌音，并在播放异常后保守标记不确定。

调用链：Skill → ToolService capability → TTSService（operations 幂等，事务外生成）→ Gradio → AudioStore → wxbot 鉴权 HTTP → 临时队列 → UI 线程持久化语音包 → DeliveryPump → VoiceSession。没有前端 DTO 变动，音频包字段仅 kind/media_id，路径和目标均不由模型提供。新 HTTP 回执等待数据库提交，不等待全部语音播放，避免长文本占满模型请求时限。生成后重新验证能力，过期或撤权不入队；提交结果未知禁止自动重发。

实施顺序与验证：1. 先写并运行失败的客户端、音频、幂等/授权、语音包测试；2. 实现客户端与存储/工具；3. 接入鉴权下载及队列/音频播放，运行相关回归；4. 新增技能并进行无说明/有说明的行为对照；5. 新鲜上下文复核整项变更；6. 按用户指定联系人和文案实机验证；7. 更新图谱并 ingest/lint。保留工作区此前修改，不提交或推送。

执行台账：已创建 codex/index-tts-skill 分支，继续使用用户指定且已统一环境的根工作目录，避免再次建立独立运行安装。无 Skill 基线模拟把“其余默认”误解为继承预设保存的高级设置；新 Skill 明确只取音色参考，其余使用网页默认值。

完成验证：新增功能与既有投递相关 22 项通过；较大范围 Butler/Codex/媒体/队列回归 778 项通过、2 项既有队列策略期望失败。真实 WebUI 已生成用户指定短文，借测试专属 HTTP/缓存/数据库及原 PTT 代码执行一次授权发送，并在目标窗口观察到新语音气泡。测试辅助服务已关闭，已有服务/长期配置未改，未重复发出。新鲜上下文复核的 3 项 P2（UIA 异常释放、MCP 时限、别名幂等）修复后复核通过。Skill 格式与行为对照通过，图谱记录见 [raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)。

先用临时数据库和假 Gradio 服务验证授权、默认参数、动态预设、一次生成、未知结果不重试、超时及文件边界，再做真实服务生成。用户已明确授权完成后按其指定的一个目标、文案和预设做实机发送；不将真实联系人、文案、预设或音频内容写入图谱。

服务由使用者自行重启加载新代码；不自动重启 Butler、wxbot、管理台或 WebUI。回退为撤销本次技能/服务代码和图谱修改，已有配置、业务数据和用户预设保持原状。
<!-- end-migrated-part: doc-f72ff421fb5c31 -->

<a id="doc-b47165c49a3a7a"></a>

### 联系人选择网页音色预设

来源：`llm wiki/wxbot/impacts/2026-11-04-webui-preset-binding.md:1`。

```yaml
type: impact
status: verified
date: '2026-11-04'
```
### 联系人选择网页音色预设

#### 根因与已确认需求

ContactDialog 的 voiceAssets 只读 /api/voice-bindings，后者返回 Butler 本地 VoiceAssetStore；网页已保存的预设由 Gradio.refresh_preset_choices 提供，两者没有连接。上一轮仅新增技能授权，未提供网页预设选择，因此用户已有网页预设仍无法选到。

在现有 IndexTTS 区域新增独立的网页音色预设下拉/刷新，保存为当前会话默认值。自动回复音色资产保留原用途。调用工具省略 preset 时使用绑定，显式 preset 优先；其他设置仍为网页默认。

#### 文件、契约与血缘

- Butler delivery/tts_presets.py 持有按会话保存的预设名、乐观版本及原子配置写入，文件位于本安装 data/tts-presets.json；不复制预设音频或高级参数。TTSService 在服务端身份上下文中解析默认预设，幂等指纹按原请求参数固定，避免重试时绑定变化导致重复发送。
- dashboard/api/tts_presets.py 增加 GET/POST /api/tts-presets，纳入本地 BUSINESS 门；POST 需同源 X-Wxbot-TTS-Action，目标必须是现有联系人，非空预设先对照网页实时列表，版本冲突 409。
- tools.py 仍只有 text/preset，preset 改为可省略（需存在绑定）；只读仍仅列表，不准生成。tts_presets 返回当前会话 default_preset。Skill 明确默认值与显式覆盖。
- ContactDialog 读取并保存 preset/version/contact 快照，未改不写、目录不可达保留旧绑定、重命名复制到新会话、部分保存明确提示；接口故障时不清空默认值。
- 更新 Vue 烟测、web/dist、README 与图谱，无新表/迁移，不改系统设备，不自动重启服务，不额外真人测试发送。

#### 实施与验证

先失败后通过：绑定持久化/版本/隔离、未知预设/网页不可达、默认音色生成与显式覆盖及重复请求；Dashboard 路由/同源确认/未知联系人；构建后的下拉默认值/刷新/保存/部分失败。真实网页只读列预设验证；保持 Hallmark 原位范围，实际路由渲染与新控件检查。最后独立复核与图谱 ingest/lint。

#### 完成验证

构建及全站 Vue 烟测通过，管理台/语音相关 256 项回归通过。独立复核的两项 P2 已通过失败→通过回归闭环：停用目标改读完整会话；等待期间目标/选项变化由提交快照、稳定 ID 返回目标和保存禁用控制。配置提交结果来自锁内版本，不在释放锁后重读。

真实 WebUI 只读查询可列出用户已有预设；实际构建的假数据路由验证了默认选中值、选项来源、桌面/375px 显示、边框对比度 5.16-5.80 和键盘焦点，Hallmark 静态无 FAIL/WARN，全页既有样式发现保留。运行中管理台尚未加载新接口，用户选择稍后自行重启管理台/Butler，未自动重启、未保存真实绑定、未新增真人发送。图谱记录 [raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d) 入库 15 页，lint 剩原有 4 项待办。
<!-- end-migrated-part: doc-b47165c49a3a7a -->

<a id="doc-56093eafa42389"></a>

### 目标 / 背景

来源：`llm wiki/wxbot/raw/changes/2026-11-03-feat-voice-002-indextts.md:1`。

```yaml
title: FEAT-VOICE-002 IndexTTS 可插 TTS 源
date: 2026-11-03
```
#### 目标 / 背景

在 P1 可插 TTS 合同上接入 IndexTTS：按正文合成 RIFF PCM mono 16-bit（16k/48k）WAV，失败或不具备参考音时不按 RALT、回退文字。仓外安装权重；不做 003 UI；不改开会话/虚拟麦/RALT。

#### 文件 / 位置

- `src/wxbot/voice/policy.py`：`tts_provider`、`IndexTtsSettings`、`contact_refs`（含预留 `asset_id`）
- `src/wxbot/voice/tts.py`：`IndexTtsSource`、`build_tts_source`；`FixtureTtsSource.prepare` 保留
- `src/wxbot/voice/__init__.py`：导出
- `src/wxbot/inbox.py` / `src/wxbot/delivery.py`：经 factory 选源；`prepare(..., contact=)`
- `tools/indextts_worker.py`：uv 环境内合成+重采样到合同
- `tools/indextts-ops.md`：安装/校验/卸载；禁止未授权克隆
- `tools/smoke_voice002_tts.py`：本地冒烟

#### API / DTO

- 配置新增 `voice.tts_provider`、`voice.indextts.*`、`voice.contact_refs.*`
- 出站 wire / RALT / 虚拟麦：**无变更**
- TTS `prepare(text, *, data=None, contact="")` 可选 `contact`

#### DB / 迁移

不涉及。

#### 前端消费

不涉及（AC-10 仍配置文件；003 另单）。

#### 测试 / 异步

- `tools/smoke_voice002_tts.py`：fixture、无参考音回退、bytes 注入、policy
- 真机微信发测：另授；P1 人工验仍挂时 AC-09 标阻塞

#### 风险 / 回滚

- IndexTTS 权重与 CUDA 仅本机；OOM/超时回退文字
- 回滚：`tts_provider=fixture` 或还原本分支；仓外目录可删

#### 不适用

管理台音色资产、ASR、云 TTS、推 main/合并。
<!-- end-migrated-part: doc-56093eafa42389 -->

<a id="doc-29fc2d893f2889"></a>

### IndexTTS 入队不再写入 P1 假音频路径

来源：`llm wiki/wxbot/raw/changes/2026-11-03-indextts-enqueue-media.md:1`。

```yaml
type: change
title: IndexTTS 入队不再写入 P1 假音频路径
pages:
  - concepts/delivery-state
  - concepts/message-pipeline
  - concepts/model-error-contract
  - concepts/voice-asset-binding
  - modules/wxbot
  - symbols/model-worker
  - tables/queue-outbox
```
### IndexTTS 入队不再写入 P1 假音频路径

#### 目标与背景

`tts_provider=indextts` 且联系人 mode=replace、有可用 `asset_id` 时，微信仍播放 P1 假音频。原因是模型线程和主动推送入队时无条件把 `policy.fixture_wav` 写入 `outbox.media_path`。`DeliveryPump._prepare_voice_audio` 见非空路径就 `load_wav_file`，不再调用 `build_tts_source` / `IndexTtsSource.prepare`。

修正：只有 `tts_provider=fixture` 写入假音频路径；其它在投递时合成的提供者把 `media_path` 留空。无可用绑定仍只回文字，不合成、不走 RALT。产品默认、管理台和运行中的服务都不改。

#### 文件与代码位置

- `src/wxbot/voice/policy.py:115` `VoicePolicy.queued_media_path`：fixture 返回 `fixture_wav`，否则返回空字符串。
- `src/wxbot/voice/policy.py:126` `resolve_queued_media_path`：有该方法时调用它；旧替身对象仅在 provider 缺省或 fixture 时回退到 `fixture_wav`。
- `src/wxbot/queue_worker.py:166`：`voice_mode != off` 时用上述解析结果作为 `voice_media_path`。绑定门控仍走 `delivery_mode_for`（约 159 行）。
- `src/wxbot/delivery.py:74`：`DeliveryPump.enqueue` 的 `kind=voice` 同样不再无条件写 `fixture_wav`。
- `src/wxbot/delivery.py:183` `_prepare_voice_audio` 未改：空 `media_path` 继续 `source.prepare`，非空继续 `load_wav_file`。
- `tools/smoke_voice_enqueue_media.py`：离线断言入队路径与 prepare 是否被调用。

#### 接口与字段

不涉及新接口。`outbox.media_path` 含义收紧：fixture 语音条仍是假 WAV 路径；indextts 语音条为空，正文仍留在 `text` 供合成和失败回退。`/send` 的 `voice: true` 字段不变。

#### 数据库与迁移

不涉及。不新增列、不改 `queue_schema`。空路径使用已有 `media_path TEXT NOT NULL DEFAULT ''`。

#### 前端消费点

不涉及。管理台不展示或编辑这条路径，页面与 `web/dist` 未改。

#### 测试与异步任务

`PYTHONPATH=src python3 tools/smoke_voice_enqueue_media.py`：indextts 的 replace/coexist/outbound `media_path` 为空且 `prepare` 被调用；fixture 的 `media_path` 为 `p1-tone.wav` 且不调用 `prepare`；无绑定只入文字。`tools/smoke_voice002_tts.py` 仍通过。未做真实微信发送。无新异步任务。

#### 风险与回滚

已入队、`media_path` 已写成假 WAV 的旧语音条仍会播 P1 音调；需要新回复或重新入队才走 IndexTTS。流式 typing 路径本来就不挂 `voice_mode`，本次未改。回滚：还原上述文件，或把 `tts_provider` 设回 `fixture`。
<!-- end-migrated-part: doc-29fc2d893f2889 -->

<a id="doc-cdb6f65d88730c"></a>

### 联系人配置中的 IndexTTS

来源：`llm wiki/wxbot/raw/changes/2026-11-04-contact-index-tts.md:1`。

```yaml
type: change
title: 联系人配置加入 IndexTTS 授权与语音设置联动
pages:
- modules/dashboard
- modules/web
- modules/wiki
- apis/dashboard-voice-assets
- apis/index-tts
- concepts/development-baseline
supersedes:
- raw/changes/2026-11-04-index-tts-skill
```
### 联系人配置中的 IndexTTS

#### 目标与背景

用户要求将已实现的 IndexTTS 能力加入 Web 联系人配置。保留现有管理台布局和原角色/通用技能入口，在会话设置提供明确授权开关，与语音模式同屏。本条只补充并更正 supersedes 记录的“前端不适用”部分；既有生成工具参数/权限/投递协议不变，旧 raw 不改写。

#### 文件与代码位置

- web/src/components/ContactDialog.vue：conversation 模式读取技能目录、显示 indexTtsEnabled 开关；沿当前策略只增删 index-tts；语音读取状态与按变化字段保存，部分保存失败留窗，用返回版本重试。saveVoiceBinding 重命名时复制 mode/asset_id 到新键，未重命名的模式修改不清参考音。
- web/src/views/ContactsView.vue：openConversation 调用现有 effectivePolicy，把当前有效策略传给弹窗，尊重 inherit_person_policy=false。
- web/src/styles/contacts.css：只为本次控件补禁用、边框对比度、提示色与标签宽度，沿既有令牌/焦点样式，不改全站主题。
- web/scripts/smoke.mjs：实际构建 Vue 的授权、继承、失败重试、变化字段、递增版本和重命名回归；web/dist 包含对应构建。
- README.md、关联图谱与影响报告记录使用路径与契约，具体稳定来源见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) sources。

#### 接口与字段

不新增 HTTP 接口或后端字段。使用 GET /api/skills 和 /api/voice-bindings，POST /api/contacts 的原 policy.allowed_skills/role_skill/heartbeat_enabled/version；沿原确认头。只有授权开关变化才发送完整保留后的策略，未变化不建立覆盖。

原 POST /api/voice-assets action=bind 仅发送改变的 mode 或 asset_id，重命名例外复制当前值。读取失败不以默认空值回写；目录不可用/角色未设不允许更改授权。姓名/授权先保存成功而语音保存失败时明确提示部分保存，保留弹窗，使用新 version 重试。跨源操作不宣称原子性。

#### 数据库与迁移

不适用：无新表/列/迁移。仍分别由既有联系人存储及语音 TOML 保存。仍使用服务端校验；没有自动修改真实用户配置、凭证、默认设备或运行数据。

#### 前端消费点

路径为联系人 → 基本资料 → 编辑窗口与收发设置 → IndexTTS 文字转语音。AI 设置的允许功能列表也保留技能并显示中文名称。网页预设音色在聊天调用时指定，不新增联系人默认预设，不改变其他生成默认值。

语音总开关关闭、模式关闭、技能不可用、缺少角色分别显示说明；配置在加载中/保存中禁用相应操作，错误可重试。自动回复音色与网页预设的绑定条件分开说明。

#### 测试与异步任务

先新增 DOM 烟测观察缺少控件失败，再实现。npm build/smoke 通过，覆盖保留其他授权、未改不写、模式不清旧绑定、目录失败重试、部分保存留窗/不重复改策略、真实递增 version、继承策略与会话重命名。独立审阅复现重命名丢绑定 P2，补失败→通过回归后复核闭环，未发现其余 P1/P2。

Hallmark component/app 静态联检新组件与共享样式为 0 FAIL/0 WARN，保留已有 spacing NOTE。独立只读假数据预览使用实际 /app/?tab=contacts 和构建资源，运行 Hallmark 多尺寸渲染并查看截图；新表单边缘对比度/焦点/375px 无横向溢出检查通过。全页渲染仍报告背景旧控件低对比度、旧卡片高度/字号、导航字色/字重等发现，未扩大修整旧页面。没有新增定时/后台业务任务，没有发送新的真实消息。

#### 风险与回滚

授权开关不自动开启语音总开关/联系人模式、不创建默认角色。继承策略变化会保存为会话覆盖，并明确提示。旧语音配置以名字作键，重命名继续复制到新键并保留旧键，后续独立清理不在本次范围。回退本次前端文件与 dist 可移除入口，原 AI/语音配置入口仍可管理已有设置。既有服务不重启；前端刷新加载新构建。
<!-- end-migrated-part: doc-cdb6f65d88730c -->

<a id="doc-a62e0514c7634a"></a>

### 网页预设文字转语音 Skill

来源：`llm wiki/wxbot/raw/changes/2026-11-04-index-tts-skill.md:1`。

```yaml
type: change
title: 网页预设文字转语音 Skill 与分段虚拟麦投递
pages:
- modules/butler
- modules/common
- modules/delivery
- modules/identity
- modules/plugin
- modules/wiki
- modules/wxbot
- apis/butler-handle-stream
- apis/butler-handle
- apis/dashboard-knowledge
- apis/index-tts
- tables/queue-batches
- tables/queue-inbox
- tables/queue-outbox
- symbols/butler-handle
- symbols/butler-result
- symbols/knowledge-auto
- symbols/mention-selection
- symbols/queue-finish
- symbols/queue-store
- concepts/delivery-state
- concepts/development-baseline
- concepts/group-identity-evidence
- concepts/identity-authority
- concepts/message-pipeline
- concepts/model-error-contract
- concepts/unread-capture-retry
- concepts/voice-asset-binding
supersedes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
```
### 网页预设文字转语音 Skill

#### 目标与背景

将本机已有 IndexTTS WebUI 接入微信 Butler，生成仅接收文字与保存的音色预设，其余网页默认；通过既有虚拟麦和 RALT 链路发送，长文本拆成多条。用户明确授权一条指定目标/文案/预设的实机发送，运行数据仅在本机测试产物，不写入图谱。

本条仅更正 supersedes 旧记录中“无绑定一律不走 RALT”的无例外表述：新授权预设包已提供参考音，因此独立于管理台绑定。旧自动回复和旧主动语音的绑定规则、管理台 UI 保持不变。既有未提交修改与两条旧待入库记录不删除、不改写。

#### 文件与代码位置

新技能 plugins/butler-wechat/skills/tools/index-tts/SKILL.md；新业务客户端 src/butler/delivery/gradio_tts.py、存储与幂等 tts.py；tools.py 声明与分发，core.py 注入服务，server.py 提供鉴权音频 GET，push.py 提供持久入队客户端。Codex MCP 工具超时随请求配置，原总预算/能力 TTL 约束保留。

common/media_bundle.py 新增独立语音 schema，voice_audio.py 完成文字/PCM 分段与重采样；wxbot/outbound.py 鉴权下载和持久化回执，queue_store.py 复用包写入；delivery.py 选择已生成音频并使用语音包开关与失败语义。wechat/chat_window.py 拒绝草稿，wechat/voice.py 先录音再播放并保证异常释放，voice/playback.py 分开准备/播放和错误清理可重入锁。具体位置和稳定锚点见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) sources。

同步 README 文件地图/使用方式、关联词条 source 行号与反向导航。对仅因文件内插入产生摘要/行号变化的图谱条目核对 diff，既有 API、身份、队列其他规则无语义变更；保留原 changes。

#### 接口与字段

tts_presets 只读；tts_generate(text<=6000, preset<=256) 通过服务签发能力，不收目标/路径/URL。动态预设共享独立 Gradio 会话，只取参考音；其余 /info 默认值，空可选 Audio 对照 /config 处理。每片文字 160 字，音频 16kHz mono PCM16、0.4-55s、全包<=50。

GET /v1/audio/<id> 使用现有 Bearer；POST /send-voice-bundle 使用现有 X-Wxbot-Token，body contact/items/request_id；items 精确 kind/media_id。queued 仅确认 UI 线程完成持久化，delivery_unknown 不重发，原图文契约保持。

#### 数据库与迁移

无新表/列/迁移。operations 登记幂等指纹、处理中和结果，别名调用编号绑定同一指纹且同步结果；耗时 HTTP 在事务外。delivery_packages/outbox 原字段复用，media_path 仅由鉴权缓存提供。文件按身份散列分区；不提交运行音频/数据库。

#### 前端消费点

无前端源码或交互修改，不适用 Hallmark/build/dist。既有队列投影读取原字段/状态。新技能沿目录发现/联系人允许列表，无 UI 新字段。

#### 测试与异步任务

先失败后通过的测试覆盖生成幂等、别名换参拒绝、权限撤销/只读、网页默认值、同会话队列、下载边界、音频保帧分段、原图文拒绝语音字段、顺序/包中断、持久化回执、RALT 时序/异常释放/草稿拒绝。新鲜上下文审阅发现 3 项 P2，均追加失败→通过回归并复核闭环。

相关 Butler/Codex/媒体/队列回归只出现两项既有队列策略期望失败，未扩展本任务修改其行为；新增相关测试通过。Skill quick_validate 通过，行为对照修正了基线继承高级预设的误读。

真实 WebUI 生成成功；使用测试专属临时 HTTP 端口/令牌/队列/数据完成现有 CABLE/PTT 链路一次发送，并在微信目标聊天核对到新语音气泡。未重启任何已有服务、未改本机长期配置、未自动重发。测试辅助服务结束后关闭。不新增后台调度任务。

#### 风险与回滚

启动/语音配置由使用者加载；本机网页、CABLE、语音总开关/联系人模式、技能白名单任一缺失均不能投递。queued 不是送达/收听。已录音失败 uncertain，余下包停止；操作断流/未知状态不自动重放。撤销本次代码和技能即可回退，不删除已有业务或预设数据。原 raw 记录保持不变，例外门控由本条追加更正。
<!-- end-migrated-part: doc-a62e0514c7634a -->

<a id="doc-14cc58d084986d"></a>

### 网页预设绑定与默认音色

来源：`llm wiki/wxbot/raw/changes/2026-11-04-webui-preset-binding.md:1`。

```yaml
type: change
title: 网页音色预设列表与联系人默认绑定
pages:
- modules/butler
- modules/dashboard
- modules/delivery
- modules/identity
- modules/plugin
- modules/web
- modules/wiki
- apis/dashboard-knowledge
- apis/dashboard-queue
- apis/dashboard-voice-assets
- apis/dashboard-workflow
- apis/index-tts
- tables/knowledge-vault
- concepts/development-baseline
- concepts/identity-authority
supersedes:
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-index-tts-skill
```
### 网页预设绑定与默认音色

#### 目标与背景

用户已有网页预设，但联系人里的自动回复音色列表只来自本地 VoiceAssetStore。上一轮只增加授权开关，未接网页预设列表。本次在 IndexTTS 区域新增独立的网页预设下拉、刷新和默认绑定；只局部更正 supersedes 记录中“无联系人默认预设”“preset 必填”和“无新增后端接口”的结论，其余权限、其他生成默认值、分段和投递契约保留。旧 raw 不修改。

#### 文件与代码位置

- src/butler/delivery/tts_presets.py：PresetBindings，由 Butler 业务持有按会话存储，实时列表、版本检查、锁内原子写入/返回本次提交结果。
- src/butler/delivery/tts.py：生成在当前服务身份中解析默认值，显式覆盖优先；幂等按原始参数固定，先复用旧操作再读默认，配置变化/清除不重发旧任务。
- src/butler/agent/tools.py：tts_generate 的 preset 可省略，tts_presets 返回当前会话 default_preset；身份/只读/动态授权边界不变。
- src/dashboard/api/tts_presets.py、routes.py：新增本地管理端适配，确认头、完整联系人存在性和版本冲突；停用会话也可配置。
- web/src/components/ContactDialog.vue、styles/contacts.css：网页预设读取/保留/刷新/绑定，部分失败留窗；提交前冻结目标及选项，响应中按稳定会话 ID 找规范化名称，后续设置不能串写其他联系人；保存期间禁用所有可编辑字段。
- plugins/butler-wechat/skills/tools/index-tts/SKILL.md：默认值与显式覆盖说明；web/scripts/smoke.mjs 与 web/dist 配套；README 和图谱更新。具体稳定锚点见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) sources。

#### 接口与字段

GET /api/tts-presets?contact=... → ok/presets[]/preset/version/available/error。网页不在线仍返回保存值和修订，不把本地资产当网页预设。POST /api/tts-presets 精确接收 contact/preset/version，需同源 X-Wxbot-TTS-Action，纳入本地 BUSINESS 门；非空预设必须仍在网页列表，空值清除。未知目标/预设 400，未确认 403，修订冲突 409，存储 I/O 错误 503。

联系人校验使用完整 ContactStore.conversations，不能使用仅含启用路线的投影。旧自动回复本地资产接口保持原契约。工具仍只接 text/preset，preset 可省略且仅在当前会话有默认时成功；显式值优先。工具结果记录实际使用的 preset，未知/失效默认不自动换声。

#### 数据库与迁移

无新表/列/迁移。Butler data_dir/tts-presets.json 保存 {version:1,presets:{会话名:预设名}}，文件 version 是格式版本；API version 为规范化内容 SHA256 修订值。网络查询不持锁；配置锁内复查版本、合并映射、临时文件 fsync/replace，写失败保留旧文件，不复制预设音频或高级参数。默认变化不影响已登记 operations 的原参数幂等。

#### 前端消费点

联系人 → 基本资料 → 会话设置 → IndexTTS → 网页音色预设。与自动回复音色资产分开。GET 失败或网页断开保留旧选择；未改不写、重命名复制；保存失败明确哪些设置已完成，保留弹窗以新版本重试。新增控件使用既有主题、焦点/禁用和可访问性状态。

保存期间冻结表单目标、模式、资产、预设与授权，按联系人响应的稳定 ID/规范化名继续；缺少目标即停止后续写入。禁用窗口可配置预设；绑定本身不授予工具执行权限，也不自动启用语音模式或设备。

#### 测试与异步任务

先失败后通过的测试覆盖绑定隔离、默认/显式覆盖、默认改变或清除后的幂等、版本冲突、网页断开、未知预设、原子写失败、管理端确认/未知/停用联系人和工具身份。实际 Vue 烟测覆盖列表来源、保存/刷新、旧绑定保留、未改不写、部分失败/重试、重命名，以及延迟联系人响应期间强改目标/模式/预设仍只保存提交快照。

独立审阅发现两项 P2（停用联系人投影与等待期间目标可变），均补失败→通过回归，复核闭环。构建、全站烟测与管理台/语音回归通过；Skill 格式验证及 Hallmark 新组件静态检查通过，真实构建路由的桌面/375px 下拉、对比度、焦点和无横向溢出检查通过。全页仍有既有背景控件/字号/卡片等样式发现，未扩大本次修整。

已只读确认真实 WebUI 可列出用户已有预设；没有保存或复制真实用户配置、没有额外真实音频发送。无新增业务调度任务。

#### 风险与回滚

当前运行服务尚未加载新接口，用户明确选择稍后手动重启；实际页面待管理台与 Butler 重启后加载。配置按安装自己的 data_dir 读取，不能从另一安装复制。部分保存不是跨文件/数据库原子事务，失败保留弹窗并说明范围。预设删除/网页不可达必须刷新/重选，不自动猜测其他声线。回退新接口、默认解析、前端和 Skill 可移除扩展，不删已生成音频或配置。临时只读预览在验证后关闭，既有服务未重启。
<!-- end-migrated-part: doc-14cc58d084986d -->

<a id="doc-a877b64be56f43"></a>

### 网页预设图谱契约说明

来源：`llm wiki/wxbot/raw/changes/2026-11-04-webui-preset-graph-note.md:1`。

```yaml
type: change
title: 网页预设图谱契约说明补充
pages:
- modules/butler
- modules/dashboard
- modules/delivery
- modules/identity
- modules/plugin
- modules/web
- modules/wiki
- apis/dashboard-knowledge
- apis/dashboard-queue
- apis/dashboard-voice-assets
- apis/dashboard-workflow
- apis/index-tts
- tables/knowledge-vault
- concepts/development-baseline
- concepts/identity-authority
supersedes:
- raw/changes/2026-11-04-webui-preset-binding
```
### 网页预设图谱契约说明

#### 目标与背景

补充前条记录后的图谱措辞核对：更正自动追加的“后端契约保持”泛化表述。只有原有音频/图文/联系人接口保持；网页预设增加 GET/POST /api/tts-presets，且工具 preset 改为可省略。本条仅更正图谱说明，不改写已入库 raw，不撤销前条实现。

#### 文件与代码位置

记录所列词条的说明与来源已核对；原实现及稳定锚点仍见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。无源码、构建或测试修改。

#### 接口与字段

新增管理端列表/默认绑定接口，原确认机制、完整联系人校验和版本检查见前条；原有其他接口不变。省略工具 preset 按服务端当前会话默认解析。

#### 数据库与迁移

不适用：本条无运行数据或迁移变化。

#### 前端消费点

不适用：仅澄清图谱，不改变已构建的下拉框。

#### 测试与异步任务

复用前条最终 256 项通过、Vue 烟测与实际路由显示验证；本条仅运行图谱 ingest/lint。无后台任务。

#### 风险与回滚

没有运行时风险；保持历史记录不可变，当前词条使用本条补充来源。原有四项图谱待办不在本次修订范围。
<!-- end-migrated-part: doc-a877b64be56f43 -->
