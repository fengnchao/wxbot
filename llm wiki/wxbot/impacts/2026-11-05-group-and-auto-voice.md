# 群聊采集与自动语音回复影响分析

## 目标与基线

修复群聊窗口越屏导致发送方无法识别、私聊语音配置未用于自动回复、群聊播放固定测试音频。
主工作树 D:/work/code/wxbot，codex/index-tts-skill，HEAD a1f40c38e120376f992d69628f0e8aec308f1d76；保留所有已有未提交工作。

## 已核对链路与候选原因

- ChatWindow.side_scores（src/wxbot/wechat/chat_window.py:94）采最外三列为左右背景，窄黑边可触发 gutter_mismatch，_classify 标成 system；MainInbox._capture/read_bundle 对无法确认的发送方保留快照并 ReadDeferred。
- 历史日志右坐标在屏幕边缘附近，但当前窗口已处于另一位置；不能只凭旧坐标断言越屏。必须以只读实时几何/像素诊断区分边框与遮挡，不放宽宽范围遮挡判据。
- ModelWorker（src/wxbot/queue_worker.py:112-170）流式私聊有 streamed 前缀时跳过非流式语音入队分支；模式 replace/coexist 应先缓冲完整回复，再按语音策略入队。
- VoicePolicy（src/wxbot/voice/policy.py:21、:106、:215）默认 fixture，queued_media_path 写固定测试 WAV；FixtureTtsSource.prepare 忽略正文，是固定提示音的原因。
- MainInbox（src/wxbot/inbox.py:79-99）仅启动时加载语音策略，保存后的新模式/绑定无法应用到后续回复。
- 网页默认音色绑定由 Butler PresetBindings 持有，GradioTtsClient 已复用运行中的 WebUI。自动链路目前不读该绑定；TTSService.generate 含主动投递，不能在自动回复中直接复用，否则会双入队。

## 修改范围与契约

- ChatWindow 仅修改方向像素证据处理；不猜发送方、不吞 ReadDeferred、不推进无法确认的快照，合成图测试覆盖真正遮挡。
- 新 Butler delivery 自动合成服务只返回标准 WAV，不写工具 operations、不主动投递、不伪造服务能力；薄适配器接现有 TtsSource.prepare(text,contact)。
- 新增 webui provider：未显式配置 provider 和 fixture_wav 时使用真实 WebUI，显式 fixture/旧 fixture_wav 保持测试兼容。按精确会话绑定读取预设，不猜声音，不启动第二份模型。
- Worker 在流式输出之前快照语音策略，语音模式先缓冲完整文字；保留 finish_batch_parts 的 voice_mode/media_path 入队合同。
- 从实际配置路径只热读 voice 设置，后续批次使用新策略，录音前复核总开关与会话模式；读失败保守停止语音，不把旧权限当成新授权。
- 预期涉及 voice/policy.py、voice/tts.py、queue_worker.py、inbox.py、delivery.py、新 Butler delivery 模块及对应临时数据测试。无需修改前端布局、角色、提醒、外部模型或消息协议。

## 数据血缘与副作用

语音设置仍来自本安装配置，网页默认预设仍由 Butler 持有。模型回复正文 → 合成 → 已有 outbox.kind=voice/media_path → 虚拟麦/PTT；无新表/字段或迁移。
只对原已开启自动语音的会话生效，不新增模型工具权限。原 replace 失败单次文字回退和 coexist 不重发文字规则保留；已开始录音的不确定结果不自动重录。
不修改运行配置或生产队列，不重启服务，不发送真实测试消息。截图/实际消息/认证内容仅用于本地诊断，禁止进入本图谱。

## 验证计划与风险

先用离线合成图和临时队列复现，再验证群聊窄边框/宽遮挡/裁剪、流式 replace/coexist、默认 provider 迁移、精确网页预设、配置重载及录音前关闭。
运行相关测试与完整离线 pytest、compileall、diff 检查。上轮全量有安装技能数量、两项队列状态、输入节奏四项失败，须区分而非静默忽略。
真实 UI 正常几何的诊断不代替历史截图；WebUI 不在线/预设缺失按原失败策略明确回退。长音频仍受既有单条时长合同约束。
回滚本次源码即可，无迁移；加载新代码仍需使用者自行重启 wxbot，自动合成服务为本地库复用既有 WebUI。


## 最终结论与验证

只读实时几何证实历史右边界2047超出当前1920屏幕，当前入屏后原方向算法正常；未放宽gutter判据，改为采集/选择前恢复可见区域。

自动语音采用本安装网页预设，daemon合成不占UI，精确预设/提供者在录音前再核对；失败单次回退，录音开始后仍不自动重试。独立复核提出的预设重绑与同tick切换竞态已修，最后无重要遗留项。

最终完整测试1540项：1536过、4项与上轮相同的失败；相关测试和本机仅生成校验已通过。详细失败名称/限制见 [[raw/changes/2026-11-05-group-auto-voice]]。源码编译和diff检查通过。无需为本次纯后端修改重建前端。未改生产数据、未发测试微信、未重启服务。
