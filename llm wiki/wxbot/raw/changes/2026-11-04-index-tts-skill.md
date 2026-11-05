---
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
---
# 网页预设文字转语音 Skill

## 目标与背景

将本机已有 IndexTTS WebUI 接入微信 Butler，生成仅接收文字与保存的音色预设，其余网页默认；通过既有虚拟麦和 RALT 链路发送，长文本拆成多条。用户明确授权一条指定目标/文案/预设的实机发送，运行数据仅在本机测试产物，不写入图谱。

本条仅更正 supersedes 旧记录中“无绑定一律不走 RALT”的无例外表述：新授权预设包已提供参考音，因此独立于管理台绑定。旧自动回复和旧主动语音的绑定规则、管理台 UI 保持不变。既有未提交修改与两条旧待入库记录不删除、不改写。

## 文件与代码位置

新技能 plugins/butler-wechat/skills/tools/index-tts/SKILL.md；新业务客户端 src/butler/delivery/gradio_tts.py、存储与幂等 tts.py；tools.py 声明与分发，core.py 注入服务，server.py 提供鉴权音频 GET，push.py 提供持久入队客户端。Codex MCP 工具超时随请求配置，原总预算/能力 TTL 约束保留。

common/media_bundle.py 新增独立语音 schema，voice_audio.py 完成文字/PCM 分段与重采样；wxbot/outbound.py 鉴权下载和持久化回执，queue_store.py 复用包写入；delivery.py 选择已生成音频并使用语音包开关与失败语义。wechat/chat_window.py 拒绝草稿，wechat/voice.py 先录音再播放并保证异常释放，voice/playback.py 分开准备/播放和错误清理可重入锁。具体位置和稳定锚点见 [[apis/index-tts]] sources。

同步 README 文件地图/使用方式、关联词条 source 行号与反向导航。对仅因文件内插入产生摘要/行号变化的图谱条目核对 diff，既有 API、身份、队列其他规则无语义变更；保留原 changes。

## 接口与字段

tts_presets 只读；tts_generate(text<=6000, preset<=256) 通过服务签发能力，不收目标/路径/URL。动态预设共享独立 Gradio 会话，只取参考音；其余 /info 默认值，空可选 Audio 对照 /config 处理。每片文字 160 字，音频 16kHz mono PCM16、0.4-55s、全包<=50。

GET /v1/audio/<id> 使用现有 Bearer；POST /send-voice-bundle 使用现有 X-Wxbot-Token，body contact/items/request_id；items 精确 kind/media_id。queued 仅确认 UI 线程完成持久化，delivery_unknown 不重发，原图文契约保持。

## 数据库与迁移

无新表/列/迁移。operations 登记幂等指纹、处理中和结果，别名调用编号绑定同一指纹且同步结果；耗时 HTTP 在事务外。delivery_packages/outbox 原字段复用，media_path 仅由鉴权缓存提供。文件按身份散列分区；不提交运行音频/数据库。

## 前端消费点

无前端源码或交互修改，不适用 Hallmark/build/dist。既有队列投影读取原字段/状态。新技能沿目录发现/联系人允许列表，无 UI 新字段。

## 测试与异步任务

先失败后通过的测试覆盖生成幂等、别名换参拒绝、权限撤销/只读、网页默认值、同会话队列、下载边界、音频保帧分段、原图文拒绝语音字段、顺序/包中断、持久化回执、RALT 时序/异常释放/草稿拒绝。新鲜上下文审阅发现 3 项 P2，均追加失败→通过回归并复核闭环。

相关 Butler/Codex/媒体/队列回归只出现两项既有队列策略期望失败，未扩展本任务修改其行为；新增相关测试通过。Skill quick_validate 通过，行为对照修正了基线继承高级预设的误读。

真实 WebUI 生成成功；使用测试专属临时 HTTP 端口/令牌/队列/数据完成现有 CABLE/PTT 链路一次发送，并在微信目标聊天核对到新语音气泡。未重启任何已有服务、未改本机长期配置、未自动重发。测试辅助服务结束后关闭。不新增后台调度任务。

## 风险与回滚

启动/语音配置由使用者加载；本机网页、CABLE、语音总开关/联系人模式、技能白名单任一缺失均不能投递。queued 不是送达/收听。已录音失败 uncertain，余下包停止；操作断流/未知状态不自动重放。撤销本次代码和技能即可回退，不删除已有业务或预设数据。原 raw 记录保持不变，例外门控由本条追加更正。
