---
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
---
# 网页预设绑定与默认音色

## 目标与背景

用户已有网页预设，但联系人里的自动回复音色列表只来自本地 VoiceAssetStore。上一轮只增加授权开关，未接网页预设列表。本次在 IndexTTS 区域新增独立的网页预设下拉、刷新和默认绑定；只局部更正 supersedes 记录中“无联系人默认预设”“preset 必填”和“无新增后端接口”的结论，其余权限、其他生成默认值、分段和投递契约保留。旧 raw 不修改。

## 文件与代码位置

- src/butler/delivery/tts_presets.py：PresetBindings，由 Butler 业务持有按会话存储，实时列表、版本检查、锁内原子写入/返回本次提交结果。
- src/butler/delivery/tts.py：生成在当前服务身份中解析默认值，显式覆盖优先；幂等按原始参数固定，先复用旧操作再读默认，配置变化/清除不重发旧任务。
- src/butler/agent/tools.py：tts_generate 的 preset 可省略，tts_presets 返回当前会话 default_preset；身份/只读/动态授权边界不变。
- src/dashboard/api/tts_presets.py、routes.py：新增本地管理端适配，确认头、完整联系人存在性和版本冲突；停用会话也可配置。
- web/src/components/ContactDialog.vue、styles/contacts.css：网页预设读取/保留/刷新/绑定，部分失败留窗；提交前冻结目标及选项，响应中按稳定会话 ID 找规范化名称，后续设置不能串写其他联系人；保存期间禁用所有可编辑字段。
- plugins/butler-wechat/skills/tools/index-tts/SKILL.md：默认值与显式覆盖说明；web/scripts/smoke.mjs 与 web/dist 配套；README 和图谱更新。具体稳定锚点见 [[apis/index-tts]] sources。

## 接口与字段

GET /api/tts-presets?contact=... → ok/presets[]/preset/version/available/error。网页不在线仍返回保存值和修订，不把本地资产当网页预设。POST /api/tts-presets 精确接收 contact/preset/version，需同源 X-Wxbot-TTS-Action，纳入本地 BUSINESS 门；非空预设必须仍在网页列表，空值清除。未知目标/预设 400，未确认 403，修订冲突 409，存储 I/O 错误 503。

联系人校验使用完整 ContactStore.conversations，不能使用仅含启用路线的投影。旧自动回复本地资产接口保持原契约。工具仍只接 text/preset，preset 可省略且仅在当前会话有默认时成功；显式值优先。工具结果记录实际使用的 preset，未知/失效默认不自动换声。

## 数据库与迁移

无新表/列/迁移。Butler data_dir/tts-presets.json 保存 {version:1,presets:{会话名:预设名}}，文件 version 是格式版本；API version 为规范化内容 SHA256 修订值。网络查询不持锁；配置锁内复查版本、合并映射、临时文件 fsync/replace，写失败保留旧文件，不复制预设音频或高级参数。默认变化不影响已登记 operations 的原参数幂等。

## 前端消费点

联系人 → 基本资料 → 会话设置 → IndexTTS → 网页音色预设。与自动回复音色资产分开。GET 失败或网页断开保留旧选择；未改不写、重命名复制；保存失败明确哪些设置已完成，保留弹窗以新版本重试。新增控件使用既有主题、焦点/禁用和可访问性状态。

保存期间冻结表单目标、模式、资产、预设与授权，按联系人响应的稳定 ID/规范化名继续；缺少目标即停止后续写入。禁用窗口可配置预设；绑定本身不授予工具执行权限，也不自动启用语音模式或设备。

## 测试与异步任务

先失败后通过的测试覆盖绑定隔离、默认/显式覆盖、默认改变或清除后的幂等、版本冲突、网页断开、未知预设、原子写失败、管理端确认/未知/停用联系人和工具身份。实际 Vue 烟测覆盖列表来源、保存/刷新、旧绑定保留、未改不写、部分失败/重试、重命名，以及延迟联系人响应期间强改目标/模式/预设仍只保存提交快照。

独立审阅发现两项 P2（停用联系人投影与等待期间目标可变），均补失败→通过回归，复核闭环。构建、全站烟测与管理台/语音回归通过；Skill 格式验证及 Hallmark 新组件静态检查通过，真实构建路由的桌面/375px 下拉、对比度、焦点和无横向溢出检查通过。全页仍有既有背景控件/字号/卡片等样式发现，未扩大本次修整。

已只读确认真实 WebUI 可列出用户已有预设；没有保存或复制真实用户配置、没有额外真实音频发送。无新增业务调度任务。

## 风险与回滚

当前运行服务尚未加载新接口，用户明确选择稍后手动重启；实际页面待管理台与 Butler 重启后加载。配置按安装自己的 data_dir 读取，不能从另一安装复制。部分保存不是跨文件/数据库原子事务，失败保留弹窗并说明范围。预设删除/网页不可达必须刷新/重选，不自动猜测其他声线。回退新接口、默认解析、前端和 Skill 可移除扩展，不删已生成音频或配置。临时只读预览在验证后关闭，既有服务未重启。
