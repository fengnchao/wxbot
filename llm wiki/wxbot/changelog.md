
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
