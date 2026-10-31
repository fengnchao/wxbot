# 建档覆盖范围

首批建档日期：2026-10-31。基于当时**当前工作树**，其中包含用户已有未提交修改；这里只描述核对过的结构，不编造这些改动的历史验证结果。

## 已建档

- 主要模块职责、入口、依赖和边界，见 [[index]] 的 modules。
- 消息处理：[[apis/butler-handle]]、[[apis/butler-handle-stream]]，含请求/响应字段、wxbot 调用方。
- 最终队列结构：[[tables/queue-inbox]]、[[tables/queue-batches]]、[[tables/queue-outbox]]，结合建表及补列阅读。
- 核心符号/显式调用关系、[[concepts/message-pipeline]]、[[concepts/delivery-state]]、[[concepts/identity-authority]]。
- 管理台读队列接口及 Vue 消费点：[[apis/dashboard-workflow]]、[[apis/dashboard-queue]]。
- 统一模型链路、请求代际热切换和原生工具边界：[[modules/models]]、[[symbols/reloadable-backend]]、[[symbols/local-model-backend]]。

## 待扩展

- 联系人完整业务表、身份合并端点/血缘，目前只有 [[modules/identity]] 概览。
- 提醒/心跳、媒体/新闻、Telegram Bot/桌面中继的详细表与端点。
- 安装配置、全部模型后端的错误/重试契约及其余前端页面。
- 未为每个文件/函数建页；调用关系只声明已核对的关键边，不声称静态分析覆盖全部。
- `tests/` 仅在开发机存在且不入 Git；测试路径作导航，不作为跨安装可用的证据。巡检不读取真实数据。

改到缺口时按 [[guide]] 先查源码、扩展词条，再更新本清单。不能从模块概览推断字段，也不能把“未命中”当成“不存在”。
