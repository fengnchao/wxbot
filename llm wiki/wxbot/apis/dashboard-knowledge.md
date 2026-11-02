---
type: api
module: dashboard
summary: 对话原文与知识图谱事实的只读查询，外加自动提炼的状态只读与一次手动触发转发，vault 不存在时返回空态而不是错误
coverage: core
last_verified: '2026-11-01'
sources:
- path: src/dashboard/routes.py
  line: 43
  anchor: '"GET", "/api/knowledge", knowledge.read'
- path: src/dashboard/routes.py
  line: 44
  anchor: '"GET", "/api/knowledge/facts", knowledge.facts'
- path: src/dashboard/routes.py
  line: 45
  anchor: '"GET", "/api/knowledge/extract", knowledge.extract_status'
- path: src/dashboard/routes.py
  line: 66
  anchor: '"POST", "/api/knowledge/extract", knowledge.extract_trigger'
- path: src/dashboard/api/knowledge.py
  line: 10
  anchor: 'def _view(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 16
  anchor: 'def _session(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 25
  anchor: 'def read(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 36
  anchor: 'def facts(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 47
  anchor: 'def extract_status(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 57
  anchor: 'def extract_trigger(ctx):'
- path: src/dashboard/knowledge_view.py
  line: 22
  anchor: 'class KnowledgeView:'
- path: src/dashboard/knowledge_view.py
  line: 32
  anchor: 'def owners(self, kind=''episodes''):'
- path: src/dashboard/knowledge_view.py
  line: 46
  anchor: 'def read(self, owner='''', query='''', limit=50, offset=0, contact='''',
    channel_type=''''):'
- path: src/dashboard/knowledge_view.py
  line: 60
  anchor: 'def facts(self, owner='''', query='''', limit=50, offset=0, contact=''''):'
- path: src/butler/runtime/knowledge_store.py
  line: 596
  anchor: 'def read(self, owner='''', query='''', limit=50, offset=0, contact='''',
    channel_type=''''):'
- path: src/butler/runtime/knowledge_store.py
  line: 625
  anchor: 'def facts(self, owner='''', query='''', limit=50, offset=0, contact=''''):'
- path: src/butler/runtime/knowledge_store.py
  line: 663
  anchor: 'def sessions(self, owner, kind=''episodes''):'
- path: web/src/views/KnowledgeView.vue
  line: 61
  anchor: const payload = await apiGet('/api/knowledge?' + params.toString())
- path: web/src/views/FactsView.vue
  line: 100
  anchor: const payload = await apiGet('/api/knowledge/facts?' + params.toString())
- path: web/src/views/FactsView.vue
  line: 113
  anchor: async function loadExtract() {
- path: src/dashboard/api/support.py
  line: 172
  anchor: 'def trigger_butler_extract(config, payload):'
- path: src/butler/server.py
  line: 141
  anchor: 'if self.path == ''/v1/knowledge/extract'':'
- path: src/butler/server.py
  line: 342
  anchor: started, reason = extract.trigger(owner=owner, batch=batch, dry_run=dry_run)
changes:
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-migrate-source-recheck
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-01-knowledge-atomic-retry
---
# GET /api/knowledge、/api/knowledge/facts 与自动提炼两条

## 方法、路径与鉴权

四条路由，三条只读、一条只转发：

| 方法 | 路径 | 处理器 | 性质 |
|---|---|---|---|
| GET | `/api/knowledge` | `api.knowledge.read` | 只读 |
| GET | `/api/knowledge/facts` | `api.knowledge.facts` | 只读 |
| GET | `/api/knowledge/extract` | `api.knowledge.extract_status` | 只读，转问 Butler |
| POST | `/api/knowledge/extract` | `api.knowledge.extract_trigger` | 只转发，不等结果 |

前两条**没有对应的 POST**：原文与事实的写入只在 Butler 侧，管理台连写路径都没有（`src/dashboard/routes.py:43`/`:44`）。

第三条的 POST（`routes.py:66`）不碰任何 vault：它把请求转给 Butler 的 `/v1/knowledge/extract`，真正的提炼在 Butler 的后台线程里跑（[[symbols/knowledge-auto]]），HTTP 只拿 202。

四条都走 [[modules/dashboard]] HTTP 的访问控制：GET 三条在 `BUSINESS_GET` 里（`routes.py:17`、`:18`），POST 在 `BUSINESS_POST`（`:25`），所以非本机安装（由对端维护业务的部署）一律 503，与 `/api/queue` 同一套门禁（`src/dashboard/http.py:217`）。

## 请求字段（类型、必填、默认、校验）

| 参数 | 类型/默认 | 校验 |
|---|---|---|
| owner | 字符串，默认空 | 精确匹配身份稳定键（`user:<uuid>` / `anon:dm:101`）；空表示不过滤。在目录行上做内存过滤，不进文件扫描之外的任何查询 |
| q | 字符串，默认空 | 原文：`user_text` 或 `reply_text` 的**大小写不敏感子串**；事实：`fact_key` 或 `fact_value` 的子串。都是内存匹配，没有 LIKE 注入面 |
| limit | 整数，默认 50 | 夹在 1..200 |
| offset | 整数，默认 0 | 负数归零 |
| contact | 字符串，默认空 | 精确匹配日记块的 `contact` / 节点 frontmatter 的 `contact`；空表示不缩 |
| channel_type | `dm` / `group`，默认空 | 与 `contact` 组合定位一个会话；**只对原文生效**，事实节点没有这一列。`_session(ctx)`（`api/knowledge.py:16`）只认这两个值，其余当没填 |

参数全部当不可信输入处理。

### 自动提炼两条的请求与响应

| 方法 | 路径 | 请求体 | 响应 |
|---|---|---|---|
| GET | `/api/knowledge/extract` | 无 | `{available: true, ...status}` 或 `{available: false, error}` |
| POST | `/api/knowledge/extract` | 可选 `{owner?, batch?, dry_run?}` | `202 {ok, status}` / `400` / `409` 忙 / `503` 转发失败 |

GET 的字段全部来自 Butler 的 `ExtractScheduler.status()`（`src/butler/server.py:141`）：`enabled`、`knowledge_enabled`、`auto_extract`、`auto_prune`、`interval_minutes`、`batch`、`max_owners`、`min_backlog`、`idle_seconds`、`next_run_at`、`last_run_at`、`last_report`、`failures`、`last_error`、`next_prune_at`。管理台**不解析数据目录、不读状态文件**，只把 Butler 的回答包一层 `available`（`api/knowledge.py:47`）。

Butler 不可达时**不是错误**：`fetch_butler_data` 抛的 `RuntimeError`（以及非本机模式的 `ValueError`）被折成 `200 {available: false, error}`，页面显示一行提示并隐藏按钮（`api/knowledge.py:51`）。理由和 vault 不存在一致——这一侧看不到，不等于业务坏了。

POST 的校验在 Butler 侧：`owner` 去空白后上限 200 字符，`batch` 必须是整数并夹在 `1..200`，`dry_run` 必须是布尔（`src/butler/server.py:329`、`:334`、`:339`）；任一不合法回 400，管理台原样透传（`api/knowledge.py:73`）。正在跑一轮时 `trigger()` 返回 `busy`，映射成 409，**不排队**（`server.py:343`）；成功只回 `202 {ok: true, status: 'started'}`，不等模型。转发本身失败（连不上、超时、没配 token、非本机模式）回 503 且 `ok: false`（`api/knowledge.py:71`）。

`dry_run` 在这里也允许：它让 Butler 只读 vault 不写入、不留状态，供排查用；管理台按钮不传它。

## 响应字段与错误语义

两条响应同形：

```
{available, owners[], rows[], total, limit, offset, has_more}
```

`owners` 每项 `{owner, name, contact, channel_type, episodes, facts, last_at, sessions}`，**恒为全量**（不受 owner 会话筛选影响），供页面左栏列出可筛选的人。`sessions` 是 `[{contact, channel_type, count}]`，按条数倒序，列出这个人在哪些会话里留下过数据；原文页取自日记文件，事实页只按 `contact` 分且 `channel_type` 恒为空字符串。`slug` 不返回——那是内部目录名。

原文行有 7 个字段 `owner` / `at` / `contact` / `channel_type` / `user_text` / `reply_text` / `outcome`（`EPISODE_FIELDS`，`knowledge_view.py:12`）；`request_id` 是内部去重键，只在写侧出现。

事实行有 10 个字段 `owner` / `contact` / `kind` / `fact_key` / `fact_value` / `quote` / `episode_at` / `confidence` / `source` / `created`（`FACT_FIELDS`，`knowledge_view.py:13`）。`kind` 的取值域是七类：`profile` / `preference` / `personality` / `goal` / `relation` / `event` / `topic`（`FACT_KINDS`，`knowledge_store.py:45`），越界值在写入时就回落成 `topic`，所以接口只会看到这七个。`KnowledgeStore.facts` 还多算一个 `node`（这条事实挂在哪个实体节点上），但投影层按白名单裁剪，**当前不对外返回**——前端因此看不到事实归属的节点名。

**vault 不存在不是错误**：`read` / `facts` 先看目录里有没有人，`self._entries()` 为空直接返回 `_empty()`（`available: false` 加空数组），**绝不创建目录、绝不写文件**。只有真正读不动（`OSError`）才抛 `RuntimeError`，由 api 层折成 `500` 且带 `read_only: true`，形状与 [[apis/dashboard-queue]] 一致。

## 实现链（路由→服务→符号）

`routes.ROUTES` → `api.knowledge.read` / `.facts` → `_view(ctx)`（`api/knowledge.py:10`）用 `ctx.butler_config_path()` 载入 [[modules/butler]] 的配置拿 `data_path()`，拼出 `data/knowledge` 目录 → `ctx.KnowledgeView(root)`。

`KnowledgeView`（`src/dashboard/knowledge_view.py:22`）**不再自己解析存储格式**，只持有一个 `KnowledgeStore(root)`：

- `owners(kind)`（`:32`）把 `store.owners()` 的目录行补上 `sessions`：原文页传 `'episodes'`，事实页传 `'facts'`，分别落到 `KnowledgeStore.sessions`（`knowledge_store.py:663`）的两条统计分支。一个人可以同时在私聊和几个群里说过话，所以左栏按人一行、不按会话拆行。
- `read`（`:46`）/ `facts`（`:60`）直接转发给 `KnowledgeStore.read`（`:596`）/ `.facts`（`:625`），再用 `EPISODE_FIELDS` / `FACT_FIELDS` 白名单裁字段。跨 vault 归并、分页、排序全在 store 里，接口层不做二次计算。

这条委托链是改版的重点：存储从三张 SQLite 表换成人一个 vault，接口层只改了一行构造与两处字段白名单，路由与响应形状一个字没动。

## 数据来源与字段血缘

只读 [[tables/knowledge-vault]]：原文来自 `p-*/vault/对话/YYYY-MM-DD.md`，事实来自 `p-*/vault/{人物,组织,话题}/*.md`。**没有写入路径**，因此不存在「经过本接口改动数据」的可能。

跨 vault 分页：`KnowledgeStore.read` / `.facts` 遍历所有 vault 收集后再切 `[offset:offset+limit]`——与 SQLite 版的「每库取 offset+limit 再归并」不同，现在是全量收集后切片。原文按 `(at, contact)` 倒序，事实按 `(created, node)` 倒序。

`at` / `created` 都来自日记块与事实行注释里的时间戳；`episode_at` 是提炼那批原文的**第一条**时间，供界面标注「基于哪段时间的对话」。

## 前端消费点（文件+函数）

[[modules/web]] 的两个页面共用 `knowledge.css`：

- `KnowledgeView.vue`（对话记录）：`load()` 用 `apiGet('/api/knowledge?...')`（`:61`）拉取，页大小固定 50；左栏渲染 `owners`，点人写入 `owner` 筛选；选定的人有多个会话时，标题下出现一行会话 chips（`:154`，`全部会话` 加每个 `sessions[i]`），点击写入 `contact` + `channel_type`，换人时清空；关键词取导航壳共享搜索框并防抖；`badgeOf(row)` 把 `outcome` 映射成「本轮失败 / 未回复 / 群聊 / 私聊」。
- `FactsView.vue`（知识库）：`apiGet('/api/knowledge/facts?...')`（`FactsView.vue:100`）；六列 时间 / 联系人 / 类型 / 事实 / 原话 / 置信，`kind` 映射成七类中文（身份背景 / 偏好习惯 / 性格 / 目标 / 关系 / 约定事件 / 关注话题），置信度百分比，低于 50% 的行降权并计数。会话 chips 形状相同（`:250`），但只写 `contact`——事实没有 `channel_type`，同名群聊与私聊在这一页分不开。
- 自动提炼状态条（`FactsView.vue:261`）：`loadExtract()`（`:113`）拉 `/api/knowledge/extract`，`runExtract()`（`:123`）发 POST（`:130`）。一条状态句把开关、上次写入条数、下次时间或失败原因说清，措辞在 `extractLine` 里；`available: false` 时降成 warn 色提示并**隐藏按钮**。触发后 4 秒刷状态、15 秒连表格一起刷、60 秒清掉「已开始提炼」，不在页面上做轮询。

两页左栏副标题都是会话摘要：选定的人一行里直接写「私聊 101、群聊 鸭王集训营」，超过两个会话折成「等 N 个会话」，后面才是条数。会话筛选只缩右栏与计数，不把人从左栏拿走（后端 `owners` 恒为全量）。

两页都在 `available=false` 时显示空态而非报错；左栏项带 `tabindex`/`role="button"` 与键盘处理，`:focus-visible` 有内焦点环。管理台自身没有写路径：知识库页唯一能改状态的是那个「立即提炼」按钮，而它只把一次请求转给 Butler，模型调用与落盘全在对端。

## 测试与风险

本地 `tests/dashboard/test_knowledge_view.py`（13 项）：vault 不存在时 `available=false` 且**不生成目录**、空目录按空态、不返回 `request_id`、筛选分页、同一人的多个会话在 `sessions` 里按条数列出且不拆行、选定人之内按 `contact`+`channel_type` 再筛（同名群与私聊不串）、索引丢失时从 vault 重建、损坏文件抛 `RuntimeError`、相对 `data_dir` 仍能只读打开，以及一条真 HTTP 用例——起真 Handler，断言四条路由：两条只读出数、`owner` 过滤、会话参数直传、非法 `channel_type` 当没填、事实行字段；自动提炼 GET 把 Butler 回答包成 `available: true`、POST 去空白后转发 `owner` 与 `dry_run`、409 原样透传、Butler 不可达时 GET 仍 200 但 `available: false` 而 POST 503；最后把 wxbot 配置切到 `mode=remote` 断言四条全部 503。

Butler 侧的 `GET/POST /v1/knowledge/extract` 由 `tests/butler/test_knowledge_auto.py` 的 `test_http_exposes_status_and_accepts_one_manual_trigger` 覆盖（默认关也能读状态、`batch`/`dry_run`/`owner` 非法各回 400、合法触发 202 且后台自己释放单飞锁、忙时 409）。

`web/scripts/smoke.mjs` 断言两个页面的渲染行数、类型中文、置信度文案与导航标签数（8）。

风险：`q` 与 `owner` 都是内存过滤，**一次请求要遍历所有人的整个 vault**，联系人数量与对话量线性叠加，是 O(全部文件)；左栏的 `sessions` 又给每个 owner 多扫一遍文件，也是 O(人数)；`index.json` 丢失会触发一次全量重建（结果正确但那次请求变慢）；分页顺序不能改成只按时间——同一秒内的多条要靠第二排序键（`contact` / `node`）定序。

## 代码依据与修改来源

- `src/dashboard/routes.py:43` — `("GET", "/api/knowledge", knowledge.read)`
- `src/dashboard/routes.py:44` — `("GET", "/api/knowledge/facts", knowledge.facts)`
- `src/dashboard/routes.py:45` — `("GET", "/api/knowledge/extract", knowledge.extract_status)`
- `src/dashboard/routes.py:66` — `("POST", "/api/knowledge/extract", knowledge.extract_trigger)`
- `src/dashboard/api/knowledge.py:10` — `def _view(ctx):`
- `src/dashboard/api/knowledge.py:16` — `def _session(ctx):`
- `src/dashboard/api/knowledge.py:25` — `def read(ctx):`
- `src/dashboard/api/knowledge.py:36` — `def facts(ctx):`
- `src/dashboard/api/knowledge.py:47` — `def extract_status(ctx):`
- `src/dashboard/api/knowledge.py:57` — `def extract_trigger(ctx):`
- `src/dashboard/knowledge_view.py:22` — `class KnowledgeView:`
- `src/dashboard/knowledge_view.py:32` — `def owners(self, kind='episodes'):`
- `src/dashboard/knowledge_view.py:46` — `def read(self, owner='', query='', limit=50, offset=0, contact='', channel_type=''):`
- `src/dashboard/knowledge_view.py:60` — `def facts(self, owner='', query='', limit=50, offset=0, contact=''):`
- `src/butler/runtime/knowledge_store.py:596` — `def read(self, owner='', query='', limit=50, offset=0, contact='', channel_type=''):`
- `src/butler/runtime/knowledge_store.py:625` — `def facts(self, owner='', query='', limit=50, offset=0, contact=''):`
- `src/butler/runtime/knowledge_store.py:663` — `def sessions(self, owner, kind='episodes'):`
- `web/src/views/KnowledgeView.vue:61` — `const payload = await apiGet('/api/knowledge?' + params.toString())`
- `web/src/views/FactsView.vue:100` — `const payload = await apiGet('/api/knowledge/facts?' + params.toString())`
- `web/src/views/FactsView.vue:113` — `async function loadExtract() {`
- `src/dashboard/api/support.py:172` — `def trigger_butler_extract(config, payload):`
- `src/butler/server.py:141` — `if self.path == '/v1/knowledge/extract':`（GET）
- `src/butler/server.py:342` — `started, reason = extract.trigger(owner=owner, batch=batch, dry_run=dry_run)`（POST）

[[raw/changes/2026-11-01-knowledge-episodes]]
[[raw/changes/2026-11-01-knowledge-sharding]]
[[raw/changes/2026-11-01-knowledge-sessions]]
[[raw/changes/2026-11-01-knowledge-auto]]
[[raw/changes/2026-11-01-knowledge-vault-graph]]
[[raw/changes/2026-11-01-knowledge-atlas-index]]
[[raw/changes/2026-11-01-knowledge-atomic-retry]]
