
## [2026-10-31] change | 项目知识图谱首批建档与维护闭环

来源：[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

## [2026-10-31] ingest | 项目知识图谱首批建档与维护闭环

来源：[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

[[apis/butler-handle]]、[[apis/butler-handle-stream]]、[[apis/dashboard-queue]]、[[apis/dashboard-workflow]]、[[concepts/delivery-state]]、[[concepts/identity-authority]]、[[concepts/message-pipeline]]、[[modules/butler]]、[[modules/common]]、[[modules/dashboard]]、[[modules/delivery]]、[[modules/identity]]、[[modules/plugin]]、[[modules/runtime]]、[[modules/telegram]]、[[modules/web]]、[[modules/wiki]]、[[modules/wxbot]]、[[symbols/butler-handle]]、[[symbols/butler-processor]]、[[symbols/butler-result]]、[[symbols/model-worker]]、[[symbols/queue-finish]]、[[symbols/queue-store]]、[[tables/queue-batches]]、[[tables/queue-inbox]]、[[tables/queue-outbox]]

## [2026-10-31] query | 首批真实关键词查询

关键词 `/v1/handle`、`reply_complete`，沿双向链接展开一跳，返回处理接口、队列和管理台消费候选。实施影响报告：[[impacts/2026-10-31-knowledge-graph-bootstrap]]。

## [2026-10-31] lint | 首批一致性巡检与交付验证

27 个词条通过机械巡检，待入库记录 0；专项回归 20 passed / 1 skipped。整库回归未通过和语义覆盖边界见 [[verification]]、[[coverage]]。来源：[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]。

## [2026-10-31] change | 保留 batches 词条后续表格排版

巡检检出入库后的词条排版变化，保留当前编辑并核对事实。来源：[[raw/changes/2026-10-31-queue-batches-format]]。

## [2026-10-31] ingest | 保留 batches 词条后续表格排版

来源：[[raw/changes/2026-10-31-queue-batches-format]]

[[tables/queue-batches]]

## [2026-10-31] ingest | 统一 Butler 模型链路与随时切换

来源：[[raw/changes/2026-10-31-switchable-models]]

[[apis/butler-handle]]、[[apis/butler-handle-stream]]、[[concepts/message-pipeline]]、[[modules/butler]]、[[modules/models]]、[[modules/runtime]]、[[modules/web]]、[[modules/wiki]]、[[modules/wxbot]]、[[symbols/butler-handle]]、[[symbols/butler-processor]]、[[symbols/butler-result]]、[[symbols/local-model-backend]]、[[symbols/reloadable-backend]]

## [2026-10-31] ingest | 配置页接入方式下拉与模型字段随选择变化

来源：[[raw/changes/2026-10-31-model-access-switch]]

[[modules/models]]、[[modules/dashboard]]、[[modules/web]]、[[modules/butler]]、[[symbols/local-model-backend]]

## [2026-10-31] ingest | 模型来源上报改用接入方式（core.py 相关词条更正）

来源：[[raw/changes/2026-10-31-model-access-switch-core-emit]]

[[apis/butler-handle]]、[[concepts/message-pipeline]]、[[symbols/butler-handle]]、[[symbols/butler-result]]

## [2026-10-31] ingest | 群成员身份改用昵称优先，头像只作证据

来源：[[raw/changes/2026-10-31-group-identity-nickname]]

[[concepts/group-identity-evidence]]、[[concepts/identity-authority]]、[[concepts/delivery-state]]、[[concepts/message-pipeline]]、[[modules/common]]、[[modules/identity]]、[[modules/wxbot]]、[[symbols/queue-finish]]、[[symbols/queue-store]]、[[tables/queue-batches]]、[[tables/queue-inbox]]、[[tables/queue-outbox]]

## [2026-10-31] ingest | 截图占位名不再当作群昵称重放

来源：[[raw/changes/2026-10-31-identity-placeholder-names]]

[[concepts/group-identity-evidence]]、[[concepts/message-pipeline]]、[[modules/wxbot]]

## [2026-11-01] change | model request failure keeps redacted status

来源：[[raw/changes/2026-11-01-model-request-error-visibility]]

## [2026-11-01] ingest | 模型请求失败保留脱敏状态码

来源：[[raw/changes/2026-11-01-model-request-error-visibility]]

[[symbols/local-model-backend]]、[[modules/models]]

## [2026-11-01] change | model failure contract archived as concept

来源：[[raw/changes/2026-11-01-model-error-contract]]

## [2026-11-01] ingest | 模型失败契约补齐为概念词条

来源：[[raw/changes/2026-11-01-model-error-contract]]

[[concepts/model-error-contract]]、[[concepts/delivery-state]]、[[modules/models]]

## [2026-11-01] ingest | L1 聊天原文落库与只读看板

来源：[[raw/changes/2026-11-01-knowledge-episodes]]

[[tables/kb-episodes]]、[[apis/dashboard-knowledge]]、[[modules/butler]]、[[modules/dashboard]]、[[modules/web]]、[[apis/butler-handle]]、[[apis/dashboard-queue]]、[[apis/dashboard-workflow]]、[[symbols/butler-handle]]、[[symbols/butler-result]]、[[concepts/message-pipeline]]、[[concepts/model-error-contract]]

## [2026-11-01] change | 知识库拆分为一人一库并新增提炼事实库

来源：[[raw/changes/2026-11-01-knowledge-sharding]]

## [2026-11-01] ingest | 知识库拆分为一人一库并新增提炼事实库

来源：[[raw/changes/2026-11-01-knowledge-sharding]]

[[tables/kb-episodes]]、[[tables/kb-facts]]、[[tables/kb-owners]]、[[apis/dashboard-knowledge]]、[[apis/butler-handle]]、[[apis/dashboard-queue]]、[[apis/dashboard-workflow]]、[[concepts/message-pipeline]]、[[concepts/model-error-contract]]、[[symbols/knowledge-extract]]、[[symbols/butler-handle]]、[[symbols/butler-result]]、[[modules/butler]]、[[modules/dashboard]]、[[modules/web]]、[[modules/runtime]]

## [2026-11-01] change | 会话维度：左栏按人、右栏按私聊/群聊再筛

来源：[[raw/changes/2026-11-01-knowledge-sessions]]

## [2026-11-01] ingest | 会话维度：左栏按人、右栏按私聊/群聊再筛

来源：[[raw/changes/2026-11-01-knowledge-sessions]]

[[apis/dashboard-knowledge]]、[[tables/kb-episodes]]、[[tables/kb-facts]]、[[tables/kb-owners]]、[[symbols/knowledge-extract]]、[[modules/web]]

## [2026-11-01] change | 自动提炼：进程内调度器、跨进程单飞与管理台状态

来源：[[raw/changes/2026-11-01-knowledge-auto]]

## [2026-11-01] ingest | 自动提炼：进程内调度器、跨进程单飞与管理台状态

来源：[[raw/changes/2026-11-01-knowledge-auto]]

[[apis/butler-handle]]、[[apis/butler-handle-stream]]、[[apis/dashboard-knowledge]]、[[apis/dashboard-queue]]、[[apis/dashboard-workflow]]、[[concepts/model-error-contract]]、[[modules/butler]]、[[modules/dashboard]]、[[modules/models]]、[[modules/runtime]]、[[modules/web]]、[[modules/wiki]]、[[symbols/butler-handle]]、[[symbols/butler-result]]、[[symbols/knowledge-auto]]、[[symbols/knowledge-extract]]、[[tables/kb-episodes]]、[[tables/kb-facts]]、[[tables/kb-owners]]

## [2026-11-01] change | 群聊提及回退清理与不可读未读的退避放弃

来源：[[raw/changes/2026-11-01-mention-fallback-unread-retry]]

## [2026-11-01] ingest | 群聊提及回退清理与不可读未读的退避放弃

来源：[[raw/changes/2026-11-01-mention-fallback-unread-retry]]

[[concepts/delivery-state]]、[[concepts/group-identity-evidence]]、[[concepts/identity-authority]]、[[concepts/message-pipeline]]、[[concepts/model-error-contract]]、[[concepts/unread-capture-retry]]、[[modules/telegram]]、[[modules/wxbot]]、[[symbols/mention-selection]]、[[symbols/queue-finish]]、[[symbols/queue-store]]、[[tables/queue-batches]]、[[tables/queue-inbox]]、[[tables/queue-outbox]]

## [2026-11-01] change | 词条代码引用行号复核

来源：[[raw/changes/2026-11-01-citation-sweep]]

## [2026-11-01] ingest | 词条代码引用行号复核

来源：[[raw/changes/2026-11-01-citation-sweep]]

[[concepts/group-identity-evidence]]

## [2026-11-01] change | README 补不可采集未读的说明与图谱来源修正

来源：[[raw/changes/2026-11-01-readme-unread-note]]

## [2026-11-01] ingest | README 补不可采集未读的说明与图谱来源修正

来源：[[raw/changes/2026-11-01-readme-unread-note]]

[[modules/wiki]]

## [2026-11-01] change | 用户知识库改为一人一个 Obsidian vault 并删除 memory 链路

来源：[[raw/changes/2026-11-01-knowledge-vault-graph]]

## [2026-11-01] ingest | 用户知识库改为一人一个 Obsidian vault 并删除 memory 链路

来源：[[raw/changes/2026-11-01-knowledge-vault-graph]]

[[tables/knowledge-vault]]、[[tables/kb-episodes]]、[[tables/kb-facts]]、[[tables/kb-owners]]、[[apis/dashboard-knowledge]]、[[symbols/knowledge-extract]]、[[symbols/knowledge-auto]]、[[modules/butler]]、[[modules/runtime]]、[[modules/dashboard]]、[[modules/identity]]、[[modules/plugin]]、[[modules/web]]、[[modules/wiki]]、[[modules/common]]、[[modules/models]]、[[apis/butler-handle]]、[[apis/butler-handle-stream]]、[[apis/dashboard-queue]]、[[apis/dashboard-workflow]]、[[symbols/butler-handle]]、[[symbols/butler-result]]、[[symbols/local-model-backend]]、[[concepts/message-pipeline]]、[[concepts/identity-authority]]、[[concepts/group-identity-evidence]]、[[concepts/model-error-contract]]

## [2026-11-01] change | 知识库 vault 词条与实现对齐

来源：[[raw/changes/2026-11-01-knowledge-vault-alignment]]

## [2026-11-01] ingest | 知识库 vault 词条与实现对齐

来源：[[raw/changes/2026-11-01-knowledge-vault-alignment]]

[[tables/knowledge-vault]]

## [2026-11-01] change | 知识库迁移改名留底前先合并 WAL

来源：[[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]

## [2026-11-01] ingest | 知识库迁移改名留底前先合并 WAL

来源：[[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint]]

[[tables/knowledge-vault]]、[[tables/kb-episodes]]、[[tables/kb-facts]]、[[tables/kb-owners]]

## [2026-11-01] change | 迁移改动后复核知识库词条来源

来源：[[raw/changes/2026-11-01-knowledge-migrate-source-recheck]]

## [2026-11-01] ingest | 迁移改动后复核知识库词条来源

来源：[[raw/changes/2026-11-01-knowledge-migrate-source-recheck]]

[[apis/dashboard-knowledge]]、[[symbols/knowledge-extract]]

## [2026-11-01] change | 知识库加中心索引页与七类事实分组

来源：[[raw/changes/2026-11-01-knowledge-atlas-index]]

## [2026-11-01] ingest | 知识库加中心索引页与七类事实分组

来源：[[raw/changes/2026-11-01-knowledge-atlas-index]]

[[tables/knowledge-vault]]、[[tables/kb-episodes]]、[[tables/kb-facts]]、[[tables/kb-owners]]、[[symbols/knowledge-extract]]、[[symbols/knowledge-auto]]、[[modules/web]]、[[apis/dashboard-knowledge]]、[[concepts/message-pipeline]]

## [2026-11-01] change | 知识库写入在文件被占用时退避重试

来源：[[raw/changes/2026-11-01-knowledge-atomic-retry]]

## [2026-11-01] ingest | 知识库写入在文件被占用时退避重试

来源：[[raw/changes/2026-11-01-knowledge-atomic-retry]]

[[tables/knowledge-vault]]、[[tables/kb-episodes]]、[[tables/kb-facts]]、[[tables/kb-owners]]、[[apis/dashboard-knowledge]]、[[symbols/knowledge-extract]]

## [2026-11-02] ingest | 知识图谱模板外部化为 Markdown 并支持管理台在线编辑

来源：[[raw/changes/2026-11-02-knowledge-graph-template]]

[[tables/knowledge-vault]]、[[tables/kb-episodes]]、[[tables/kb-facts]]、[[tables/kb-owners]]、[[symbols/knowledge-template]]、[[symbols/knowledge-extract]]、[[apis/dashboard-knowledge]]、[[apis/dashboard-queue]]、[[apis/dashboard-workflow]]、[[modules/runtime]]、[[modules/dashboard]]、[[modules/web]]、[[modules/plugin]]、[[modules/wiki]]

## [2026-11-02] ingest | UI 快照引用、发送确认证据与稳定失败码

来源：[[raw/changes/2026-11-02-ui-snapshot-ref-contract]]

[[concepts/delivery-state]]、[[concepts/group-identity-evidence]]、[[concepts/message-pipeline]]、[[concepts/unread-capture-retry]]、[[modules/wiki]]、[[modules/wxbot]]、[[symbols/mention-selection]]、[[symbols/queue-store]]、[[tables/queue-outbox]]

## [2026-11-02] ingest | 投递细节白名单扩展的词条复核

来源：[[raw/changes/2026-11-02-details-whitelist-reverify]]

[[concepts/identity-authority]]、[[concepts/model-error-contract]]、[[symbols/queue-finish]]、[[tables/queue-batches]]、[[tables/queue-inbox]]

## [2026-11-02] ingest | 群聊提及先等候选面板，失败残留登记为可清理草稿

来源：[[raw/changes/2026-11-02-mention-picker-gating-residue]]

[[concepts/delivery-state]]、[[modules/wiki]]、[[modules/wxbot]]、[[symbols/mention-selection]]、[[symbols/queue-store]]、[[tables/queue-outbox]]

## [2026-11-02] ingest | 提及残留登记引发的来源复核

来源：[[raw/changes/2026-11-02-mention-residue-reverify]]

[[concepts/group-identity-evidence]]、[[concepts/identity-authority]]、[[concepts/message-pipeline]]、[[concepts/model-error-contract]]、[[concepts/unread-capture-retry]]、[[symbols/queue-finish]]、[[tables/queue-batches]]、[[tables/queue-inbox]]
## [2026-11-02] ingest | 管理台全局搜索增加清空按钮

来源：[[raw/changes/2026-11-02-web-global-search-clear]]

[[modules/web]]

## [2026-11-03] change | FEAT-VOICE-001 P1 虚拟麦语音条（可插 TTS / Right Alt）

来源：[[raw/changes/2026-11-03-feat-voice-001-virtual-mic]]

## [2026-11-03] ingest | FEAT-VOICE-001 P1 虚拟麦语音条（可插 TTS / Right Alt）

来源：[[raw/changes/2026-11-03-feat-voice-001-virtual-mic]]

[[modules/wxbot]]、[[modules/delivery]]、[[concepts/delivery-state]]、[[tables/queue-outbox]]、[[concepts/message-pipeline]]

## [2026-11-03] change | FEAT-VOICE-001 连带锚点刷新

来源：[[raw/changes/2026-11-03-feat-voice-001-anchor-refresh]]

## [2026-11-03] ingest | FEAT-VOICE-001 连带锚点刷新

来源：[[raw/changes/2026-11-03-feat-voice-001-anchor-refresh]]

[[symbols/model-worker]]、[[symbols/queue-finish]]、[[symbols/queue-store]]、[[concepts/group-identity-evidence]]、[[concepts/identity-authority]]、[[concepts/model-error-contract]]、[[concepts/unread-capture-retry]]、[[tables/queue-batches]]、[[tables/queue-inbox]]、[[symbols/mention-selection]]

## [2026-11-03] change | FEAT-VOICE-003 音色资产与会话绑定

来源：[[raw/changes/2026-11-03-feat-voice-003-voice-assets]]

## [2026-11-03] ingest | FEAT-VOICE-003 音色资产与会话绑定

来源：[[raw/changes/2026-11-03-feat-voice-003-voice-assets]]

[[apis/dashboard-knowledge]]、[[apis/dashboard-queue]]、[[apis/dashboard-workflow]]、[[concepts/delivery-state]]、[[concepts/group-identity-evidence]]、[[concepts/message-pipeline]]、[[concepts/model-error-contract]]、[[concepts/unread-capture-retry]]、[[modules/dashboard]]、[[modules/wxbot]]、[[modules/web]]、[[tables/knowledge-vault]]、[[tables/queue-outbox]]、[[apis/dashboard-voice-assets]]、[[concepts/voice-asset-binding]]、[[symbols/voice-asset-store]]

## [2026-11-03] ingest | FEAT-VOICE-003 连带复核 model-worker 锚点

来源：[[raw/changes/2026-11-03-feat-voice-003-model-worker-drift]]

[[symbols/model-worker]]

## [2026-11-03] ingest | 音色资产页布局与状态打磨

来源：[[raw/changes/2026-11-03-voice-assets-polish]]

[[modules/web]]、[[apis/dashboard-voice-assets]]

## [2026-11-03] change | 统一当前开发基线、配置来源与发送实现文档

来源：[[raw/changes/2026-11-03-development-doc-baseline]]

## [2026-11-03] ingest | 统一当前开发基线、配置来源与发送实现文档

来源：[[raw/changes/2026-11-03-development-doc-baseline]]

[[concepts/development-baseline]]、[[modules/wiki]]

## [2026-11-04] change | 统一主目录 main 与可编辑安装绑定

来源：[[raw/changes/2026-11-04-root-workspace-unification]]

## [2026-11-04] ingest | 统一主目录 main 与可编辑安装绑定

来源：[[raw/changes/2026-11-04-root-workspace-unification]]

[[concepts/development-baseline]]、[[modules/wiki]]

## [2026-11-04] ingest | 网页预设文字转语音 Skill 与分段虚拟麦投递

来源：[[raw/changes/2026-11-04-index-tts-skill]]

[[modules/butler]]、[[modules/common]]、[[modules/delivery]]、[[modules/identity]]、[[modules/plugin]]、[[modules/wiki]]、[[modules/wxbot]]、[[apis/butler-handle-stream]]、[[apis/butler-handle]]、[[apis/dashboard-knowledge]]、[[apis/index-tts]]、[[tables/queue-batches]]、[[tables/queue-inbox]]、[[tables/queue-outbox]]、[[symbols/butler-handle]]、[[symbols/butler-result]]、[[symbols/knowledge-auto]]、[[symbols/mention-selection]]、[[symbols/queue-finish]]、[[symbols/queue-store]]、[[concepts/delivery-state]]、[[concepts/development-baseline]]、[[concepts/group-identity-evidence]]、[[concepts/identity-authority]]、[[concepts/message-pipeline]]、[[concepts/model-error-contract]]、[[concepts/unread-capture-retry]]、[[concepts/voice-asset-binding]]

## [2026-11-04] change | 网页预设语音工具与一次授权实机验证

来源：[[raw/changes/2026-11-04-index-tts-skill]]

手工创建记录补登记；28 个关联词条已完成源码/契约核对与入库。局部 22 项通过，较大范围回归保留 2 项既有失败；一次真实发送的个人运行数据不入图谱。


## [2026-11-04] change | 联系人配置加入 IndexTTS 授权与语音设置

来源：[[raw/changes/2026-11-04-contact-index-tts]]

## [2026-11-04] ingest | 联系人配置加入 IndexTTS 授权与语音设置联动

来源：[[raw/changes/2026-11-04-contact-index-tts]]

[[modules/dashboard]]、[[modules/web]]、[[modules/wiki]]、[[apis/dashboard-voice-assets]]、[[apis/index-tts]]、[[concepts/development-baseline]]


## [2026-11-04] change | 网页音色预设列表与联系人默认绑定

来源：[[raw/changes/2026-11-04-webui-preset-binding]]

## [2026-11-04] ingest | 网页音色预设列表与联系人默认绑定

来源：[[raw/changes/2026-11-04-webui-preset-binding]]

[[modules/butler]]、[[modules/dashboard]]、[[modules/delivery]]、[[modules/identity]]、[[modules/plugin]]、[[modules/web]]、[[modules/wiki]]、[[apis/dashboard-knowledge]]、[[apis/dashboard-queue]]、[[apis/dashboard-voice-assets]]、[[apis/dashboard-workflow]]、[[apis/index-tts]]、[[tables/knowledge-vault]]、[[concepts/development-baseline]]、[[concepts/identity-authority]]


## [2026-11-04] change | 网页预设图谱契约说明补充

来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]

## [2026-11-04] ingest | 网页预设图谱契约说明补充

来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]

[[modules/butler]]、[[modules/dashboard]]、[[modules/delivery]]、[[modules/identity]]、[[modules/plugin]]、[[modules/web]]、[[modules/wiki]]、[[apis/dashboard-knowledge]]、[[apis/dashboard-queue]]、[[apis/dashboard-voice-assets]]、[[apis/dashboard-workflow]]、[[apis/index-tts]]、[[tables/knowledge-vault]]、[[concepts/development-baseline]]、[[concepts/identity-authority]]

## [2026-11-05] change | 修复联系人策略保存锁等待与不可见旧技能

来源：[[raw/changes/2026-11-05-contact-policy-save]]

## [2026-11-05] ingest | 修复联系人策略保存锁等待与不可见旧技能

来源：[[raw/changes/2026-11-05-contact-policy-save]]

[[apis/dashboard-contact-policy]]、[[modules/identity]]、[[modules/dashboard]]、[[modules/web]]、[[apis/index-tts]]、[[apis/dashboard-voice-assets]]、[[concepts/development-baseline]]

## [2026-11-05] change | 修复群聊越屏采集与自动语音回复链路

来源：[[raw/changes/2026-11-05-group-auto-voice]]

## [2026-11-05] ingest | 修复群聊越屏采集与自动语音回复链路

来源：[[raw/changes/2026-11-05-group-auto-voice]]

[[modules/delivery]]、[[modules/wiki]]、[[modules/wxbot]]、[[apis/dashboard-voice-assets]]、[[apis/index-tts]]、[[symbols/mention-selection]]、[[symbols/model-worker]]、[[tables/queue-outbox]]、[[concepts/automatic-voice-reply]]、[[concepts/capture-viewport]]、[[concepts/delivery-state]]、[[concepts/development-baseline]]、[[concepts/group-identity-evidence]]、[[concepts/message-pipeline]]、[[concepts/model-error-contract]]、[[concepts/unread-capture-retry]]、[[concepts/voice-asset-binding]]

## [2026-11-05] ingest | 新消息补建联系人窗口与移除会话 IndexTTS 专区

来源：[[raw/changes/2026-11-05-contact-enrollment-and-tts-ui]]

[[modules/identity]]、[[concepts/message-pipeline]]、[[symbols/butler-handle]]、[[modules/web]]、[[apis/index-tts]]、[[apis/dashboard-contact-policy]]、[[apis/dashboard-voice-assets]]、[[apis/butler-handle]]、[[concepts/development-baseline]]、[[concepts/group-identity-evidence]]、[[concepts/model-error-contract]]、[[modules/butler]]、[[modules/wiki]]、[[symbols/butler-result]]

## [2026-11-05] ingest | 为停用的群成员身份增加启用按钮

来源：[[raw/changes/2026-11-05-enable-group-binding]]

[[apis/dashboard-contact-policy]]、[[apis/index-tts]]、[[modules/identity]]、[[modules/web]]
