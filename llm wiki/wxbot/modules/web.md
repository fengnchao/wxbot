---
type: module
module: web
summary: 共享导航壳和现有请求封装的管理界面
coverage: overview
last_verified: '2026-11-02'
sources:
- path: web/src/router.js
  line: 4
  anchor: 'export '
- path: web/src/api.js
  line: 23
  anchor: 'export '
- path: web/src/views/WorkflowView.vue
  line: 356
  anchor: fetch('/api/workflow',
- path: web/src/views/QueueView.vue
  line: 248
  anchor: apiGet('/api/queue?'
- path: web/src/views/ConfigurationView.vue
  line: 37
  anchor: const backendName =
- path: web/src/views/FactsView.vue
  line: 116
  anchor: async function loadExtract() {
- path: web/src/views/FactsView.vue
  line: 39
  anchor: const kinds = computed(
- path: web/src/views/KnowledgeTemplateView.vue
  line: 43
  anchor: async function load(force = false) {
- path: web/src/views/ConfigurationView.vue
  line: 14
  anchor: '[''contacts'', ''联系人与策略''], [''knowledge'', ''知识库''], [''logging'', ''日志''],
    [''advanced'', ''高级配置'']'
changes:
- raw/changes/2026-11-02-web-global-search-clear
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-switchable-models
- raw/changes/2026-10-31-model-access-switch
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-02-knowledge-graph-template
depends_on:
- modules/dashboard
---
# Vue 管理台

## 范围与依赖

`web/` 是 Vue 3/Vite 管理台；源码 `web/src/`，构建目录 `web/dist/` 由管理台提供 `/app/`。入口/页面注册步骤在根 README。导航由 router.js 和 App.vue 共同登记；请求封装见 api.js。顶栏 `#view-search` 按 tab 保存关键词；有内容时旁显示 `#view-search-clear`（「清空」），只清当前页并回焦；`configuration` / `telegram-relay` 等 `searchHidden` 页两者都不显示。

## API 消费映射

- WorkflowView.vue 的刷新请求消费 [[apis/dashboard-workflow]]，全文和实时事件分别读 workflow-content / workflow-stream；不是直接调用 Butler handle API。
- QueueView.vue 消费 [[apis/dashboard-queue]]；重试/确认已发/丢弃是另外的显式动作，不能把只读投影当成发送成功证据。
- KnowledgeView.vue 消费 [[apis/dashboard-knowledge]] 的 `/api/knowledge`；纯只读，不提供删除、编辑、导出。左栏渲染接口返回的 `owners`（会话摘要、原文数、事实数），点人写入 `owner` 筛选；选定的人有多个会话时，标题下出现会话 chips（全部会话 / 私聊 X / 群聊 Y），点击再写 `contact` 与 `channel_type`；换人清空会话筛选。关键词走顶部分类共享的搜索框，防抖 250ms。
- FactsView.vue 消费同一词条的 `/api/knowledge/facts`；六列表格（时间/联系人/类型/事实/原话/置信），`kind` 映射中文、置信度显示百分比，低于 50% 的行降权并在页脚计数。类型表由接口下发：`kinds`（`FactsView.vue:39`）用响应里的 `kinds[{key, label}]` 建映射，后端新增 kind 不需要改前端；`LEGACY_KINDS`（`:11`）只在旧服务缺字段时兜底，`kindOf`（`:210`）优先用接口标签、再查兜底表。会话 chips 同样只写 `contact`，因为事实没有 `channel_type` 列。两页共用 `web/src/styles/knowledge.css`（含 `.session-bar` 一节）。
- FactsView.vue 顶上还有一条自动提炼状态（`FactsView.vue:264`）：`loadExtract()`（`:116`）读 `/api/knowledge/extract`，一句话说清开关、上次写入条数、下次时间或失败原因；`available: false` 时降成 warn 色并隐藏按钮。`runExtract()`（`:126`）把当前左栏选中的人作为 `owner` 发给 `POST /api/knowledge/extract`，触发后 4s 刷状态、15s 连表格一起刷、60s 清掉反馈，不做轮询。

KnowledgeTemplateView.vue 消费 `/api/knowledge/template`：`load()`（`:43`）读生效模板、摘要与逐行错误；`submit()`（`:72`）发 `validate` / `save` / `reset`，请求带 `version` 与确认头；`save()`（`:107`）/ `reset()`（`:113`）各自先确认。没有修改时保存禁用，没有覆盖层时恢复禁用。见 [[apis/dashboard-knowledge]]。

知识库相关页面都不提供事实的原地编辑：事实的写路径在 Butler（[[symbols/knowledge-auto]] 定时 + 页面转发一次手动触发），管理台只展示与转发；知识模板页只改模板，不读写具体事实。非本机安装模式下 `contacts` / `jobs` / `knowledge` / `facts` / `knowledge-template` / `telegram-relay` 六个标签一起从导航隐藏（`App.vue:47` 的 `hidden` 集合），模板页也不显示全局搜索框（`:67`）。

## 维护约束

UI 修改按根 AGENTS 的 Hallmark 流程，保留现有设计系统；构建和 smoke 后一起交付 dist。配置管理页现在按模型草稿显示适用字段，保存反馈区分模型热生效和需要重启的字段。见 [[modules/models]]；其它页面字段契约仍待建档。

配置页的「模型后端」分类只有一个接入方式下拉（`[model].provider`）。选项中文名与说明来自接口的 `model_access`，页面不维护第二份映射表：`model_access.fields` 决定哪些连接字段显示，`model_access.notes` 显示当前接入方式的说明。`butler.agent.provider` 已移入「高级配置」，避免同一件事出现两个下拉；`model.provider` 行不受兼容降级影响，否则选过 Codex 就无法切回。

配置页左栏分类是页面自己的枚举（`ConfigurationView.vue:12`）；「知识库」是本次新增的一类（`:14`，`categoryOf` 在 `:134` 把 `butler.knowledge` 归进去），用来放 `auto_extract` / `extract_batch` 等 11 个字段。字段行本身仍由后端 `ConfigView.read()` 枚举，中文名与说明来自 `config_schema.LABELS`，页面不另存一份。改动这些字段要重启 Butler 才生效（调度器在 `serve()` 里构造）。

## 代码依据

- `web/src/router.js:4` — `export `
- `web/src/api.js:23` — `export `
- `web/src/views/WorkflowView.vue:356` — `fetch('/api/workflow',`
- `web/src/views/QueueView.vue:248` — `apiGet('/api/queue?'`
- `web/src/views/ConfigurationView.vue:37` — `const backendName =`
- `web/src/views/FactsView.vue:116` — `async function loadExtract() {`
- `web/src/views/FactsView.vue:39` — `const kinds = computed(`（映射来自接口 `kinds`）
- `web/src/views/KnowledgeTemplateView.vue:43` — `async function load(force = false) {`
- `web/src/views/ConfigurationView.vue:14` — `['contacts', '联系人与策略'], ['knowledge', '知识库'], …`

## 入库来源

[[raw/changes/2026-11-02-web-global-search-clear]]

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]


[[raw/changes/2026-10-31-switchable-models]]

[[raw/changes/2026-10-31-model-access-switch]]

[[raw/changes/2026-11-01-knowledge-episodes]]

[[raw/changes/2026-11-01-knowledge-sharding]]


[[raw/changes/2026-11-01-knowledge-sessions]]

[[raw/changes/2026-11-01-knowledge-auto]]

[[raw/changes/2026-11-01-knowledge-atlas-index]]

[[raw/changes/2026-11-02-knowledge-graph-template]]
