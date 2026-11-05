---
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
---
# 修复群聊越屏采集与自动语音回复链路

## 目标与背景

修复群聊无法采集/回复、私聊语音模式仍发文字、群聊播放固定提示音。已证实历史消息区越出真实监视器导致截图补黑；当前窗口入屏后原方向算法正常。自动语音另有隐式 fixture、启动快照不更新、streaming 绕过语音三条原因。见 [[impacts/2026-11-05-group-and-auto-voice]]、[[concepts/capture-viewport]]、[[concepts/automatic-voice-reply]]。

## 文件与代码位置

新增 wechat/viewport.py 联合几何/工作区恢复；chat_window.py 截图前拒绝 row_offscreen 并恢复当前面板，main_window.py 选择前恢复。新增 Butler delivery/automatic_tts.py 精确预设/规范 PCM 服务；voice/policy.py 新 provider 与热读，voice/tts.py 薄适配及音频预设身份；queue_worker.py 在流式前快照语音并缓冲；inbox.py 注入 loader 及录音恢复后 UI 互斥；delivery.py daemon 合成、绑定复核、旧 fixture 缓存重合成及失败终结。dashboard/voice_admin.py 显示有效 provider，README 更新说明。准确位置见各关联页 sources/anchors；保留原有未提交修改。

## 接口与字段

无外部 API/DTO 变更。保持 finish_batch_parts 的 voice_mode/media_path 和 outbox.kind=voice。内部 TtsAudio 新增默认 source_preset，AutomaticReplyTts.synthesize 新增可选 expected_preset，旧调用兼容。生成前后、start_voice 和 before_enter 复核准确预设/提供者。自动服务只合成，不主动投递、不 mint 工具能力或写 operations。

## 数据库与迁移

无表/字段/迁移。配置热读只取本安装 wxbot 文件的 voice；网页绑定仍由 Butler 的本安装数据目录持有。旧自动 fixture 媒体在当前 webui 下重合成，显式媒体包不变。自动 webui 在录音前失败终结 skipped 并保留错误，replace 单次文字回退、coexist 不重复文字；录音后的 uncertain 仍不重播。未改生产队列或权限配置。

## 前端消费点

未改 web/ 源码或构建产物，本次不涉及前端设计/构建。GET /api/voice-bindings 的 tts_provider 复用有效 provider 推导，字段/schema 不变。角色和声音选择保持管理员的已保存值。

## 测试与异步任务

TDD 红绿覆盖越屏截图/同文缓存/窗口恢复、provider 默认、streaming 语音、热读、异步等待、准确预设变更、同 tick 录音切换及失败不重试。群聊相关39项、语音相关50项通过，另2项本机fakeHTTP传输通过。最终全量1540项：1536通过、4失败、无errors/skips。失败与上轮相同：test_portable_install.py::test_plugin_references_and_protocol_are_self_contained；test_queue_admin.py::test_multipart_cli_sent_and_retry_preserve_other_parts；test_queue_store.py::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker；test_typing.py::test_typing_steps_keep_half_second_between_batches_and_one_final_enter。compileall/diff检查通过。独立复核发现的预设身份/录音切换竞态已修并复查。真实本机WebUI仅生成验证返回16kHz单声道PCM16、6.42秒音频，不是送达证明。新增daemon Future后台准备，不占active UI，不重复认领，close后不采用晚到结果。测试用临时库/假投递/合成像素，未触碰真实剪贴板或发测试微信。

## 风险与回滚

无法恢复窗口或监视器信息不可用时仍安全暂缓；不放宽gutter、不猜发送方。自动语音受单条时长上限，超长/WebUI离线/本地预设缺失按模式回退，不截断或猜声音。外部Butler的远端绑定不会由新增endpoint读取。新代码需使用者手动重启wxbot；现有WebUI继续复用，无第二份模型。之后语音配置用于后续批次和录音前复核。不自动重启、不改角色/音色/运行配置、不发真实测试消息。回滚本次源码/README，无迁移。保留两个原有2026-11-03待入库记录，不机械代替其语义核对。
