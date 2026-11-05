---
type: impact
status: verified
date: '2026-11-04'
---
# Butler IndexTTS 技能设计与影响面

## 已确认需求

- 在 `plugins/butler-wechat/skills/tools/index-tts/` 新增技能，供微信中的 Butler 通过授权工具调用。
- 生成工具只接收 `text`（文字）与 `preset`（网页保存的音色预设名称）。
- 使用当前 `http://127.0.0.1:7860` WebUI。选用预设的音色参考音频；语言、语速、情感和采样等其余参数使用 WebUI 公布的默认值。

## 方案

由 Butler 服务端调用现有 WebUI 的 Gradio API，复用已经加载的模型。另一条路径是另起 IndexTTS Python 进程，但这会重复加载模型且偏离用户指定的网页服务，故本设计采用前者。

新增两个工具：

- `tts_presets()`：读取网页当前已保存的预设名称。
- `tts_generate(text, preset)`：使用指定预设的参考音频生成 WAV，将音频复制到 Butler 数据目录中当前身份所属的子目录，返回成功状态、音频编号和本机 WAV 文件路径。

按用户后续明确要求，生成后通过既有 CABLE Input 播放 / CABLE Output 录音、Right Alt 长按链路发送到当前微信会话。文字按句拆分，生成的音频再保证每条不超过 55 秒，整包按序持久化投递。工具返回 queued 只表示持久化排队，不表示微信气泡已确认。

## 权限与失败行为

沿用 `ToolService.issue/verify/definitions/call`。管理员须将技能加入对应联系人的允许技能，服务端验证当前身份与技能授权；只读/心跳上下文仅可查询预设。

URL、身份和输出目录由服务端确定，模型不能指定联系人、文件路径或任意远端地址。Gradio 请求仅连接本机并绕过系统代理。

使用现有 `operations` 表的 owner/request_id/call_id/fingerprint/result 记录幂等状态；提交生成前先登记，耗时 HTTP 调用在数据库事务外执行。重复工具调用复用记录；提交后超时或断流不自动再次生成。

未知或空预设、缺少参考音频、网页不可连接、接口不兼容和无效音频均返回明确失败，不能宣称已生成。通过刷新接口读取预设，不把 `/config` 中启动时的下拉快照当作实时预设列表。

## 文件、调用方与契约

- 新增技能 `plugins/butler-wechat/skills/tools/index-tts/SKILL.md`，声明 `tts_presets/tts_generate`。
- 修改 `src/butler/agent/tools.py` 的工具定义、参数校验与分发，保留已有工具语义。
- 新增 `src/butler/delivery/gradio_tts.py`，负责 Gradio 队列/SSE、默认参数和音频下载。
- 新增 `src/butler/delivery/tts.py`，负责身份归属、幂等状态与生成文件存储。
- 使用 `SkillCatalogue` 现有工具分类、会话白名单与 MCP/原生工具后端，无需新增模型后端或修改 WebUI。
- 配套更新 README 与受影响图谱词条、追加 raw 记录并 ingest/lint。保留主目录原有未提交修订。

源码依据：`src/butler/agent/catalogue.py:8`、`src/butler/agent/tools.py:51`（能力校验）、`:99`（分发）、`src/butler/business.py:44`（operations 表）。实施后以实际位置更新来源。

## 数据、前端与验证

不新增数据库表或迁移；扩展 operations.result 的本工具状态内容。没有 Vue 页面、字段或交互改动，也不改另一仓库的 WebUI 源码。

补充影响面：`common/media_bundle.py` 新增独立语音包校验（原图文 schema 不变）；`common/voice_audio.py` 做 PCM 转换、重采样和分段；Butler 新增鉴权音频 GET；`wxbot/outbound.py` 增加 `/send-voice-bundle` 和持久化回执；`queue_store.py` 复用 delivery_packages/outbox.kind/media_id/media_path/part_seq；`delivery.py` 用已准备音频绕过参考音绑定和再次合成，仍检查语音全局开关及联系人模式。语音包不走新闻订阅校验，也不在失败后重复发文字。`voice/playback.py` 修复启动错误清理时重入锁死锁，`wechat/voice.py` 确保先按 RALT 再开始灌音，并在播放异常后保守标记不确定。

调用链：Skill → ToolService capability → TTSService（operations 幂等，事务外生成）→ Gradio → AudioStore → wxbot 鉴权 HTTP → 临时队列 → UI 线程持久化语音包 → DeliveryPump → VoiceSession。没有前端 DTO 变动，音频包字段仅 kind/media_id，路径和目标均不由模型提供。新 HTTP 回执等待数据库提交，不等待全部语音播放，避免长文本占满模型请求时限。生成后重新验证能力，过期或撤权不入队；提交结果未知禁止自动重发。

实施顺序与验证：1. 先写并运行失败的客户端、音频、幂等/授权、语音包测试；2. 实现客户端与存储/工具；3. 接入鉴权下载及队列/音频播放，运行相关回归；4. 新增技能并进行无说明/有说明的行为对照；5. 新鲜上下文复核整项变更；6. 按用户指定联系人和文案实机验证；7. 更新图谱并 ingest/lint。保留工作区此前修改，不提交或推送。

执行台账：已创建 codex/index-tts-skill 分支，继续使用用户指定且已统一环境的根工作目录，避免再次建立独立运行安装。无 Skill 基线模拟把“其余默认”误解为继承预设保存的高级设置；新 Skill 明确只取音色参考，其余使用网页默认值。

完成验证：新增功能与既有投递相关 22 项通过；较大范围 Butler/Codex/媒体/队列回归 778 项通过、2 项既有队列策略期望失败。真实 WebUI 已生成用户指定短文，借测试专属 HTTP/缓存/数据库及原 PTT 代码执行一次授权发送，并在目标窗口观察到新语音气泡。测试辅助服务已关闭，已有服务/长期配置未改，未重复发出。新鲜上下文复核的 3 项 P2（UIA 异常释放、MCP 时限、别名幂等）修复后复核通过。Skill 格式与行为对照通过，图谱记录见 [[raw/changes/2026-11-04-index-tts-skill]]。

先用临时数据库和假 Gradio 服务验证授权、默认参数、动态预设、一次生成、未知结果不重试、超时及文件边界，再做真实服务生成。用户已明确授权完成后按其指定的一个目标、文案和预设做实机发送；不将真实联系人、文案、预设或音频内容写入图谱。

服务由使用者自行重启加载新代码；不自动重启 Butler、wxbot、管理台或 WebUI。回退为撤销本次技能/服务代码和图谱修改，已有配置、业务数据和用户预设保持原状。
