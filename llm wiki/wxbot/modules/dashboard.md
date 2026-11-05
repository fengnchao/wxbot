---
type: module
module: dashboard
summary: 聚合运行事实，读取队列不初始化或迁移数据库
coverage: overview
last_verified: '2026-11-05'
sources:
- path: src/dashboard/api/tts_presets.py
  line: 6
  anchor: 'def _known_contact(ctx, contact):'
- path: src/dashboard/routes.py
  line: 59
  anchor: ("GET", "/api/voice-assets", voice_assets.list_assets),
- path: src/dashboard/api/voice_assets.py
  line: 15
  anchor: 'def list_assets(ctx):'
- path: src/dashboard/routes.py
  line: 32
  anchor: ROUTES = (
- path: src/dashboard/queue_view.py
  line: 15
  anchor: 'class QueueView:'
- path: src/dashboard/workflow_view.py
  line: 41
  anchor: 'class WorkflowView:'
- path: src/dashboard/config_view.py
  line: 95
  anchor: 'class ConfigView:'
- path: src/dashboard/config_editor.py
  line: 153
  anchor: def _access_changes(
- path: src/dashboard/api/knowledge.py
  line: 54
  anchor: 'def extract_status(ctx):'
- path: src/dashboard/knowledge_template_view.py
  line: 27
  anchor: 'class KnowledgeTemplateView:'
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-model-access-switch
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-policy-save
depends_on:
- modules/common
---
# 管理台 HTTP 与投影

联系人表单的 IndexTTS 授权仍复用 /api/skills、/api/contacts 与语音绑定接口；网页预设列表/默认选择现由新增 GET/POST /api/tts-presets 适配 Butler 业务服务。角色与技能仍由 ContactAdmin._policy 的服务端目录验证，UI 勾选不是执行能力；多源保存边界与前端消费者见 [[apis/index-tts]]。新接口需使用者手动重启管理台加载，无新表或迁移。

## 范围与入口

`src/dashboard/`：server 组装 HTTP 服务，http 负责传输、鉴权/同源和静态文件；routes.ROUTES 是单张路由表；api 只做胶水，view/action 承担投影与明确动作。

## 对外接口及消费方

[[apis/dashboard-workflow]] 被 [[modules/web]] 的 WorkflowView 消费；[[apis/dashboard-queue]] 被 QueueView 消费。数据库是 [[modules/wxbot]] 的队列，视图使用 SQLite `mode=ro`；GET 不允许初始化、迁移或恢复。

[[apis/dashboard-knowledge]] 同属只读投影，但读的是 Butler 侧的 [[tables/kb-episodes]]（L1 原文）与 [[tables/kb-facts]]（L2 事实），枚举靠 [[tables/kb-owners]]。`KnowledgeView` 先读索引库列人；索引库缺失或损坏时退回扫目录，从各库内的 `distinct owner` 反推。每个库都用 `mode=ro` 打开，**不建库不建表**：默认就没有历史，空态不是错误。

同一词条里还有自动提炼两条：`GET /api/knowledge/extract`（`src/dashboard/routes.py:45`）把 Butler 的调度器状态包一层 `available` 转发给页面，Butler 不可达只是 `available: false`；`POST /api/knowledge/extract`（`:67`）只做参数收拢再转给 Butler（`api/support.py:172`），**管理台自己不跑模型、不写库**。两条都受 `BUSINESS_GET` / `BUSINESS_POST` 门禁（`routes.py:18`、`:25`），非本机部署返回 503。

知识模板两条：`GET /api/knowledge/template`（`:46`）只读返回生效模板、覆盖层内容与逐行错误；`POST /api/knowledge/template`（`:68`）交 `KnowledgeTemplateView`（`knowledge_template_view.py:27`）处理 `validate` / `save` / `reset`。写路径不指定路径，固定落在 `data/knowledge/template.md`，复用 `config_lock`、sha256 版本比对、写前备份与原子替换；同样受 `BUSINESS_GET` / `BUSINESS_POST` 门禁，非本机 503。

两个视图都不写库：事实上游是 Butler 的调度器（[[symbols/knowledge-auto]] → [[symbols/knowledge-extract]]），管理台只负责展示，外加把「立即提炼」转发给 Butler 一次。

## 边界与缺口

写操作需专用动作头、JSON、明确 acknowledge、可信 Host 和同源；队列写操作和联系人写操作不在本批接口词条范围。身份管理归 [[modules/identity]]，不是页面自行授予。配置与业务操作细节仍见 README 和实际处理器。

配置投影的 `model_access` 是页面唯一的接入方式来源：`current` 由 `config_schema.access_provider()` 推导（`[model].provider` 优先，否则按 `[agent].provider` 回退），`fields` 与 `notes` 覆盖全部接入方式。保存时 `config_editor._access_changes()` 把接入方式展开成 `[agent].provider` 和 `[model].backend` 再落盘，Codex 用 `op:default` 删掉多余协议字段，因此三个字段不会各行其是。

## 代码依据

- `src/dashboard/routes.py:28` — `ROUTES = (`
- `src/dashboard/queue_view.py:15` — `class QueueView:`
- `src/dashboard/workflow_view.py:41` — `class WorkflowView:`
- `src/dashboard/config_view.py:95` — `class ConfigView:`
- `src/dashboard/config_editor.py:153` — `def _access_changes(`
- `src/dashboard/api/knowledge.py:54` — `def extract_status(ctx):`
- `src/dashboard/knowledge_template_view.py:27` — `class KnowledgeTemplateView:`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

[[raw/changes/2026-10-31-model-access-switch]]

[[raw/changes/2026-11-01-knowledge-episodes]]

[[raw/changes/2026-11-01-knowledge-sharding]]

[[raw/changes/2026-11-01-knowledge-auto]]

[[raw/changes/2026-11-02-knowledge-graph-template]]

## 音色资产 API

- [[apis/dashboard-voice-assets]]：资产 CRUD、参考音预览、会话绑定写 config.wxbot.toml。



## 联系人语音配置核对

[[raw/changes/2026-11-04-contact-index-tts]]：新增会话授权控件与原接口消费，源码位置已核对；后端契约保持。


## 联系人语音配置核对

[[raw/changes/2026-11-04-webui-preset-binding]]：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [[apis/index-tts]]。


图谱契约说明来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]。


## 策略保存复核（2026-11-05）

联系人策略保存的事务外目录校验、事务内版本复查及未安装技能的显式取消入口见 [[apis/dashboard-contact-policy]]。保留原角色与工具权限规则，无数据库迁移，不自动删除已有技能引用。来源 [[raw/changes/2026-11-05-contact-policy-save]]。
