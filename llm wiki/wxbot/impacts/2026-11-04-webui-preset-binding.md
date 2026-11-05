---
type: impact
status: verified
date: '2026-11-04'
---
# 联系人选择网页音色预设

## 根因与已确认需求

ContactDialog 的 voiceAssets 只读 /api/voice-bindings，后者返回 Butler 本地 VoiceAssetStore；网页已保存的预设由 Gradio.refresh_preset_choices 提供，两者没有连接。上一轮仅新增技能授权，未提供网页预设选择，因此用户已有网页预设仍无法选到。

在现有 IndexTTS 区域新增独立的网页音色预设下拉/刷新，保存为当前会话默认值。自动回复音色资产保留原用途。调用工具省略 preset 时使用绑定，显式 preset 优先；其他设置仍为网页默认。

## 文件、契约与血缘

- Butler delivery/tts_presets.py 持有按会话保存的预设名、乐观版本及原子配置写入，文件位于本安装 data/tts-presets.json；不复制预设音频或高级参数。TTSService 在服务端身份上下文中解析默认预设，幂等指纹按原请求参数固定，避免重试时绑定变化导致重复发送。
- dashboard/api/tts_presets.py 增加 GET/POST /api/tts-presets，纳入本地 BUSINESS 门；POST 需同源 X-Wxbot-TTS-Action，目标必须是现有联系人，非空预设先对照网页实时列表，版本冲突 409。
- tools.py 仍只有 text/preset，preset 改为可省略（需存在绑定）；只读仍仅列表，不准生成。tts_presets 返回当前会话 default_preset。Skill 明确默认值与显式覆盖。
- ContactDialog 读取并保存 preset/version/contact 快照，未改不写、目录不可达保留旧绑定、重命名复制到新会话、部分保存明确提示；接口故障时不清空默认值。
- 更新 Vue 烟测、web/dist、README 与图谱，无新表/迁移，不改系统设备，不自动重启服务，不额外真人测试发送。

## 实施与验证

先失败后通过：绑定持久化/版本/隔离、未知预设/网页不可达、默认音色生成与显式覆盖及重复请求；Dashboard 路由/同源确认/未知联系人；构建后的下拉默认值/刷新/保存/部分失败。真实网页只读列预设验证；保持 Hallmark 原位范围，实际路由渲染与新控件检查。最后独立复核与图谱 ingest/lint。

## 完成验证

构建及全站 Vue 烟测通过，管理台/语音相关 256 项回归通过。独立复核的两项 P2 已通过失败→通过回归闭环：停用目标改读完整会话；等待期间目标/选项变化由提交快照、稳定 ID 返回目标和保存禁用控制。配置提交结果来自锁内版本，不在释放锁后重读。

真实 WebUI 只读查询可列出用户已有预设；实际构建的假数据路由验证了默认选中值、选项来源、桌面/375px 显示、边框对比度 5.16-5.80 和键盘焦点，Hallmark 静态无 FAIL/WARN，全页既有样式发现保留。运行中管理台尚未加载新接口，用户选择稍后自行重启管理台/Butler，未自动重启、未保存真实绑定、未新增真人发送。图谱记录 [[raw/changes/2026-11-04-webui-preset-binding]] 入库 15 页，lint 剩原有 4 项待办。
