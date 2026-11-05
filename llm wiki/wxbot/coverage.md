# 建档覆盖范围

首批建档日期：2026-10-31。基于当时**当前工作树**，其中包含用户已有未提交修改；这里只描述核对过的结构，不编造这些改动的历史验证结果。

## 已建档

- 网页预设动态列表、联系人默认绑定及可选工具音色参数，见 [[apis/index-tts]]；区分本地自动回复资产，含保存快照、防串写、停用联系人、修订冲突与原子 JSON 配置。

- 联系人会话的 IndexTTS 授权开关、现有策略继承/局部变更与语音设置保存边界，见 [[apis/index-tts]]、[[modules/web]]；无新后端接口。

- 网页音色预设工具、同会话 Gradio 队列、分段标准 WAV、鉴权音频编号、语音包入队/发送状态及原自动音色绑定例外，见 [[apis/index-tts]]。

- 音色页单内容区、加载/空/失败/有数据展示、字段血缘与响应式约束，见 [[modules/web]]、[[apis/dashboard-voice-assets]]；后端契约保持不变。

- 开发工作树与解释器基线、现行配置与依赖来源、生产后端与旁路的层级、历史布局边界，见 [[concepts/development-baseline]]；不记录真实配置或运行进程状态。
- 主要模块职责、入口、依赖和边界，见 [[index]] 的 modules。
- 消息处理：[[apis/butler-handle]]、[[apis/butler-handle-stream]]，含请求/响应字段、wxbot 调用方。
- 最终队列结构：[[tables/queue-inbox]]、[[tables/queue-batches]]、[[tables/queue-outbox]]，结合建表及补列阅读。
- 核心符号/显式调用关系、[[concepts/message-pipeline]]、[[concepts/delivery-state]]、[[concepts/identity-authority]]。
- 管理台读队列接口及 Vue 消费点：[[apis/dashboard-workflow]]、[[apis/dashboard-queue]]。
- 统一模型链路、请求代际热切换和原生工具边界：[[modules/models]]、[[symbols/reloadable-backend]]、[[symbols/local-model-backend]]。
- 模型失败的跨层契约（脱敏、`retry_safe` 来源、自动重试上限、超时放行）：[[concepts/model-error-contract]]。
- 群提及的两段验证与回退清理链（含 uiautomation 特殊键名约束）：[[symbols/mention-selection]]。
- 未读采集的重试退避、放弃出口及与 `pending_sessions`／`prepare` 的关系：[[concepts/unread-capture-retry]]。
- 用户知识库的 vault 存储形态、文件格式、迁移路径：[[tables/knowledge-vault]]；提炼链路 [[symbols/knowledge-extract]]、调度与游标 [[symbols/knowledge-auto]]；管理台只读投影：[[apis/dashboard-knowledge]]。三张 `kb_*` 平表已退场，留档页保留迁移说明。

## 待扩展

- 联系人完整业务表、身份合并端点/血缘，目前只有 [[modules/identity]] 概览。
- 提醒/心跳、媒体/新闻、Telegram Bot/桌面中继的详细表与端点。
- 安装配置与其余前端页面。
- 单个后端各自的失败细节（Codex 提交边界、Cursor 工作目录、Ollama 完整判据）尚未逐项建页，目前只在 [[concepts/model-error-contract]] 里写了公共部分。
- 未为每个文件/函数建页；调用关系只声明已核对的关键边，不声称静态分析覆盖全部。
- `tests/` 仅在开发机存在且不入 Git；测试路径作导航，不作为跨安装可用的证据。巡检不读取真实数据。

改到缺口时按 [[guide]] 先查源码、扩展词条，再更新本清单。不能从模块概览推断字段，也不能把“未命中”当成“不存在”。
