# 用户知识 vault

用户知识为一人一个 Markdown vault，原文、事实与可重建索引分工明确。旧 kb_* SQLite 表已退场；旧表和迁移设计只在历史材料中保留，运行用知识模板仍在插件内。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 使用说明

- [wxbot / Butler / 知识库](#doc-adb52ac360f25f) · `README.md`

<a id="doc-adb52ac360f25f"></a>

### wxbot / Butler / 知识库

来源：`README.md:614`。

#### 知识库

一个人一个 Obsidian vault：`data/knowledge/p-<slug>/vault/`。节点是 Markdown，关联只靠正文里的
`[[双链]]`，所以用 Obsidian 打开就能在 graph view 里看到这个人的人物、组织、话题和对话原文怎么连起来。

```
data/knowledge/
  index.json                 目录缓存：owner、条数、提炼游标；删掉也能从 vault 重建
  template.md                可选覆盖层：页面保存的知识图谱模板；删除即回到插件内置
  p-<slug>/vault/
    人物/冯草草.md            事实按 kind 分小节：身份 / 偏好 / 关系 / 事件 / 话题
    组织/鸭王集训营.md
    话题/AI 编程.md
    对话/2026-11-01.md       按天记录的原文，事实里可以 [[对话/2026-11-01]] 溯源
```

- 原文（L1）在处理完成时写成当天的 `对话/YYYY-MM-DD.md` 块；事实（L2）由模型从中提炼，
  写成对应节点小节里的一行，行尾 HTML 注释带指纹、key、kind、置信度、来源和原话。
  同一 `kind|key|value` 指纹去重，矛盾的说法各记一条。
- 骨架与提炼口径由模板决定：插件内置一份只读模板（`plugins/butler-wechat/knowledge/graph-template.md`），
  管理台保存的覆盖层 `data/knowledge/template.md` 优先。新增一个节点目录或分类行后，之后新建的 vault
  与下一次提炼立即跟着变；已有节点不迁移，模板里消失的旧分类归入「其他」。内置 6 条安全规则不可删，
  模板的「提炼规则」只能追加在其后。事实行格式是解析契约，不由模板配置。
- 为什么不是表：字段能存进表，节点之间的拓扑存不进；`[[双链]]` 是 Obsidian 唯一认的边。
  为什么一人一个 vault：一个人的数据坏了或整体清空都不牵连别人，图也不会被别人的节点淹没。
  为什么原文也写 Markdown：事实要能点回原话才站得住，按天一个文件把文件数压到每年 365 个。
- 自动提炼：Butler 进程内一个单线程调度器，按 `extract_interval_minutes`（默认 60）扫一遍。
  只有「最近 `extract_idle_seconds`（默认 120）没有新消息」且某人游标之后还有
  `extract_min_backlog`（默认 1）条原文时，才把一批（`extract_batch`，默认 40 条）交给模型；
  一轮最多 `extract_max_owners`（默认 5）人。模型失败按 `extract_retry_minutes` 指数退避，上限 6 小时。
  游标是时间戳，只在整批成功后前移；模型给出空数组也算成功，非 JSON 不前移。
- 关掉 `auto_extract` 不影响 `python -m butler knowledge-extract` 手动跑。`auto_prune` 打开后按
  `prune_interval_hours`（默认 24）清 `retention_days` 之前的原文文件，事实节点不参与清理。
- 单飞：`data/cache/knowledge_extract.lock` 由调度器与 CLI 共用，锁文件超过 30 分钟视为上次进程
  崩溃并回收。状态与审计写在 `data/cache/knowledge_extract_state.json` 和
  `knowledge_extract_audit.jsonl`，只记条数与错误类型，不写原文。
- 提炼使用独立的会话作用域，不占用聊天上下文。对话注入的事实条数由 `KNOWLEDGE_INJECT_FACTS`
  控制（默认 20），`/v1/handle` 前一次性读出来放进提示，不额外多一轮模型调用。
- 写 Markdown 没有事务：先写同目录 `.tmp` 再 `os.replace`，读侧永远看到完整文件。
- 老库升级：`python -m butler knowledge-migrate` 把 SQLite 时代的 `kb_*` 库和遗留 `memory` 表
  搬进 vault，成功后原文件改名留底。这一步是显式的，只在停服后由使用者手动执行。
- 删除联系人档案不删 vault：文件操作不在 SQLite 事务里，回滚会把已写的 Markdown 一起带走。
<!-- end-migrated-part: doc-adb52ac360f25f -->

## 技术资料

- [对话原文、知识事实、自动提炼和知识模板](#doc-17461d21600be6) · `llm wiki/wxbot/apis/dashboard-knowledge.md`
- [knowledge_template](#doc-4656beba355895) · `llm wiki/wxbot/symbols/knowledge-template.md`
- [SQLite kb_episodes（已退场）](#doc-84df4a3514bf20) · `llm wiki/wxbot/tables/kb-episodes.md`
- [SQLite kb_facts（已退场）](#doc-eae62eb158097e) · `llm wiki/wxbot/tables/kb-facts.md`
- [SQLite kb_owners（已退场）](#doc-68c7e63f609bfb) · `llm wiki/wxbot/tables/kb-owners.md`
- [用户知识库：一人一个 Obsidian vault](#doc-dc9956670d38fd) · `llm wiki/wxbot/tables/knowledge-vault.md`

<a id="doc-17461d21600be6"></a>

### 对话原文、知识事实、自动提炼和知识模板

来源：`llm wiki/wxbot/apis/dashboard-knowledge.md:1`。

```yaml
type: api
module: dashboard
summary: 对话原文与知识图谱事实的只读查询、自动提炼的状态与手动触发转发，以及知识模板的读取与校验保存；vault 不存在时返回空态而不是错误
coverage: core
last_verified: '2026-11-06'
sources:
- path: src/dashboard/routes.py
  line: 48
  anchor: '"GET", "/api/knowledge", knowledge.read'
- path: src/dashboard/routes.py
  line: 49
  anchor: '"GET", "/api/knowledge/facts", knowledge.facts'
- path: src/dashboard/routes.py
  line: 50
  anchor: '"GET", "/api/knowledge/extract", knowledge.extract_status'
- path: src/dashboard/routes.py
  line: 78
  anchor: '"POST", "/api/knowledge/extract", knowledge.extract_trigger'
- path: src/dashboard/routes.py
  line: 51
  anchor: '"GET", "/api/knowledge/template", knowledge.template_read'
- path: src/dashboard/routes.py
  line: 79
  anchor: '"POST", "/api/knowledge/template", knowledge.template_save'
- path: src/dashboard/api/knowledge.py
  line: 10
  anchor: 'def _view(ctx, *, with_identity=False):'
- path: src/dashboard/api/knowledge.py
  line: 18
  anchor: 'def _template_view(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 25
  anchor: 'def _session(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 34
  anchor: 'def read(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 45
  anchor: 'def facts(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 67
  anchor: 'def extract_status(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 77
  anchor: 'def template_read(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 86
  anchor: 'def template_save(ctx):'
- path: src/dashboard/api/knowledge.py
  line: 103
  anchor: 'def extract_trigger(ctx):'
- path: src/dashboard/knowledge_view.py
  line: 26
  anchor: 'class KnowledgeView:'
- path: src/dashboard/knowledge_view.py
  line: 37
  anchor: 'def taxonomy(self):'
- path: src/dashboard/knowledge_view.py
  line: 47
  anchor: 'def owners(self, kind=''episodes''):'
- path: src/dashboard/knowledge_view.py
  line: 65
  anchor: 'def read(self, owner='''', query='''', limit=50, offset=0, contact='''',
    channel_type=''''):'
- path: src/dashboard/knowledge_view.py
  line: 129
  anchor: 'def facts(self, owner='''', query='''', limit=50, offset=0, contact='''', *, group=''''):'
- path: src/butler/runtime/knowledge_store.py
  line: 693
  anchor: 'def read(self, owner='''', query='''', limit=50, offset=0, contact='''',
    channel_type=''''):'
- path: src/butler/runtime/knowledge_store.py
  line: 722
  anchor: 'def facts(self, owner='''', query='''', limit=50, offset=0, contact='''', *, allowed_owners=None):'
- path: src/butler/runtime/knowledge_store.py
  line: 763
  anchor: 'def sessions(self, owner, kind=''episodes''):'
- path: web/src/views/KnowledgeView.vue
  line: 61
  anchor: const payload = await apiGet('/api/knowledge?' + params.toString())
- path: web/src/views/FactsView.vue
  line: 112
  anchor: const payload = await apiGet('/api/knowledge/facts?' + params.toString())
- path: web/src/views/FactsView.vue
  line: 127
  anchor: async function loadExtract() {
- path: web/src/views/FactsView.vue
  line: 44
  anchor: const kinds = computed(() => new Map((data.value?.kinds || []).map(item
    => [item.key, item.label])))
- path: src/dashboard/api/support.py
  line: 172
  anchor: 'def trigger_butler_extract(config, payload):'
- path: src/butler/server.py
  line: 157
  anchor: 'if self.path == ''/v1/knowledge/extract'':'
- path: src/butler/server.py
  line: 385
  anchor: started, reason = extract.trigger(owner=owner, batch=batch, dry_run=dry_run)
- path: src/dashboard/routes.py
  line: 80
  anchor: '("POST", "/api/knowledge/facts/delete", knowledge.delete_fact)'
- path: src/dashboard/api/knowledge.py
  line: 56
  anchor: 'def delete_fact(ctx):'
- path: src/butler/server.py
  line: 337
  anchor: 'if self.path == ''/v1/knowledge/facts/delete'':'
- path: web/src/views/FactsView.vue
  line: 155
  anchor: 'async function deleteFact(row)'
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-migrate-source-recheck
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-01-knowledge-atomic-retry
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-knowledge-group-sources
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
- raw/changes/2026-11-05-resident-diary-web
```
### 对话原文、知识事实、自动提炼和知识模板

#### 方法、路径与鉴权

七条路由覆盖查询、事实删除、提炼和模板管理。

| 方法 | 路径 | 处理器 | 性质 |
|---|---|---|---|
| GET | `/api/knowledge` | `api.knowledge.read` | 只读 |
| GET | `/api/knowledge/facts` | `api.knowledge.facts` | 只读 |
| POST | `/api/knowledge/facts/delete` | `api.knowledge.delete_fact` | 确认后转发 Butler 删除单条事实 |
| GET | `/api/knowledge/extract` | `api.knowledge.extract_status` | 只读，转问 Butler |
| POST | `/api/knowledge/extract` | `api.knowledge.extract_trigger` | 只转发，不等结果 |
| GET | `/api/knowledge/template` | `api.knowledge.template_read` | 只读，不建目录 |
| POST | `/api/knowledge/template` | `api.knowledge.template_save` | 校验／保存／恢复覆盖层 |

原文与事实由 Butler 写入，管理台将单条事实的删除确认转发给 Butler。

提炼那条 POST（`routes.py:67`）不碰任何 vault：它把请求转给 Butler 的 `/v1/knowledge/extract`，真正的提炼在 Butler 的后台线程里跑（[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)），HTTP 只拿 202。

模板两条只改 `data/knowledge/template.md`，不碰 vault（见下文）。

这些路由都走 [modules/dashboard](dashboard.md#doc-bb47c9474691fe) 的本机业务访问控制。非本机安装一律 503，与 `/api/queue` 同一套门禁。

#### 删除单条事实

事实行的 `fact_id` 按 owner、相对节点路径和原始事实行生成。管理台验证本机同源和 `X-Wxbot-Knowledge-Action` 后，把 `{owner,fact_id,acknowledge:true}` 转发 `/v1/knowledge/facts/delete`。Butler 验证服务凭据，并使用提炼锁和存储锁处理。匹配成功回 `200 {ok,deleted,indexes_updated}`，事实已变更或已删回 404，占锁回 409，参数错误回 400。原文与游标保留。来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 请求字段（类型、必填、默认、校验）

| 参数 | 类型/默认 | 校验 |
|---|---|---|
| owner | 字符串，默认空 | 精确匹配身份稳定键（`user:<uuid>` / `anon:dm:101`）；空表示不过滤。在目录行上做内存过滤，不进文件扫描之外的任何查询 |
| q | 字符串，默认空 | 原文：`user_text` 或 `reply_text` 的**大小写不敏感子串**；事实：`fact_key` 或 `fact_value` 的子串。都是内存匹配，没有 LIKE 注入面 |
| limit | 整数，默认 50 | 夹在 1..200 |
| offset | 整数，默认 0 | 负数归零 |
| contact | 字符串，默认空 | 精确匹配日记块的 `contact` / 节点 frontmatter 的 `contact`；空表示不缩 |
| group | 字符串，默认空 | 仅事实接口使用。精确群窗口名，优先于 contact，分页前跨 owner 筛选 |
| channel_type | `dm` / `group`，默认空 | 与 `contact` 组合定位一个会话；**只对原文生效**，事实节点没有这一列。`_session(ctx)`（`api/knowledge.py:23`）只认这两个值，其余当没填 |

参数全部当不可信输入处理。

##### 自动提炼两条的请求与响应

| 方法 | 路径 | 请求体 | 响应 |
|---|---|---|---|
| GET | `/api/knowledge/extract` | 无 | `{available: true, ...status}` 或 `{available: false, error}` |
| POST | `/api/knowledge/extract` | 可选 `{owner?, batch?, dry_run?}` | `202 {ok, status}` / `400` / `409` 忙 / `503` 转发失败 |

GET 的字段全部来自 Butler 的 `ExtractScheduler.status()`（`src/butler/server.py:157`）：`enabled`、`knowledge_enabled`、`auto_extract`、`auto_prune`、`interval_minutes`、`batch`、`max_owners`、`min_backlog`、`idle_seconds`、`next_run_at`、`last_run_at`、`last_report`、`failures`、`last_error`、`next_prune_at`。管理台**不解析数据目录、不读状态文件**，只把 Butler 的回答包一层 `available`（`api/knowledge.py:54`）。

Butler 不可达时**不是错误**：`fetch_butler_data` 抛的 `RuntimeError`（以及非本机模式的 `ValueError`）被折成 `200 {available: false, error}`，页面显示一行提示并隐藏按钮（`api/knowledge.py:58`）。理由和 vault 不存在一致——这一侧看不到，不等于业务坏了。

POST 的校验在 Butler 侧：`owner` 去空白后上限 200 字符，`batch` 必须是整数并夹在 `1..200`，`dry_run` 必须是布尔（`src/butler/server.py:329`、`:334`、`:339`）；任一不合法回 400，管理台原样透传（`api/knowledge.py:106`）。正在跑一轮时 `trigger()` 返回 `busy`，映射成 409，**不排队**（`server.py:343`）；成功只回 `202 {ok: true, status: 'started'}`，不等模型。转发本身失败（连不上、超时、没配 token、非本机模式）回 503 且 `ok: false`（`api/knowledge.py:104`）。

`dry_run` 在这里也允许：它让 Butler 只读 vault 不写入、不留状态，供排查用；管理台按钮不传它。

#### 响应字段与错误语义

两条响应同形，并都带上模板分类：

```
{available, owners[], rows[], total, limit, offset, has_more,
 kinds[{key,label,section,hint}], node_types[{key,label,description}]}
```

`kinds` 的 `label` 取模板的「索引分类」，`section` 是节点里的小节名；`node_types` 的 `label` 是目录名。前端直接拿它们当筛选与列文案，不再维护第二份七类映射。

`owners` 每项 `{owner, name, contact, channel_type, episodes, facts, last_at, sessions}`，**恒为全量**（不受 owner 会话筛选影响），供页面左栏列出可筛选的人。`sessions` 是 `[{contact, channel_type, count}]`，按条数倒序，列出这个人在哪些会话里留下过数据；原文页取自日记文件，事实页只按 `contact` 分且 `channel_type` 恒为空字符串。`slug` 不返回——那是内部目录名。

事实响应另有 `groups[{name,facts,episodes}]`，汇总所有 owner 的群聊归档。`owners[].group_only` 标记纯群条目，前端将其折入群项。可确定群归档的事实带 `source_group/source_name`，后者来自身份库的群昵称、人物显示名或未识别标签。相同 owner 的同名群与私聊不能仅凭旧节点 contact 判定通道，相关事实留在个人或全部知识。来源 [raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)。

原文行有 7 个字段 `owner` / `at` / `contact` / `channel_type` / `user_text` / `reply_text` / `outcome`（`EPISODE_FIELDS`，`knowledge_view.py:12`）；`request_id` 是内部去重键，只在写侧出现。

事实行的基础字段为 `owner`、`contact`、`fact_id`、`kind`、`fact_key`、`fact_value`、`quote`、`episode_at`、`confidence`、`source` 和 `created`。`kind` 来自模板分类，历史分类仍按原样返回。投影省略节点名和文件路径。

**vault 不存在不是错误**：`read` / `facts` 先看目录里有没有人，`self._entries()` 为空直接返回 `_empty()`（`available: false` 加空数组），**绝不创建目录、绝不写文件**。只有真正读不动（`OSError`）才抛 `RuntimeError`，由 api 层折成 `500` 且带 `read_only: true`，形状与 [apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f) 一致。

#### 实现链（路由→服务→符号）

`routes.ROUTES` → `api.knowledge.read` / `.facts` → `_view(ctx)`（`api/knowledge.py:10`）用 `ctx.butler_config_path()` 载入 [modules/butler](butler.md#doc-38393df7a7b4da) 的配置拿 `data_path()`，拼出 `data/knowledge` 目录 → `ctx.KnowledgeView(root)`。模板两条走 `_template_view(ctx)`（`:16`），它传的是 `data_path()` 本身，写入目标由视图内部拼成 `knowledge/template.md`。

`KnowledgeView`（`src/dashboard/knowledge_view.py:22`）**不再自己解析存储格式**，只持有一个 `KnowledgeStore(root)`：

- `taxonomy()`（`:32`）从 `store.template` 取分类与节点类型，两条只读投影都把它合进响应。
- `owners(kind)`（`:42`）把 `store.owners()` 的目录行补上 `sessions`：原文页传 `'episodes'`，事实页传 `'facts'`，分别落到 `KnowledgeStore.sessions`（`knowledge_store.py:709`）的两条统计分支。一个人可以同时在私聊和几个群里说过话，所以左栏按人一行、不按会话拆行。
- `read`（`:56`）/ `facts`（`:71`）直接转发给 `KnowledgeStore.read`（`:642`）/ `.facts`（`:671`），再用 `EPISODE_FIELDS` / `FACT_FIELDS` 白名单裁字段。跨 vault 归并、分页、排序全在 store 里，接口层不做二次计算。

这条委托链是改版的重点：存储从三张 SQLite 表换成人一个 vault，接口层只改了一行构造与两处字段白名单，路由与响应形状一个字没动。

#### 数据来源与字段血缘

查询读取 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 的日记和节点文件。事实删除经 Butler 原子改写单个节点及派生索引，原文与游标保持独立。

跨 vault 分页：`KnowledgeStore.read` / `.facts` 遍历所有 vault 收集后再切 `[offset:offset+limit]`——与 SQLite 版的「每库取 offset+limit 再归并」不同，现在是全量收集后切片。原文按 `(at, contact)` 倒序，事实按 `(created, node)` 倒序。

`at` / `created` 都来自日记块与事实行注释里的时间戳；`episode_at` 是提炼那批原文的**第一条**时间，供界面标注「基于哪段时间的对话」。

#### 前端消费点（文件+函数）

[modules/web](dashboard.md#doc-aeec90dfe23cd3) 的两个页面共用 `knowledge.css`：

- `KnowledgeView.vue`（对话记录）：`load()` 用 `apiGet('/api/knowledge?...')`（`:61`）拉取，页大小固定 50；左栏渲染 `owners`，点人写入 `owner` 筛选；选定的人有多个会话时，标题下出现一行会话 chips（`:154`，`全部会话` 加每个 `sessions[i]`），点击写入 `contact` + `channel_type`，换人时清空；关键词取导航壳共享搜索框并防抖；`badgeOf(row)` 把 `outcome` 映射成「本轮失败 / 未回复 / 群聊 / 私聊」。
- `FactsView.vue`（知识库）使用 `/api/knowledge/facts` 查询群或个人档案，按模板显示类别，保留事实、来源、原话和置信度。「操作」列提交已确认的单条删除并刷新当前列表。
- 自动提炼状态条（`FactsView.vue:264`）：`loadExtract()`（`:116`）拉 `/api/knowledge/extract`，`runExtract()`（`:126`）发 POST（`:133`）。一条状态句把开关、上次写入条数、下次时间或失败原因说清，措辞在 `extractLine` 里；`available: false` 时降成 warn 色提示并**隐藏按钮**。触发后 4 秒刷状态、15 秒连表格一起刷、60 秒清掉「已开始提炼」，不在页面上做轮询。

两页左栏副标题都是会话摘要：选定的人一行里直接写「私聊 101、群聊 鸭王集训营」，超过两个会话折成「等 N 个会话」，后面才是条数。会话筛选只缩右栏与计数，不把人从左栏拿走（后端 `owners` 恒为全量）。

两页都在 `available=false` 时显示空态而非报错；左栏项带 `tabindex`/`role="button"` 与键盘处理，`:focus-visible` 有内焦点环。管理台自身没有写路径：知识库页唯一能改状态的是那个「立即提炼」按钮，而它只把一次请求转给 Butler，模型调用与落盘全在对端。

#### 测试与风险

本地 `tests/dashboard/test_knowledge_view.py`（11 项）：vault 不存在时 `available=false` 且**不生成目录**、空目录按空态、不返回 `request_id`、筛选分页、同一人的多个会话在 `sessions` 里按条数列出且不拆行、选定人之内按 `contact`+`channel_type` 再筛（同名群与私聊不串）、索引丢失时从 vault 重建、损坏文件抛 `RuntimeError`、相对 `data_dir` 仍能只读打开，以及一条真 HTTP 用例——起真 Handler，断言四条路由：两条只读出数、`owner` 过滤、会话参数直传、非法 `channel_type` 当没填、事实行字段；自动提炼 GET 把 Butler 回答包成 `available: true`、POST 去空白后转发 `owner` 与 `dry_run`、409 原样透传、Butler 不可达时 GET 仍 200 但 `available: false` 而 POST 503；最后把 wxbot 配置切到 `mode=remote` 断言四条全部 503。

Butler 侧的 `GET/POST /v1/knowledge/extract` 由 `tests/butler/test_knowledge_auto.py` 的 `test_http_exposes_status_and_accepts_one_manual_trigger` 覆盖（默认关也能读状态、`batch`/`dry_run`/`owner` 非法各回 400、合法触发 202 且后台自己释放单飞锁、忙时 409）。

模板两条的用例在同目录 `tests/dashboard/test_knowledge_template_view.py`（10 项）：读取不建目录、保存新版本、版本冲突不改文件、校验不落盘、非法内容带行号、请求体不能指定写入路径、恢复内置保留备份、缺确认头/未知动作被拒、HTTP 模板 GET/POST 的 400/409 与 503 门禁、facts 携带模板分类。六条知识路由的 HTTP 门禁由两个测试文件合起来覆盖：本文件的三条只读 + 提炼 POST，加上模板文件的 GET/POST。

`web/scripts/smoke.mjs` 断言两个页面的渲染行数、类型文案（改为模板块下发的「喜好」）、置信度文案与导航标签数（9，含「知识模板」）。

风险：`q` 与 `owner` 都是内存过滤，**一次请求要遍历所有人的整个 vault**，联系人数量与对话量线性叠加，是 O(全部文件)；左栏的 `sessions` 又给每个 owner 多扫一遍文件，也是 O(人数)；`index.json` 丢失会触发一次全量重建（结果正确但那次请求变慢）；分页顺序不能改成只按时间——同一秒内的多条要靠第二排序键（`contact` / `node`）定序。

#### 代码依据与修改来源

- `src/dashboard/routes.py:51` — `("GET", "/api/knowledge", knowledge.read)`
- `src/dashboard/routes.py:51` — `("GET", "/api/knowledge/facts", knowledge.facts)`
- `src/dashboard/routes.py:51` — `("GET", "/api/knowledge/extract", knowledge.extract_status)`
- `src/dashboard/routes.py:51` — `("GET", "/api/knowledge/template", knowledge.template_read)`
- `src/dashboard/routes.py:79` — `("POST", "/api/knowledge/extract", knowledge.extract_trigger)`
- `src/dashboard/routes.py:79` — `("POST", "/api/knowledge/template", knowledge.template_save)`
- `src/dashboard/api/knowledge.py:10` — `def _view(ctx):`
- `src/dashboard/api/knowledge.py:16` — `def _template_view(ctx):`
- `src/dashboard/api/knowledge.py:23` — `def _session(ctx):`
- `src/dashboard/api/knowledge.py:32` — `def read(ctx):`
- `src/dashboard/api/knowledge.py:43` — `def facts(ctx):`
- `src/dashboard/api/knowledge.py:54` — `def extract_status(ctx):`
- `src/dashboard/api/knowledge.py:64` — `def template_read(ctx):`
- `src/dashboard/api/knowledge.py:73` — `def template_save(ctx):`
- `src/dashboard/api/knowledge.py:90` — `def extract_trigger(ctx):`
- `src/dashboard/knowledge_view.py:22` — `class KnowledgeView:`
- `src/dashboard/knowledge_view.py:32` — `def taxonomy(self):`
- `src/dashboard/knowledge_view.py:42` — `def owners(self, kind='episodes'):`
- `src/dashboard/knowledge_view.py:56` — `def read(self, owner='', query='', limit=50, offset=0, contact='', channel_type=''):`
- `src/dashboard/knowledge_view.py:71` — `def facts(self, owner='', query='', limit=50, offset=0, contact=''):`
- `src/butler/runtime/knowledge_store.py:693` — `def read(self, owner='', query='', limit=50, offset=0, contact='', channel_type=''):`
- `src/butler/runtime/knowledge_store.py:722` — `def facts(self, owner='', query='', limit=50, offset=0, contact=''):`
- `src/butler/runtime/knowledge_store.py:709` — `def sessions(self, owner, kind='episodes'):`
- `web/src/views/KnowledgeView.vue:61` — `const payload = await apiGet('/api/knowledge?' + params.toString())`
- `web/src/views/FactsView.vue:103` — `const payload = await apiGet('/api/knowledge/facts?' + params.toString())`
- `web/src/views/FactsView.vue:116` — `async function loadExtract() {`
- `web/src/views/FactsView.vue:39` — `const kinds = computed(() => new Map((data.value?.kinds || []).map(item => [item.key, item.label])))`
- `src/dashboard/api/support.py:172` — `def trigger_butler_extract(config, payload):`
- `src/butler/server.py:157` — `if self.path == '/v1/knowledge/extract':`（GET）
- `src/butler/server.py:385` — `started, reason = extract.trigger(owner=owner, batch=batch, dry_run=dry_run)`（POST）

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)
[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)
[raw/changes/2026-11-01-knowledge-sessions](knowledge-vault.md#doc-ba214c308af8ff)
[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)
[raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)
[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)
[raw/changes/2026-11-01-knowledge-atomic-retry](knowledge-vault.md#doc-8614fbc4e2f39c)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。

#### 常驻角色接入核对

已对照当前共享源码复核本词条的接口或调用位置。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。

#### 小潮日记接入核对

复核共享路由表，知识库、事实、模板和提炼接口的处理器与本机门禁保持原有契约。 来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。
<!-- end-migrated-part: doc-17461d21600be6 -->

<a id="doc-4656beba355895"></a>

### knowledge_template

来源：`llm wiki/wxbot/symbols/knowledge-template.md:1`。

```yaml
type: symbol
module: runtime
summary: 知识图谱模板的解析与加载——一份 Markdown 决定节点目录、事实分类、索引分区与提炼规则，覆盖层优先，坏模板回退内置
coverage: core
last_verified: '2026-11-02'
sources:
- path: src/butler/runtime/knowledge_template.py
  line: 28
  anchor: BUILTIN_TEMPLATE = REPO_ROOT
- path: src/butler/runtime/knowledge_template.py
  line: 59
  anchor: 'class TemplateError(ValueError):'
- path: src/butler/runtime/knowledge_template.py
  line: 83
  anchor: 'class GraphTemplate:'
- path: src/butler/runtime/knowledge_template.py
  line: 154
  anchor: DEFAULT_TEMPLATE = GraphTemplate(
- path: src/butler/runtime/knowledge_template.py
  line: 296
  anchor: 'def parse_template(text):'
- path: src/butler/runtime/knowledge_template.py
  line: 440
  anchor: 'def resolve_template(override=None, log=None):'
- path: src/butler/runtime/knowledge_template.py
  line: 456
  anchor: 'def load_template(override=None, log=None):'
- path: plugins/butler-wechat/knowledge/graph-template.md
  line: 21
  anchor: '## 节点目录'
changes:
- raw/changes/2026-11-02-knowledge-graph-template
calls: []
called_by:
- symbols/knowledge-extract
```
### knowledge_template

#### 签名与职责

```
parse_template(text) -> GraphTemplate          # 严格；任何问题抛 TemplateError([{line, message}])
resolve_template(override=None, log=None) -> (GraphTemplate, source, path)
load_template(override=None, log=None) -> GraphTemplate   # 宽松；失败回退，绝不抛
```

模板决定四件事：新 vault 有哪些节点目录、事实分哪些类（节点小节与索引分类）、索引页怎么分区、提炼 prompt 的分类/类型说明与追加规则。它**不决定**事实行的机器可读注释——那是 `FACT_LINE` 的解析契约，改了就读不回历史事实。

#### 两层来源与回退

| 优先级 | 路径 | 来源标记 | 谁写 |
|---|---|---|---|
| 1 | `data/knowledge/template.md` | `override` | 管理台「知识模板」页 |
| 2 | `plugins/butler-wechat/knowledge/graph-template.md` | `plugin` | 随插件分发，只读 |
| 3 | 代码里的 `DEFAULT_TEMPLATE`（`:154`） | `builtin` | 两层都读不到时兜底 |

覆盖层存在但解析失败时，真实生效的是插件内置模板，所以 `resolve_template` 返回的 `source` 是 `plugin`，并把覆盖层的错误原文留在页面上供修。坏模板只告警一次（按 mtime + size 缓存），不会每次写入都刷日志。

缓存键是 `(路径, mtime_ns, 大小)`：编辑保存后下一次读取自然失效，不需要重启 Butler。

#### 模板结构

frontmatter 控制 `id` / `version` / `episode_dir` / `index_file` / `index_title` / `index_note` / `index_limit` / `index_days`。正文三个二级标题：

- `## 节点目录`：表格 `type | 目录 | 说明`，type 是小写 key，目录是 vault 里的文件夹名。
- `## 分类`：表格 `kind | 节点小节 | 索引分类 | 提炼指引`；节点小节与索引分类刻意分开，节点里叫「身份」、索引页叫「用户信息」。
- `## 提炼规则`：`- ` 开头的列表，追加在内置 6 条安全规则之后。

列名允许中英别名（`类型` / `目录` / `分类` / `小节` / `索引` / `指引`），但 key 必须匹配 `^[a-z][a-z0-9_]{0,31}$`。目录名不能含 `[] | # ^`、路径分隔符或控制字符，也不能与 `episode_dir` 重名。

#### 约束与兜底

- 必须保留 `person` 节点类型与 `topic` 分类：`parse_facts` 与 `add_fact` 用它们做越界值的兜底。
- 上限：kind ≤ 20、节点类型 ≤ 12、规则 ≤ 20；单条指引 ≤ 120 字、单条规则 ≤ 200 字；说明与规则合计 ≤ 2400 字（`MAX_PROMPT`）；文件 ≤ 256 KB。
- 内置的 6 条安全规则（只提取用户说过的话、不推测、矛盾各记一条、助理回复不作事实来源、links 不编造、没有内容输出 `[]`）写死在 `knowledge_extract.CORE_RULES`，模板只能追加。
- 未知 kind / 节点类型在写入时降级到 `topic` / `person`；模板里被删掉的旧分类不会改写已有节点，索引页把它们归入「其他」。

#### 调用方

- `KnowledgeStore.__init__`（`knowledge_store.py:315`）默认 `load_template(root / 'template.md')`，之后 `episodes_dir` / `node_path` / `index_page_path` / `add_fact` / `rebuild_index` 都读 `self.template`。见 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)。
- `knowledge_extract.build_prompt`（`:54`）与 `parse_facts` 白名单来自模板；见 [symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)。
- 管理台 `KnowledgeTemplateView` 用严格解析做保存前校验；`GET /api/knowledge/facts` 的 `kinds` / `node_types` 来自 `GraphTemplate.summary()`，见 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)。

#### 测试与风险

`tests/butler/test_knowledge_template.py` 覆盖：默认模板与旧七类一致、重复分类报行号、必须保留 person/topic、目录与对话目录重名被拒、覆盖层新增目录/分类/规则落到 vault、`episode_dir` / `index_file` 可配置、坏覆盖层回退且只告警一次、未知 kind/type 降级、prompt 与白名单来自模板、随包模板可加载。

风险：模板是提示词注入面，但只拼白名单字段并限长，且文件由安装者本地持有；模板改动不迁移历史，旧分类仍按原文件展示；共享缓存是进程内的，多个进程各自按 mtime 失效，不共享状态。

#### 代码依据

- `src/butler/runtime/knowledge_template.py:28` — `BUILTIN_TEMPLATE = REPO_ROOT / 'plugins' / ...`
- `src/butler/runtime/knowledge_template.py:59` — `class TemplateError(ValueError):`
- `src/butler/runtime/knowledge_template.py:83` — `class GraphTemplate:`
- `src/butler/runtime/knowledge_template.py:154` — `DEFAULT_TEMPLATE = GraphTemplate(`
- `src/butler/runtime/knowledge_template.py:296` — `def parse_template(text):`
- `src/butler/runtime/knowledge_template.py:440` — `def resolve_template(override=None, log=None):`
- `src/butler/runtime/knowledge_template.py:456` — `def load_template(override=None, log=None):`
- `plugins/butler-wechat/knowledge/graph-template.md:21` — `## 节点目录`

[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)
<!-- end-migrated-part: doc-4656beba355895 -->

<a id="doc-84df4a3514bf20"></a>

### SQLite kb_episodes（已退场）

来源：`llm wiki/wxbot/tables/kb-episodes.md:1`。

```yaml
type: table
module: butler
summary: 已退场——SQLite 时代的 L1 原文表，现由 vault 里的「对话/YYYY-MM-DD.md」承担，只保留迁移读入口
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/runtime/knowledge_store.py
  line: 48
  anchor: OUTCOMES = ('ok', 'error', 'silent')
- path: src/butler/runtime/knowledge_store.py
  line: 809
  anchor: 'def _import_sqlite(store, path, log):'
- path: src/butler/runtime/knowledge_store.py
  line: 815
  anchor: 'if ''kb_episodes'' in tables:'
- path: src/butler/runtime/knowledge_store.py
  line: 855
  anchor: 'def migrate_legacy(data_dir, log=None):'
- path: src/butler/runtime/knowledge_store.py
  line: 788
  anchor: 'def _checkpoint_legacy(path):'
- path: src/butler/__main__.py
  line: 73
  anchor: 'if args.command==''knowledge-migrate'':'
changes:
- raw/changes/2026-11-01-knowledge-episodes
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-01-knowledge-atomic-retry
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-05-knowledge-group-sources
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
```
### SQLite kb_episodes（已退场）

**这张表不再被写入，也不再被读取。** L1 原文现在落在每个人的 vault 里：`对话/YYYY-MM-DD.md`，一天一个文件，一轮对话一个 `##` 块。当前形态见 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)。

保留这一页只为迁移：`migrate_legacy` 仍按旧列名把 SQLite 里的行读出来喂给 vault。

#### 它曾经是什么

SQLite 时代的 L1 原文层：一条记录等于一轮对话（用户说了什么、机器人回了什么、这轮成功与否），每个 owner 一个库 `data/knowledge/p-<slug>/episodes.sqlite3`。

`outcome` 只有 `ok` / `error` / `silent` 三个值（`OUTCOMES`，`src/butler/runtime/knowledge_store.py:48`）：`silent` 是模型选择不回，`error` 是处理抛错，`reply_text` 为 NULL 表示这轮没有产出回复——三者不是同一件事。

#### 退场后的替代

| 旧 | 新 |
|---|---|
| 表 `kb_episodes`，一行一轮 | 日记文件 `对话/YYYY-MM-DD.md`，`## 时间 · 联系人 · 私聊 / 群聊` 块 |
| `id INTEGER PRIMARY KEY` 定序去重 | 没有自增 id；块首注释里的 `at` 与 `rid` 定序去重 |
| `outcome` 列 | 块首注释 `rid` / `at` / `outcome` / `contact` / `channel` |
| 部分唯一索引 `kb_episodes_request` | 读该天文件，看文本里是否已有 `rid:…` |
| `prune` 按 `at < cutoff` 删行 | `prune` 按保留期删整天文件 |

原文按天归档而不是一轮一文件：一年 365 个文件，不至于把 Obsidian 的图挤满。

#### 仅存的读取路径：迁移

`migrate_legacy(data_dir)`（`src/butler/runtime/knowledge_store.py:801`）→ `_import_sqlite`（`:755`）在旧库里发现 `kb_episodes` 表（`:761`）就逐行读，调 `KnowledgeStore.record(...)` 写进 vault；搬完把旧库改名留底、不删：

| 旧文件 | 处理 |
|---|---|
| `data/knowledge.sqlite3` | 搬完改名 `knowledge.legacy.sqlite3` |
| `data/knowledge/p-*/episodes.sqlite3` | 搬完改名 `episodes.sqlite3.migrated` |

改名之前会先 `_checkpoint_legacy`（`:734`）合并 WAL：旧库是 WAL 模式时，直接把主库改名会让 `-wal` 失配，留底库就只剩改名前的旧页（详见 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 与 [raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)）。

入口只有一个：`python -m butler knowledge-migrate`（`src/butler/__main__.py:73`）。迁移幂等，重复跑不会写出重复块。

2026-11-02 的模板化不改变迁移语义：迁移仍把旧行逐条交给 `record`，历史轮次不会因模板新增/删除目录而丢失或重排；模板只影响此后新写入的日记目录与索引分区。

#### 代码依据与修改来源

- `src/butler/runtime/knowledge_store.py:48` — `OUTCOMES = ('ok', 'error', 'silent')`
- `src/butler/runtime/knowledge_store.py:755` — `def _import_sqlite(store, path, log):`
- `src/butler/runtime/knowledge_store.py:761` — `if 'kb_episodes' in tables:`
- `src/butler/runtime/knowledge_store.py:801` — `def migrate_legacy(data_dir, log=None):`
- `src/butler/runtime/knowledge_store.py:734` — `def _checkpoint_legacy(path):`
- `src/butler/__main__.py:73` — `if args.command=='knowledge-migrate':`

[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)
[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)
[raw/changes/2026-11-01-knowledge-sessions](knowledge-vault.md#doc-ba214c308af8ff)
[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)
[raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)
[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)
[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)
[raw/changes/2026-11-01-knowledge-atomic-retry](knowledge-vault.md#doc-8614fbc4e2f39c)
[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)

#### 本次核对

管理台群汇总读取现有日记文件的会话计数；旧表及迁移路径沿用。 来源 [raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)。

#### 本次核对

新删除入口只作用于事实节点，对话日记与旧表迁移沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

已对照当前共享源码复核本词条的接口或调用位置。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。
<!-- end-migrated-part: doc-84df4a3514bf20 -->

<a id="doc-eae62eb158097e"></a>

### SQLite kb_facts（已退场）

来源：`llm wiki/wxbot/tables/kb-facts.md:1`。

```yaml
type: table
module: butler
summary: 已退场——L2 事实表被 vault 里的「人物/组织/话题」节点 Markdown 取代，只保留迁移读入口
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/runtime/knowledge_store.py
  line: 50
  anchor: FACT_KINDS = LEGACY_KINDS
- path: src/butler/runtime/knowledge_store.py
  line: 809
  anchor: 'def _import_sqlite(store, path, log):'
- path: src/butler/runtime/knowledge_store.py
  line: 821
  anchor: 'if ''kb_facts'' in tables:'
- path: src/butler/runtime/knowledge_store.py
  line: 833
  anchor: 'def _import_memory(store, path, log):'
- path: src/butler/runtime/knowledge_store.py
  line: 788
  anchor: 'def _checkpoint_legacy(path):'
changes:
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-01-knowledge-atomic-retry
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-05-knowledge-group-sources
- raw/changes/2026-11-05-delete-knowledge-fact
```
### SQLite kb_facts（已退场）

**这张表不再被写入，也不再被读取。** L2 事实现在写在 vault 的实体节点里——`人物/…`、`组织/…`、`话题/…` 三个目录下的 Markdown，一条事实一行，行尾 HTML 注释带去重指纹与出处。当前形态见 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)。

保留这一页只为迁移：`_import_sqlite` 仍按旧列名把事实读出来喂给 `add_fact`。

#### 它曾经是什么

SQLite 时代的 L2 事实层：从 L1 原文提炼出的、值得长期记住的陈述——身份背景、偏好习惯、与他人的关系、约定与发生过的事、长期关注的话题。每个 owner 一个库 `data/knowledge/p-<slug>/facts.sqlite3`，与原文分库是因为两者生命周期不同：原文按 `retention_days` 过期，事实不跟着消失。

`kind` 白名单当年是 `FACT_KINDS`（现在 `src/butler/runtime/knowledge_store.py:50` 只剩兼容常量 `FACT_KINDS = LEGACY_KINDS`）；越界值在 `add_fact` 里回落成 `topic`。当前白名单实际来自模板 [symbols/knowledge-template](knowledge-vault.md#doc-4656beba355895)，见 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)。

**唯一键建在指纹上而不是 `fact_key` 上**：指纹是 `sha1(kind|fact_key|fact_value)`。同一件事的同一说法只留一条；措辞不同的矛盾陈述（「喜欢美式」与「更喜欢拿铁」）各留一条，不互相覆盖——谁对谁错要靠人和时间判断，库不该替他们做决定。这条设计原样带进了 vault：指纹变成行尾注释里的 `fp`。

#### 退场后的替代

| 旧 | 新 |
|---|---|
| 表 `kb_facts`，一行一条事实 | 实体节点 `…md` 正文的一行 `- 陈述 <!-- fp:… -->` |
| `owner` / `contact` 列 | 节点 frontmatter 的 `owner` / `contact` |
| `kind` 列 | 正文按 `FACT_SECTIONS` 分小节，小节即 kind |
| `fact_key` / `fact_value` | 行内陈述文本 + 注释里的 `key:` |
| `quote` / `confidence` / `source` / `episode_at` | 注释里的 `quote:` / `conf:` / `src:` / `at:` |
| `fingerprint` + 部分唯一索引 | 行尾注释的 `fp:`，写入前扫一遍已有行 |
| `created` 排序 | 节点 frontmatter 的 `updated` / `updated_ts` |

**新增了表里没有的两样东西**：`subject`（这条事实挂到哪个节点）与 `links`（正文里生成哪些 `[[双链]]`）。没有它们，写出来的只是一堆孤立的事实行，Obsidian 的 graph view 连不起来——这正是改版的原因。

#### 仅存的读取路径：迁移

`migrate_legacy(data_dir)` → `_import_sqlite`（`src/butler/runtime/knowledge_store.py:755`）逐行读 `kb_facts`（`:767`）并调 `add_fact(...)`，`source` 与 `created` 原样带过去。搬完改名留底：

| 旧文件 | 处理 |
|---|---|
| `data/knowledge.sqlite3` | 搬完改名 `knowledge.legacy.sqlite3` |
| `data/knowledge/p-*/facts.sqlite3` | 搬完改名 `facts.sqlite3.migrated` |

事实库同样是 WAL 模式，改名之前会先 `_checkpoint_legacy`（`:734`）合并 WAL；否则留底库可能连 `kb_facts` 表都读不出来（首次真实迁移踩到过，见 [raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)）。

同一支迁移还顺带收编另一套存储：`_import_memory`（`:779`）把 `business.sqlite3` 里遗留的 `memory` 表逐条搬成 `kind=profile`、`source=memory-migration` 的节点事实，原表保留不动。

2026-11-02 的模板化不改变迁移语义：`_import_sqlite` 仍按旧表的七类 kind 原样交给 `add_fact`，这些 kind 仍在内置模板里；即使安装者删掉其中一类，历史事实也只在读取时按原节点展示，不会被改写或丢弃。

#### 代码依据与修改来源

- `src/butler/runtime/knowledge_store.py:50` — `FACT_KINDS = LEGACY_KINDS`（兼容默认值；实际白名单来自模板）
- `src/butler/runtime/knowledge_store.py:755` — `def _import_sqlite(store, path, log):`
- `src/butler/runtime/knowledge_store.py:767` — `if 'kb_facts' in tables:`
- `src/butler/runtime/knowledge_store.py:779` — `def _import_memory(store, path, log):`
- `src/butler/runtime/knowledge_store.py:734` — `def _checkpoint_legacy(path):`

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)
[raw/changes/2026-11-01-knowledge-sessions](knowledge-vault.md#doc-ba214c308af8ff)
[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)
[raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)
[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)
[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)
[raw/changes/2026-11-01-knowledge-atomic-retry](knowledge-vault.md#doc-8614fbc4e2f39c)
[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)

#### 本次核对

管理台群汇总过滤现有事实节点；旧事实表迁移路径沿用。 来源 [raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)。

#### 本次核对

新删除入口定位现有 Markdown 事实行，旧表迁移沿用。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。
<!-- end-migrated-part: doc-eae62eb158097e -->

<a id="doc-68c7e63f609bfb"></a>

### SQLite kb_owners（已退场）

来源：`llm wiki/wxbot/tables/kb-owners.md:1`。

```yaml
type: table
module: butler
summary: 已退场——owner 目录与提炼游标改为可重建的 index.json，SQLite 索引库只在迁移时被改名留底
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/runtime/knowledge_store.py
  line: 331
  anchor: 'def index_path(self):'
- path: src/butler/runtime/knowledge_store.py
  line: 353
  anchor: 'def _catalog(self):'
- path: src/butler/runtime/knowledge_store.py
  line: 368
  anchor: 'def _touch(self, owner, contact, channel_type, *, episodes=0, facts=0,
    at=None):'
- path: src/butler/runtime/knowledge_store.py
  line: 389
  anchor: 'def _recount(self):'
- path: src/butler/runtime/knowledge_store.py
  line: 878
  anchor: index = root / 'index.sqlite3'
- path: src/butler/runtime/knowledge_store.py
  line: 788
  anchor: 'def _checkpoint_legacy(path):'
changes:
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-01-knowledge-atomic-retry
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-05-knowledge-group-sources
- raw/changes/2026-11-05-delete-knowledge-fact
```
### SQLite kb_owners（已退场）

**这张表连同 `data/knowledge/index.sqlite3` 一起退场。** 目录现在是一个 JSON 文件 `data/knowledge/index.json`，仍然只做枚举不做存储；`index.sqlite3` 若还存在，迁移时只改名留底、不读内容。当前形态见 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)。

#### 它曾经是什么

索引库的唯一表，不是数据本体，只是**目录**：谁有库、目录名是什么、展示名是什么、有多少条、最后说话是什么时候、提炼到哪一条。

**为什么曾经要有索引库**：`owner` 形如 `user:<uuid>` / `anon:group:产品群`，带冒号和中文，不能直接当目录名，所以目录名是散列 `p-` 加 `sha1(owner)` 前 16 位（`owner_slug`，`src/butler/runtime/knowledge_store.py:77`）。散列不可逆，必须有地方记「这个散列是谁」，否则只读侧无法列出可筛选的人，也无法显示展示名。

**为什么不把原文和事实塞进索引库**：那就退回到「一个库装所有人」，一个人的损坏牵连所有人。

#### 退场后的替代：index.json

同一个位置、同一份职责，换成了 JSON（`index_path`，`:325`）：

```json
{"owners": {"user:<uuid>": {"owner", "slug", "contact", "contact_name",
                            "channel_type", "episodes", "facts",
                            "extracted_at", "first_at", "last_at"}}}
```

| 旧列 | 新字段 | 变化 |
|---|---|---|
| `owner` PRIMARY KEY | `owners` 字典的键 | 从行变成键 |
| `slug` UNIQUE | `slug` | 不变 |
| `contact` / `contact_name` | 同名字段 | 不变 |
| `channel_type` | 同名字段 | 不变 |
| `episodes` / `facts` | 同名字段 | 仍是冗余计数 |
| `extracted_upto`（原文 id 水位） | `extracted_at`（时刻水位） | **语义变了**：没有自增 id，游标只能按时间推进 |
| `first_at` / `last_at` | 同名字段 | 不变 |

**为什么敢用 JSON**：这张表规模等于联系人数，整份读写比维护连接便宜；更重要的是它是**缓存**——`_catalog()`（`:347`）读不出来就调 `_recount()`（`:383`）扫一遍 `p-*/vault` 现数回来，游标沿用旧值，不会把已提炼的原文重提一遍。SQLite 版也有重建，但重建是例外路径；这里重建是一等公民。

**仍然没有 schema 版本号**：未知键原样保留，加字段不需要改表。

目录多一个用途：`prune` 删完成天日记后要遍历 `owners()`（`:430`）把每人的 `vault/index.md` 重画一遍，否则索引页里会留着已删除日记的断链。删行本身不经过目录，但「删完之后还要修哪些人」靠它枚举。

#### 仅存的接触点：迁移

`migrate_legacy` 最后一步（`:824`）：`data/knowledge/index.sqlite3` 存在就先 `_checkpoint_legacy`（`:734`）合并 WAL，再改名成 `index.sqlite3.migrated`。**不读内容**——各 owner 的库搬进 vault 时 `_touch`（`:362`）已经把新目录建好了，计数从真实文件数出来，旧索引只是垃圾；但垃圾也要是可打开的文件，否则回收站里的就不是备份。

2026-11-02 的模板化只改变 vault 内的节点目录、分类与索引页分区，不改变 `index.json` 的字段、游标语义或重建路径；目录仍是缓存，模板不参与枚举。

#### 代码依据与修改来源

- `src/butler/runtime/knowledge_store.py:77` — `def owner_slug(owner):`
- `src/butler/runtime/knowledge_store.py:331` — `def index_path(self):`
- `src/butler/runtime/knowledge_store.py:353` — `def _catalog(self):`
- `src/butler/runtime/knowledge_store.py:368` — `def _touch(self, owner, contact, channel_type, *, episodes=0, facts=0, at=None):`
- `src/butler/runtime/knowledge_store.py:389` — `def _recount(self):`
- `src/butler/runtime/knowledge_store.py:824` — `index = root / 'index.sqlite3'`
- `src/butler/runtime/knowledge_store.py:734` — `def _checkpoint_legacy(path):`

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)
[raw/changes/2026-11-01-knowledge-sessions](knowledge-vault.md#doc-ba214c308af8ff)
[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)
[raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)
[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)
[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)
[raw/changes/2026-11-01-knowledge-atomic-retry](knowledge-vault.md#doc-8614fbc4e2f39c)
[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)

#### 本次核对

管理台可按群聚合多个 owner，底层 owner 缓存和旧表迁移沿用。 来源 [raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)。

#### 本次核对

删除更新 owner 的事实数，保留既有目录与提炼游标。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。
<!-- end-migrated-part: doc-68c7e63f609bfb -->

<a id="doc-dc9956670d38fd"></a>

### 用户知识库：一人一个 Obsidian vault

来源：`llm wiki/wxbot/tables/knowledge-vault.md:1`。

```yaml
type: table
module: butler
summary: 用户知识图谱的存储形态——一人一个 Obsidian vault，目录骨架、事实分类与索引分区由 Markdown 模板决定
coverage: core
last_verified: '2026-11-06'
sources:
- path: src/butler/runtime/knowledge_store.py
  line: 1
  anchor: 用户知识图谱：一人一个 Obsidian vault
- path: src/butler/runtime/knowledge_store.py
  line: 77
  anchor: 'def owner_slug(owner):'
- path: src/butler/runtime/knowledge_store.py
  line: 83
  anchor: 'def _safe(name, fallback=''未命名''):'
- path: src/butler/runtime/knowledge_store.py
  line: 107
  anchor: 'def _atomic_write(path, text, attempts=3, delay=0.05):'
- path: src/butler/runtime/knowledge_store.py
  line: 318
  anchor: 'class KnowledgeStore:'
- path: src/butler/runtime/knowledge_store.py
  line: 442
  anchor: 'def _ensure_vault(self, owner):'
- path: src/butler/runtime/knowledge_store.py
  line: 457
  anchor: def record(self, owner, contact, channel_type, request_id, user_text,
- path: src/butler/runtime/knowledge_store.py
  line: 480
  anchor: def add_fact(self, owner, contact, fact_value, *, kind='topic', fact_key='',
- path: src/butler/runtime/knowledge_store.py
  line: 677
  anchor: 'def episodes_of(self, owner, after_at=0.0, limit=200):'
- path: src/butler/runtime/knowledge_store.py
  line: 722
  anchor: 'def facts(self, owner='''', query='''', limit=50, offset=0, contact='''', *, allowed_owners=None):'
- path: src/butler/runtime/knowledge_store.py
  line: 50
  anchor: FACT_KINDS = LEGACY_KINDS
- path: src/butler/runtime/knowledge_store.py
  line: 53
  anchor: INDEX_SECTIONS
- path: src/butler/runtime/knowledge_store.py
  line: 57
  anchor: INDEX_FILE
- path: src/butler/runtime/knowledge_store.py
  line: 346
  anchor: 'def index_page_path(self, owner):'
- path: src/butler/runtime/knowledge_store.py
  line: 594
  anchor: 'def rebuild_index(self, owner):'
- path: src/butler/runtime/knowledge_store.py
  line: 788
  anchor: 'def _checkpoint_legacy(path):'
- path: src/butler/runtime/knowledge_store.py
  line: 855
  anchor: 'def migrate_legacy(data_dir, log=None):'
- path: src/butler/runtime/knowledge_template.py
  line: 154
  anchor: DEFAULT_TEMPLATE = GraphTemplate(
- path: plugins/butler-wechat/knowledge/graph-template.md
  line: 21
  anchor: '## 节点目录'
- path: src/dashboard/knowledge_view.py
  line: 26
  anchor: 'class KnowledgeView:'
- path: src/dashboard/routes.py
  line: 48
  anchor: '"GET", "/api/knowledge", knowledge.read'
- path: src/butler/runtime/knowledge_store.py
  line: 516
  anchor: 'def delete_fact(self, owner, fact_id):'
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-vault-alignment
- raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-01-knowledge-atomic-retry
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-knowledge-group-sources
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-diary-web
```
### 用户知识库：一人一个 Obsidian vault

#### 含义与磁盘布局

用户知识不再是数据库表，而是**一人一个 Obsidian vault**：实体是 Markdown 文件，实体之间的关系只由正文里的双链（Obsidian 的 wikilink 语法）表达。实现只有一份，见 [modules/runtime](butler-functions.md#doc-241e7c8bdd1c05) 里的 `KnowledgeStore`。

```text
data/knowledge/
  index.json                 目录缓存：owner 列表、原文/事实条数、提炼游标
  template.md                可选覆盖层：页面编辑的模板；存在时优先于插件内置
  p-<slug>/vault/            Obsidian vault 根，只放 .md
    人物/冯草草.md           实体节点（type: person）
    组织/鸭王集训营.md       type: org
    话题/AI 编程.md          type: topic
    对话/2026-11-01.md       当天的对话原文；与实体节点之间没有双链
    index.md                 中心索引页：按类别列事实、按目录列节点、按天列日记
```

`<slug>` 由 `sha1(owner)[:16]` 加前缀 `p-` 得到（`:77`）。owner 里带冒号和中文，不适合当目录名，且名字不需要反查——反查靠写进每个文件 frontmatter 的 `owner` 字段。

**为什么一人一个 vault**：任何一个人的数据损坏、被单独导出或整体清空，都不牵连别人；Obsidian 一次只开一个 vault，一个人的图也不会被别人的节点淹没。

#### 模板决定骨架

目录名、事实分类、索引分区与提炼规则不再写死在代码里：[symbols/knowledge-template](knowledge-vault.md#doc-4656beba355895) 从 `plugins/butler-wechat/knowledge/graph-template.md`（内置只读）或 `data/knowledge/template.md`（页面可写的覆盖层）读取，覆盖层优先。

- 首次写入时 `_ensure_vault`（`:436`）按模板的节点目录与 `episode_dir` 建出骨架，不写标记文件。已有目录不动；之后新增的目录由 `add_fact` 写节点时自建，因此老 vault 不需要迁移。
- `add_fact`（`:474`）的 `kind` / `subject_type` 先过模板白名单，越界分别降级到 `topic` / `person`；节点小节与索引分区分别取自模板的「节点小节」「索引分类」。
- `rebuild_index`（`:543`）按模板分类顺序出分区，未知 kind 归入「其他」；节点清单遍历 vault 里**实际存在**的目录，所以模板改过目录名后，旧目录的历史节点仍会出现在索引页。

模板覆盖层在 vault 之外，不会被 `facts()` 的 `vault/*/*.md` 扫描，也不会被迁移逻辑当成知识节点。

#### 为什么是 Markdown 而不是表

知识图谱的价值在关联，而 Obsidian 的 graph view 只从正文的双链连边——表能存字段，存不出拓扑。旧的 `kb_episodes` / `kb_facts` / `kb_owners` 三张表已退场，留档说明见 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)。

原文也写成 Markdown（按天一个文件）：按天归档把文件数量压到每年 365 个，不至于把图挤满。

**事实不生成指向日记的双链**：溯源靠事实行尾注释的 `at` 与 `quote`，而不是把日期节点挂上去——每个事实都向时间线拉一条边的话，图会被日期节点淹没。因此日记文件自己连不到任何节点。

**但没有孤立点**：vault 根还有一张 `index.md`，它按类别列出全部事实（每条都指向所属人物节点）、按目录列出节点、按天列出最近十天的日记。所有文件都挂到这一张中心页上，graph view 才是连通的——新库、单聊、还没有第三方实体的时候尤其依赖它。

#### 文件格式

**实体节点**（默认 `人物/组织/话题` 三个目录，由模板决定）：frontmatter 带 `type` / `name` / `contact` / `owner` / `updated` / `updated_ts`，正文 `# 标题` 下按模板分类分小节；默认模板是身份、偏好、性格、目标、关系、事件、话题七节。每条形如：

```text
- 喜欢喝美式，不加糖。 <!-- fp:1a2b…|key:咖啡|kind:preference|conf:0.80|at:1767225600.0|src:extract|quote:我一般只要美式 -->
```

行尾 HTML 注释是这项设计的**唯一去重键**：`fp` 为 `sha1(kind|fact_key|value)[:16]`（`:491`），重复写入直接跳过（`:497`）。措辞不同的矛盾陈述各留一条，库不替人判断谁对——这与旧 `kb_facts_fingerprint` 部分唯一索引等价。

**事实行格式不由模板配置**：`kind` 只决定小节名与索引分类，`fp/key/conf/at/src/quote` 的排列是 `FACT_LINE`（`:62`）的解析契约，改了模板也读不回历史事实。

**对话日记**（`<episode_dir>/YYYY-MM-DD.md`，默认 `对话/`）：frontmatter 带 `type: conversations` / `date` / `owner` / `contact` / `channel_type`；正文每轮一个 `## 时间 · 联系人 · 私聊|群聊` 块，块内注释记录 `rid` / `at` / `outcome` / `contact` / `channel`，正文用 `**用户**` / `**助理**` 加引用块。同一 `request_id` 重试靠文本里是否已有 `rid:…|` 判重（`:465`），不需要事务。

**中心索引页**（默认 `index.md`，文件名由模板 `index_file` 决定）：frontmatter 只有 `type: index` / `owner` / `contact` / `updated`，正文依次是模板分类分区、实际目录节点、最近日记。分区标题取模板的「索引分类」，和节点里的小节名刻意不同——节点用「身份/偏好」，索引页用「用户信息/喜好」，改一处不会让旧内容留错位置；模板里没有的旧 kind 统一进「其他」。每个事实条目只列前 `index_limit`（默认 40）条，超出补一行「另有 N 条未列出」；日记只列 `index_days`（默认 10）天。索引页不写事实行、不带 `fp`，所以 `facts()` 不把它算进事实条数。

`_safe()`（`:83`）清洗文件名：把控制字符与 `<>:"/\\|?*#^[]` 一律替换成 `-`，压缩空白，去掉首尾空格与点号，截断 60 字——这些字符会破坏 Obsidian 的链接语法。清洗后同名会合并成一个节点，因此事件原名另存 frontmatter `name`，可人工核对。

#### 关联、索引与一致性

- **没有外键**：关系就是正文里的双链，`add_fact` 的 `links` 参数经 `_fact_line`（`:157`）把实体名写成链接。原文会被 `prune` 清理，事实不引用原文 id，只存 `at` 时间戳，所以原文过期不会让事实失效。
- **没有 schema 版本号**：Markdown 文件自带 frontmatter，未知键原样保留（`_rewrite_meta` 只更新 `updated`/`updated_ts`）。
- **`index.json` 是缓存不是数据源**：只存计数与游标；文件丢了 `_recount()`（`:383`）从 vault 现数回来，游标沿用旧值，不会把已提炼的原文重提一遍。
- **没有事务**：每次写入先落同目录临时文件再 `os.replace`（`:107`），读侧永远看到完整文件。目标文件被别的进程短暂持有时（Obsidian 正在索引同一个 vault），`os.replace` 会抛 `PermissionError`，所以写入带 `attempts=3` / `delay=0.05` 的退避重试：只用尽次数或遇到别的错误才抛出，抛出前清掉 `.tmp`，不留给编辑器索引成空节点。同一节点的并发写会丢一条，当前只有单进程写入。

#### 字段血缘（vault → 对象 → API → 前端）

- `owner` / `contact` / `channel_type`：由身份体系签发；`episode_owner()`（`:68`）优先用 `memory_owner`，没有身份就落到 `anon:dm|group:<名字>` 独立命名空间，绝不挂到别人名下。
- 读原文：`KnowledgeStore.read`（`:642`）跨 vault 归并，返回 `owner` / `contact` / `channel_type` / `request_id` / `user_text` / `reply_text` / `outcome` / `at`。
- 读事实：`KnowledgeStore.facts`（`:671`）遍历节点小节，多返回 `node` 与 `kind`；`query` 同时匹配 `fact_key` 与 `fact_value`。
- 会话维度：`sessions()`（`:709`）按 `contact`(+`channel_type`) 统计，左栏的「私聊/群聊」分组来自这里。
- 只读投影 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6) 只做转发：`KnowledgeView`（`src/dashboard/knowledge_view.py:22`）把 `KnowledgeStore` 的三个读接口原样透出，不再自己解析文件。

#### 冗余与迁移

`index.json` 与 vault 内容冗余，但方向明确：vault 是权威，索引可重建。`contact` 与 `owner` 并存不是冗余——前者是展示名，后者是身份稳定键。

`migrate_legacy(data_dir)`（`:801`）把 SQLite 时代的数据搬进 vault，成功后把原文件改名留底，不删：

| 旧文件 | 处理 |
|---|---|
| `data/knowledge.sqlite3` | 读 `kb_episodes` / `kb_facts` 写入 vault，改名为 `knowledge.legacy.sqlite3` |
| `data/knowledge/p-*/episodes.sqlite3` | 同上，改名为 `episodes.sqlite3.migrated` |
| `data/knowledge/p-*/facts.sqlite3` | 同上，改名为 `facts.sqlite3.migrated` |
| `data/knowledge/index.sqlite3` | 只改名 `index.sqlite3.migrated` |
| `data/business.sqlite3` 的 `memory` 表 | 每条搬成 `kind=profile` 的事实，`source=memory-migration`，原表保留 |

迁移是幂等的：`record` 与 `add_fact` 都靠 `rid` / `fp` 判重。**升级后必须在停服状态手动跑一次 `python -m butler knowledge-migrate`**，否则旧库里的原文与事实不会出现在 vault 里。

**留底前必须 checkpoint**：`_import_sqlite`（`:755`）用 `mode=ro` 只读 URI 打开旧库，读得到 WAL 里的行却永远不会把 WAL 合并回主库；紧接着 `replace` 改名后，`-wal` / `-shm` 的名字还停在旧文件名上，SQLite 不再认这对边车，留底库就成了空壳——实测 `facts.sqlite3.migrated` 不带 WAL 时连 `kb_facts` 表都读不出来。所以四处改名之前都先调 `_checkpoint_legacy`（`:734`）：用读写连接跑 `PRAGMA wal_checkpoint(TRUNCATE)`，再清掉残留边车。这段缺陷在首次真实迁移后才发现，见 [raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)。

#### 读写符号与测试

写：`record`（`:451`）追加日记块；`add_fact`（`:474`）追加节点事实行；`set_extracted_at`（`:516`）推进提炼游标；`prune`（`:526`）只删过期日记文件，节点事实不参与过期。

每次写完都调 `rebuild_index`（`:543`）重画中心索引页；`prune` 删到东西时也会把所有人的索引页重画一遍，免得索引里留着已删除日记的断链。

读：`owners`（`:430`）、`episodes_of`（`:626`）、`read`（`:642`）、`facts`（`:671`）、`sessions`（`:709`）。`close()`（`:622`）保留为空方法，让调用方不必区分新旧实现。

调用方：[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15) 的 `_record_episode` 调 `record`；[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774) 调 `episodes_of` / `add_fact` / `set_extracted_at`；[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) 调 `extracted_at` 与 `prune`。

本地用例（`tests/` 不入 Git）：`test_knowledge_store.py` 覆盖双链生成、指纹去重、`prune` 不动事实、索引重建、索引页分类分组、过期日记不留断链、索引页不计入事实条数；`test_knowledge_template.py` 覆盖模板新增目录/分类/规则落到骨架与索引、`episode_dir` / `index_file` 可配置、坏模板回退；`test_knowledge_extract.py` 覆盖解析容错与游标；`test_knowledge_view.py` 覆盖只读投影、模板分类下发与 HTTP 路由。

#### 代码依据与修改来源

- `src/butler/runtime/knowledge_store.py:1` — 模块说明：一人一个 Obsidian vault
- `src/butler/runtime/knowledge_store.py:77` — `def owner_slug(owner):`
- `src/butler/runtime/knowledge_store.py:83` — `def _safe(name, fallback='未命名'):`
- `src/butler/runtime/knowledge_store.py:107` — `def _atomic_write(path, text, attempts=3, delay=0.05):`
- `src/butler/runtime/knowledge_store.py:318` — `class KnowledgeStore:`
- `src/butler/runtime/knowledge_store.py:442` — `def _ensure_vault(self, owner):`（首次写入按模板建骨架）
- `src/butler/runtime/knowledge_store.py:457` — `def record(self, owner, contact, channel_type, request_id, user_text,`
- `src/butler/runtime/knowledge_store.py:480` — `def add_fact(self, owner, contact, fact_value, *, kind='topic', fact_key='',`
- `src/butler/runtime/knowledge_store.py:677` — `def episodes_of(self, owner, after_at=0.0, limit=200):`
- `src/butler/runtime/knowledge_store.py:722` — `def facts(self, owner='', query='', limit=50, offset=0, contact=''):`
- `src/butler/runtime/knowledge_store.py:50` — `FACT_KINDS = LEGACY_KINDS`（兼容默认值；实际分类来自模板）
- `src/butler/runtime/knowledge_store.py:53` — `INDEX_SECTIONS`（索引页默认中文小标题）
- `src/butler/runtime/knowledge_store.py:57` — `INDEX_FILE = 'index.md'`（默认值；实际文件名来自模板）
- `src/butler/runtime/knowledge_store.py:346` — `def index_page_path(self, owner):`
- `src/butler/runtime/knowledge_store.py:594` — `def rebuild_index(self, owner):`
- `src/butler/runtime/knowledge_store.py:734` — `def _checkpoint_legacy(path):`
- `src/butler/runtime/knowledge_store.py:801` — `def migrate_legacy(data_dir, log=None):`
- `src/butler/runtime/knowledge_template.py:154` — `DEFAULT_TEMPLATE = GraphTemplate(`
- `plugins/butler-wechat/knowledge/graph-template.md:21` — `## 节点目录`
- `src/dashboard/knowledge_view.py:22` — `class KnowledgeView:`
- `src/dashboard/routes.py:43` — `("GET", "/api/knowledge", knowledge.read),`

[raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)

[raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)

[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)

[raw/changes/2026-11-01-knowledge-atomic-retry](knowledge-vault.md#doc-8614fbc4e2f39c)

[raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。

#### 本次核对

群聊合并是管理台查询与分页过滤。owner、日记与事实节点的存储沿用，展示范围见 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)。 来源 [raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)。

#### 本次核对

单条事实删除在存储锁内原子替换节点，保留其他事实和日记。目录事实数及中心索引同步重建。删除定位与接口见 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 小潮日记接入核对

复核共享路由表，知识库和对话记录的读取路径仍对应原处理器。小潮日记使用独立的文件目录。 来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。
<!-- end-migrated-part: doc-dc9956670d38fd -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [知识库中心索引页与七类事实分组影响分析](#doc-528d62fcf07d59) · `llm wiki/wxbot/impacts/2026-11-01-knowledge-atlas-index.md`
- [用户知识库改为 Obsidian Markdown 图谱影响分析](#doc-b92e2632af0e9b) · `llm wiki/wxbot/impacts/2026-11-01-knowledge-vault-graph.md`
- [知识图谱模板外部化与在线编辑影响分析](#doc-f77e7236a67711) · `llm wiki/wxbot/impacts/2026-11-02-knowledge-graph-template.md`
- [知识库逐条删除](#doc-2d4c142263c11b) · `llm wiki/wxbot/impacts/2026-11-05-delete-knowledge-fact.md`
- [知识库按群汇总与来源标识](#doc-53fb2c0d450b09) · `llm wiki/wxbot/impacts/2026-11-05-knowledge-group-sources.md`
- [知识库加中心索引页与七类事实分组](#doc-69eb9deaf900e3) · `llm wiki/wxbot/raw/changes/2026-11-01-knowledge-atlas-index.md`
- [知识库写入在文件被占用时退避重试](#doc-8614fbc4e2f39c) · `llm wiki/wxbot/raw/changes/2026-11-01-knowledge-atomic-retry.md`
- [L1 聊天原文落库与只读看板](#doc-697690fcf2df43) · `llm wiki/wxbot/raw/changes/2026-11-01-knowledge-episodes.md`
- [迁移改动后复核知识库词条来源](#doc-97b2533a5ffcf7) · `llm wiki/wxbot/raw/changes/2026-11-01-knowledge-migrate-source-recheck.md`
- [知识库迁移改名留底前先合并 WAL](#doc-06dbdfdc7302a4) · `llm wiki/wxbot/raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint.md`
- [会话维度：左栏按人、右栏按私聊/群聊再筛](#doc-ba214c308af8ff) · `llm wiki/wxbot/raw/changes/2026-11-01-knowledge-sessions.md`
- [知识库拆分为一人一库并新增提炼事实库](#doc-c0bff474452694) · `llm wiki/wxbot/raw/changes/2026-11-01-knowledge-sharding.md`
- [知识库 vault 词条与实现对齐](#doc-3f269e1ad8b05e) · `llm wiki/wxbot/raw/changes/2026-11-01-knowledge-vault-alignment.md`
- [用户知识库改为一人一个 Obsidian vault 并删除 memory 链路](#doc-13c52ea2bba75a) · `llm wiki/wxbot/raw/changes/2026-11-01-knowledge-vault-graph.md`
- [知识图谱模板外部化为 Markdown 并支持管理台在线编辑](#doc-a582ec7ef75fe6) · `llm wiki/wxbot/raw/changes/2026-11-02-knowledge-graph-template.md`
- [修改记录](#doc-dde024d7417249) · `llm wiki/wxbot/raw/changes/2026-11-05-delete-knowledge-fact.md`
- [修改记录](#doc-867b5eee05957a) · `llm wiki/wxbot/raw/changes/2026-11-05-knowledge-group-sources.md`

<a id="doc-528d62fcf07d59"></a>

### 知识库中心索引页与七类事实分组影响分析

来源：`llm wiki/wxbot/impacts/2026-11-01-knowledge-atlas-index.md:1`。

```yaml
type: impact
status: completed
date: '2026-11-01'
```
### 知识库中心索引页与七类事实分组影响分析

#### 需求关键词与图谱命中

需求：vault 虽然已经是 Obsidian 图谱，但单聊、新库里只有「人物/<联系人>」与若干天日记两个孤立点，要求「索引之间关联」；同时补上用户点名的分类（用户信息、喜好、性格、目标）。

图谱命中：[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)。

覆盖缺口：图谱没有「中心索引页」这个概念，也没有 `personality` / `goal` 两类事实的记录；本次在 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 新增「中心索引页」小节，并把三类 kind 白名单一起写清。

#### 要改的文件、符号与调用方

- `src/butler/runtime/knowledge_store.py`：新增 `index_page_path`、`rebuild_index` 与四个 `INDEX_*` 常量；`FACT_KINDS` / `FACT_SECTIONS` 扩到七类。调用方是 `record`（[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15) 的 `_record_episode`）、`add_fact`（[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)）、`prune`（[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) 的调度线程）。
- `src/butler/runtime/knowledge_extract.py`：`KINDS` 与 `PROMPT` 同步七类，否则模型不会产出性格与目标。
- `web/src/views/FactsView.vue`：`KINDS` 中文映射补两项，否则新类型显示成「关注话题」。

#### 接口与前端契约

`GET /api/knowledge/facts` 的字段、分页、排序都不变；只有 `kind` 的取值域从五个变七个。前端类型列是纯映射，不新增列、不新增请求。

#### 数据库与字段血缘

无表结构变更：`index.md` 是 vault 里的派生文件，frontmatter 只带 `type: index` / `owner` / `contact` / `updated`，没有 `fp`，因此不会进入 `facts()` 的统计，也不会被当成实体节点。分类标题走两套常量（节点小节 vs 索引页标题），互不影响。

#### 风险、验证、异步任务与回滚

风险：`rebuild_index` 每写一次就重扫整份 vault，写路径从 O(1) 变成 O(节点文件数)；索引页事实只列前 40 条、日记只列 10 天，超出部分不展示。异步侧 `prune` 会多写 N 份索引页，仍在既有调度线程内。

验证：`tests/butler/test_knowledge_store.py` 新增四条覆盖双链、分类分组、过期断链、不计入事实；`pytest tests/butler tests/dashboard` 全绿；`npm run build` 与 `npm run smoke` 通过。

回滚：删掉 `rebuild_index` 与三处调用及 `INDEX_*` 常量即可，`index.md` 是纯派生文件，删掉不影响任何事实与日记。

#### 实际改动与 raw 归档

实施结果与分析一致，附带三处顺带订正（同一批词条行号已因插入点后移）：

- [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 的读符号行号（`read` / `sessions` / `owners` / `set_extracted_at` / `prune` / `close`）与 `episode_owner`、`_recount`、`_import_sqlite` 全部按当前源码重算。
- [symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) 把退场名 `extracted_upto` 改成 `extracted_at`，并把 `src/butler/server.py` 的三个行号各减一（与实际 `construct/start/stop` 位置对齐）。
- [concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15) 的旁路支线仍写着 SQLite 的 `p-<slug>/episodes.sqlite3`，改为 vault 的 `对话/YYYY-MM-DD.md` 并补上 `_record_episode` 代号。

raw 归档：[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)。
<!-- end-migrated-part: doc-528d62fcf07d59 -->

<a id="doc-b92e2632af0e9b"></a>

### 用户知识库改为 Obsidian Markdown 图谱影响分析

来源：`llm wiki/wxbot/impacts/2026-11-01-knowledge-vault-graph.md:1`。

```yaml
type: impact
status: completed
date: '2026-11-01'
```
### 用户知识库改为 Obsidian Markdown 图谱影响分析

#### 需求关键词与图谱命中

需求：用户知识不再存平表，改成一人一个 Obsidian vault——实体节点是 Markdown、关系用 `[[双链]]`、原文按天写成日记文件；同时删掉并行的 `memory` 表与工具，只留一套。

图谱命中：[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)、[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)、[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/plugin](resident-skills.md#doc-709338d3e083eb)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。

覆盖缺口：图谱没有 `memory` 表、`UserRegistry.recall/change_memory`、`butler-memory` 工具 skill 的词条，也没有 `web/src/components/UserDialog.vue` 的记忆面板。已按源码补齐，入库时新建 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 取代三张 kb_* 词条。

#### 要改的文件、符号与调用方

存储层 `src/butler/runtime/knowledge_store.py` 整体重写：`KnowledgeStore` 保留类名与 `record/facts/read/owners/prune/episodes_of/close` 方法名，内部从 SQLite 换成 vault 文件；游标由 `extracted_upto(owner)->int` 改为 `extracted_at(owner)->float`。

- 写入方：`core.py:304` `_record_episode` → `record`；`knowledge_extract.py:88` `extract` → `episodes_of/add_fact/set_extracted_at`。
- 调度方：`knowledge_auto.py:145` `_pending` 与 `:182` `run_once` 读游标；`__main__.py:60/66` 两个 CLI 子命令。
- 只读投影：`src/dashboard/knowledge_view.py` 从直接读三张表改为委托 `KnowledgeStore`，删除 `read_episodes/_fact_where` 等重复实现。
- 注入方：`core.py:353-357` 由 `registry.recall` 换成 `knowledge.facts(owner=...)`，事件名 `butler_memory` → `butler_knowledge`，字段 `memory_count` → `fact_count`（同步 `dashboard/flow_view.py:15,18,29` 与 `dashboard/workflow_view.py:25`）。

删除的 memory 链路：`business.py` 的 `memory` 表与 `set_memory/delete_memory/memories/runtime_memory/_memory_changed`；`identity/contact_identity.py` 的 `memory_items/conflict_memories/user_memory_variants` 与两处 `memory_version` 自增；`identity/user_registry.py` 的 `recall/change_memory`、`_row` 的 `memory_count`、`link` 的 notes 合并、`adopt_legacy` 的 notes 迁移；`agent/tools.py` 的四个 memory 工具与分发；`plugins/butler-wechat/skills/tools/butler-memory/`。

#### 接口与前端契约

`GET /api/knowledge` 与 `GET /api/knowledge/facts` 的响应字段保持不变（`owner/contact/kind/fact_key/fact_value/quote/episode_at/confidence/source/created`），只换数据来源；`FactsView.vue` 不需要改。

删除的接口：`GET /api/contacts/memory`（`dashboard/routes.py:34`）、`GET /api/users/memory`（`:37`）、`dashboard/user_admin.py:15` 的 `/v1/users/memory`、`identity/user_api.py:51,67-68,109-110` 的 `memory_set/memory_delete` 动作。前端 `UserDialog.vue` 的记忆面板、`ContactsView.vue` 与 `contactState.js` 的 `memory_*` 状态一并移除。

#### 数据库与字段血缘

`kb_episodes`/`kb_facts`/`kb_owners` 三张表退场，`data/knowledge/*.sqlite3` 在迁移后改名为 `*.migrated` 留底，不再被读写。`business.sqlite3` 的 `memory`、`user_memory_variants` 两张表与 `user_profiles.memory_version` 列退场；`memory_version` 参与会话 scope 哈希（`backends/codex.py:62`、`compatible.py:74`），移除后旧会话 id 失配一次，表现为各自重开一个空会话，可接受。

新增 `data/knowledge/index.json`：只存 owner 目录、条数与提炼游标，可由 vault 重建，不是第二份知识。vault 内节点 frontmatter 带 `owner/name/type`，事实行尾带 `<!-- fp:…|key:…|kind:…|conf:…|at:…|quote:… -->` 去重指纹，等价于原 `kb_facts_fingerprint` 唯一索引。

#### 风险、验证、异步任务与回滚

风险一：Markdown 是文本，并发写靠原子替换，没有事务；提取与回复可能同一秒写不同文件，互不覆盖，但同一节点并发写会丢一条。当前单进程写入，风险低。

风险二：`_safe()` 清洗文件名会改变实体名，两个实体清洗后同名会合并成一个节点；节点名写入 frontmatter 保留原名，可核对。

风险三：游标从 `episode.id` 改成时间戳，边界上的同一秒可能重复提取一次；指纹去重保证不产生重复事实。

验证：`tests/butler/test_knowledge_store.py`、`test_knowledge_extract.py`、`test_knowledge_auto.py`、`test_knowledge_capture.py`、`tests/dashboard/test_knowledge_view.py` 五个文件按新语义改写；另跑 `compileall src/butler`、`pytest tests/butler tests/dashboard`。不启动服务、不发微信、不调用模型。

回滚：vault 与 `*.migrated` 都在 `data/` 下，回滚代码即可让旧库重新生效；`memory` 表删除前先在 `data/knowledge/p-*/vault/` 里落成 Markdown，数据不丢。

#### 实际改动与 raw 归档

实施结果与分析基本一致，偏差与补充：

- **`FactsView.vue` 是新建而非改动**：分析阶段假设它已存在，实际是本次新建（连同 `KnowledgeView.vue` 与 `web/src/styles/knowledge.css`）。页面结构、类型中文映射、会话 chips 都按新契约重写。
- **`catalogue.validate` 改为降级而非报错**：技能目录跟着安装走，删掉 `butler-memory` 后，策略里残留的白名单条目会被静默剔除并记日志，不再让整份策略判死。`tests/unit/codex/test_codex_foundation.py` 的断言随之改写。
- **事实行的 `node` 字段没有对外暴露**：`KnowledgeStore.facts` 会算出事实所属实体节点，但 `knowledge_view.FACT_FIELDS` 白名单未收录，接口仍只回 10 个字段——图谱的「节点」维度在管理台上看不到，是已知缺口。
- **`merge_users` 不搬 vault**：分析阶段未覆盖。身份合并只动 SQLite，源 vault 留在磁盘且 `index.json` 仍记着它；文件搬动不在事务内，回滚会造成不可恢复的丢失，因此有意不做。
- **`knowledge-migrate` 必须停服手动跑**：不是自动升级步骤，README 与 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 都已写明。
- **`episodes_of` 签名从 `after_id` 改为 `after_at`**：游标语义从「原文 id 水位」变成时间水位，`knowledge_extract` / `knowledge_auto` 两个调用方一起改。
- **测试补充**：`tests/unit/test_project_wiki.py` 修掉一处写死日期的用例；`web/scripts/smoke.mjs` 的 13 处 memory 断言改写成「入口已下线」。

校验：`pytest tests` 只剩 3 个与本次无关的既有失败；`npm run build` 与 `npm run smoke` 通过（9 个页面）；Hallmark `sloplint --scope app` 对两个新页面 0 FAIL / 0 WARN；图谱 `lint` 为 OK。

raw 归档：[raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)（27 个词条已 ingest）。
<!-- end-migrated-part: doc-b92e2632af0e9b -->

<a id="doc-f77e7236a67711"></a>

### 知识图谱模板外部化与在线编辑影响分析

来源：`llm wiki/wxbot/impacts/2026-11-02-knowledge-graph-template.md:1`。

```yaml
type: impact
status: completed
date: '2026-11-02'
```
### 知识图谱模板外部化与在线编辑影响分析

#### 需求关键词与图谱命中

需求：把知识图谱的目录、事实分类、索引分区与提炼规则从代码常量改成一份 Markdown 模板；新建每个用户的 vault 时按模板生成骨架；模板支持新增节点目录、新增分类、追加提炼规则；管理台新增「知识模板」页展示并编辑该模板。

图谱命中：[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)、[symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)、[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。

覆盖缺口：图谱没有「模板」这一概念，也没有 `dashboard/config_editor.py` 的写入约定（锁 + 版本 + 备份 + 原子替换）词条，本次按源码补齐并新建模板相关词条。

#### 要改的文件、符号与调用方

新增 `src/butler/runtime/knowledge_template.py`：`GraphTemplate`、`Kind`、`NodeType`、`parse_template`（严格，带行号）、`load_template`（宽松，失败回退）、mtime 缓存、`DEFAULT_TEMPLATE`。

新增 `plugins/butler-wechat/knowledge/graph-template.md`：内置默认模板，随插件版本分发，页面只读。

改造 `src/butler/runtime/knowledge_store.py`：

- `__init__` 增加 `template` 参数，导入模板模块；模块级 `FACT_KINDS/FACT_SECTIONS/INDEX_SECTIONS/NODE_DIRS` 保留为默认值来源，内部改为读 `self.template`。
- `node_path:325` 由 `NODE_DIRS` 改为 `self.template.node_dir()`。
- `add_fact:459` 的 kind 白名单与 `:474` 的小节名来自模板；未知 kind 落「其他」。
- `rebuild_index:540-561` 由固定 7 类、3 个目录改为模板顺序 + 实际存在的目录 + 未知分类的「其他」分区。
- `EPISODE_DIR` 的所有使用点（`episodes_dir/prune/sessions/read/facts/_recount`）改为 `self.template.episode_dir`。
- `record` 首次写入前调用 `_ensure_vault()` 按模板建目录，不新增标记文件。

改造 `src/butler/runtime/knowledge_extract.py`：`PROMPT` 拆为 `build_prompt(template, contact)`；`parse_facts` 接受模板白名单；内置 6 条规则固定不可删，模板规则追加在后。

新增 `src/dashboard/knowledge_template_view.py`：读写 `data/knowledge/template.md`，复用 `common.config_lock` 与 `config_view.source_version`，写入前备份并原子替换。

新增 `src/dashboard/api/knowledge.py::template_read/template_save` 与 `routes.py` 两条路由，并加入 `BUSINESS_GET/BUSINESS_POST`。

前端新增 `web/src/views/KnowledgeTemplateView.vue`，注册 `router.js` 的 TABS 与 `App.vue` 组件映射；`FactsView.vue` 的 `KINDS` 常量改为接口下发，避免新增分类显示成「关注话题」。

调用方不变：`core.py:117`、`__main__.py:60`、`knowledge_auto.py:165` 都持有同一个 `KnowledgeStore` 实例，模板注入点集中在构造函数。

#### 接口与前端契约

新增 `GET /api/knowledge/template`：返回生效来源（override/plugin/builtin）、路径、version（sha256）、modified_at、content、解析摘要（kinds/node_types/rules/index_title）。

新增 `POST /api/knowledge/template`：`{action: validate|save|reset, content, version, acknowledge}`；400 返回带行号的校验错误，409 为版本冲突，503 为非本机安装。

`GET /api/knowledge/facts` 响应新增 `kinds` 与 `node_types` 两个数组（只增字段，不改旧字段），供前端动态映射分类名。

`FactsView.vue` 保留原有表格与筛选，仅把常量映射改为「接口下发 + 原始 key 兜底」。

#### 数据库与字段血缘

不涉及 SQL。模板两层：`plugins/butler-wechat/knowledge/graph-template.md`（只读）与 `data/knowledge/template.md`（可写覆盖层），后者在 vault 之外，不会被 `facts()` 的 `vault/*/*.md` 扫描。

事实行格式 `<!-- fp|key|kind|conf|at|src|quote -->` 不变，仍由 `FACT_LINE` 正则读回；模板只影响目录名、小节名、索引分区名与 prompt，不改变行格式。`index.json` 结构不变，不新增字段。

#### 风险、验证、异步任务与回滚

风险一：模板写坏会导致提炼 prompt 或索引页异常。对策：运行时宽松解析失败回退默认；页面保存前强制严格校验；模板规则只追加，内置 6 条不可删。

风险二：模板成为提示词注入面。对策：只用白名单字段拼 prompt，限长 2400 字，模板是安装者本地文件，不是外部输入。

风险三：改模板不改历史。旧 kind 在新模板中缺失时归入「其他」，旧节点目录若被删除仍会出现在索引页的未识别目录中，不丢数据。

风险四：Windows 下文件被占用。对策：保存走临时文件 + `os.replace` 并退避重试；失败给明确错误。

验证：新增 `tests/butler/test_knowledge_template.py`；改写或补充 `test_knowledge_store.py`、`test_knowledge_extract.py`；`tests/dashboard/test_knowledge_view.py` 补模板接口用例。全部离线，不启动服务、不发消息、不调模型。

回滚：删除 `data/knowledge/template.md` 即回到内置模板；代码回滚后模板文件被忽略，vault 不需要迁移。

#### 实际改动与 raw 归档

已按方案落地，未偏离。实际改动与验证记录见 [raw/changes/2026-11-02-knowledge-graph-template](knowledge-vault.md#doc-a582ec7ef75fe6)：

- 新增模板模块与随插件分发的 `knowledge/graph-template.md`；`KnowledgeStore` 与 `KnowledgeExtractor` 全部改读模板，默认值与旧行为一致。
- 新增两条模板路由与 `KnowledgeTemplateView`，页面支持校验、保存、恢复内置；`FactsView` 改为接口下发分类。
- 不涉及 SQL 或 vault 迁移；删除 `data/knowledge/template.md` 即回滚到内置模板。
- 验证：相关 5 个测试文件 65 项通过；`npm run build` / `npm run smoke` 通过（导航 9 项）；Hallmark 静态 0 FAIL、真实渲染 4 视口 0 FAIL，剩余 1 REFLEX + 1 WARN 属既有导航壳，已披露未清理。
<!-- end-migrated-part: doc-f77e7236a67711 -->

<a id="doc-2d4c142263c11b"></a>

### 知识库逐条删除

来源：`llm wiki/wxbot/impacts/2026-11-05-delete-knowledge-fact.md:1`。

```yaml
type: impact
status: completed
date: 2026-11-05
```
### 知识库逐条删除

#### 入口与字段

沿 [apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 与 [symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) 核对。`knowledge_store.py:191,671` 解析 Markdown 事实；事实列表新增从 owner、相对节点位置和事实行计算的 `fact_id`，旧事实无需迁移。

- `web/src/views/FactsView.vue:312` 新增逐条按钮和确认，成功刷新当前筛选及分页。
- `src/dashboard/routes.py:77`、`src/dashboard/api/knowledge.py:45` 新增本机确认 POST，经现有服务凭据转发到 `src/butler/server.py:335` 附近的 Butler 写端点。只收 owner、fact_id 和 acknowledge。
- Butler 复用知识提炼跨进程锁，存储复用进程内锁和原子替换，删除精确匹配的事实行并重建统计及索引。保留节点、原文和提炼游标。不新增 DB 字段、后台任务或删除聊天数据。

#### 验证与回滚

临时库覆盖同文多节点、原文与游标、旧编号、并发提炼和索引写入失败。假数据验证确认、取消、错误及刷新。回滚代码和 dist 即移除功能，已删除的事实只能从既有备份恢复。

实际变更见 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。
<!-- end-migrated-part: doc-2d4c142263c11b -->

<a id="doc-53fb2c0d450b09"></a>

### 知识库按群汇总与来源标识

来源：`llm wiki/wxbot/impacts/2026-11-05-knowledge-group-sources.md:1`。

```yaml
type: impact
status: completed
date: 2026-11-05
```
### 知识库按群汇总与来源标识

#### 来源和缺口

[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6)、[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15) 说明了 owner 分档与节点 contact，知识库侧栏缺少按群汇总和归档成员展示。旧事实只有节点级 contact，缺少逐条通道和消息标识。

#### 改动与边界

- `src/dashboard/knowledge_view.py:42,71` 和 `src/dashboard/api/knowledge.py:10,40`：事实响应保留 owners，补充按群汇总、来源人名、群筛选。会话目录确认群来源，群和私聊同名且无法区分的事实不放入群筛选。
- `src/butler/runtime/knowledge_store.py:671`：在现有跨 vault 分页前接受已验证的 owner 集合，保留原调用。
- `web/src/views/FactsView.vue:36,229`：同群显示一项，事实表展示来源。保留个人筛选、搜索、分页和提炼入口。
- 群成员名从本地身份库只读解析，无 schema、vault、队列、后台提炼或权限迁移。回滚源码和 dist 即恢复原投影。

#### 验证

临时库覆盖多成员同群、匿名、同名私聊、跨成员分页和旧事实保留，前端用假数据验证分组与来源。

实际变更见 [raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)。
<!-- end-migrated-part: doc-53fb2c0d450b09 -->

<a id="doc-69eb9deaf900e3"></a>

### 知识库加中心索引页与七类事实分组

来源：`llm wiki/wxbot/raw/changes/2026-11-01-knowledge-atlas-index.md:1`。

```yaml
type: change
title: 知识库加中心索引页与七类事实分组
pages:
- tables/knowledge-vault
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
- symbols/knowledge-extract
- symbols/knowledge-auto
- modules/web
- apis/dashboard-knowledge
- concepts/message-pipeline
```
### 知识库加中心索引页与七类事实分组

#### 目标与背景

`data/knowledge/p-*/vault` 已经是一人一个 Obsidian vault，但新库和纯单聊的 vault 里只有「人物/<联系人>」一个节点加若干天日记：事实行不引用日期，日记不引用节点，Obsidian 的 graph view 里就是两个互不相连的孤立点。目标是「索引之间关联」——图里必须有一张把节点与日记串起来的中心页。

顺带补上点名的分类维度（用户信息、喜好、性格、目标）：原来 `FACT_KINDS` / `FACT_SECTIONS` 只有 profile / preference / relation / event / topic 五类，模型提炼不出「性格」与「目标」。

#### 文件与代码位置

- `src/butler/runtime/knowledge_store.py`
  - 常量：`FACT_KINDS`（`:45`）与 `FACT_SECTIONS`（`:46`）扩到七类，新增 `personality`（性格）/ `goal`（目标）；新增 `INDEX_SECTIONS`（`:49`，索引页专用中文标题）、`INDEX_FILE`（`:54`）、`INDEX_LIMIT`（`:55`）、`INDEX_DAYS`（`:56`）。
  - 新增 `index_page_path(owner)`（`:312`）：vault 根下的 `index.md`。
  - 新增 `rebuild_index(owner)`（`:499`–`:559`）：扫节点文件收集全部事实行，按七类分组写成带 `[[双链]]` 的条目，再列出三目录节点与最近 `INDEX_DAYS` 天日记，最后 `_atomic_write` 落盘。
  - 三处调用：`record`（`:427`）、`add_fact`（`:463`）写完各重画一次；`prune`（`:493`）删到东西后遍历 `owners()` 全部重画。
  - 模块 docstring：删掉与实现不符的「事实可以双链溯源」，补 `index.md` 行与「为什么还有 index.md」一段。
- `src/butler/runtime/knowledge_extract.py`：`KINDS`（`:21`）同步扩到七类，`PROMPT`（`:24`）的 kind 行加 `personality（性格/说话方式）` 与 `goal（目标/打算）`。
- `web/src/views/FactsView.vue`：`KINDS`（`:10`）补 `personality: '性格'`、`goal: '目标'`。
- `tests/butler/test_knowledge_store.py`：新增四条（`:144`、`:156`、`:169`、`:181`）。

#### 接口与字段

- HTTP 契约不变：`GET /api/knowledge/facts` 的字段与形状没动，只是 `kind` 的取值域从五个变成七个（`profile` / `preference` / `personality` / `goal` / `relation` / `event` / `topic`）。越界值仍在写入时回落 `topic`，接口不会吐出第八种。
- 磁盘格式新增一种文件：`p-<slug>/vault/index.md`，frontmatter 为 `type: index` / `owner` / `contact` / `updated`。它不带 `fp` 注释，`facts()` 只扫 `*/*.md`（跳过日记目录），所以既不会被算成事实，也不会被当成节点。
- 分类标题分两层：节点小节名（`FACT_SECTIONS`，身份/偏好/性格/目标/关系/事件/话题）与索引页标题（`INDEX_SECTIONS`，用户信息/喜好/性格/目标/关系/经历/关注）刻意不同，节点小节改名时旧内容不会留错位置。

#### 数据库与迁移

不适用：知识库已不在 SQLite 里，这次只新增一个 Markdown 文件，没有表结构变更、没有迁移脚本。

已有 vault 不需要人工处理：下一条消息（`record`）、下一条事实（`add_fact`）或下一次清理（`prune`）都会顺手把 `index.md` 重画出来。

#### 前端消费点

`FactsView.vue` 的类型列通过 `KINDS` 映射中文，`kindOf`（`:207`）查不到时回落「关注话题」。不补这两行，新提炼出的性格与目标会显示成「关注话题」。索引页只在 Obsidian 里看，管理台不渲染它。

#### 测试与异步任务

`tests/butler/test_knowledge_store.py` 新增四条：

- `test_index_page_ties_nodes_and_days_together`（`:144`）：索引页落在 vault 根，正文同时含 `[[101]]` 与当天日期双链。
- `test_index_page_groups_facts_by_category`（`:156`）：四类事实分别出现在四个中文标题下。
- `test_index_page_drops_expired_day_links`（`:169`）：`prune` 删掉整天日记后索引页不再留该日期的断链。
- `test_index_page_is_not_counted_as_facts`（`:181`）：索引页不进入 `facts()['total']`。

`pytest tests/butler tests/dashboard` 全绿；`npm.cmd --prefix web run build` 与 `npm.cmd --prefix web run smoke` 通过。

异步任务：`prune` 由 [symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) 的调度线程发起，现在每轮清理会多写 N 份索引页（N = 目录里的人数）。这是既有线程内的同步文件写，没有新增线程或队列。

#### 风险与回滚

- `rebuild_index` 每次都重扫整份 vault 收集事实：写一轮对话多一次 O(全部节点文件) 扫描。当前规模可以接受；人数或事实量上来后要改成增量维护。
- 索引页有上限：事实每类只列前 40 条（补一行「另有 N 条未列出」），日记只列 10 天。改 `INDEX_LIMIT` / `INDEX_DAYS` 即可，不需要迁移。
- 索引页会被覆盖，文件里已写明「本文件由 Butler 自动重建，手改会被覆盖」；想保留的手写笔记应放到别的文件。
- 回滚：删掉 `rebuild_index` 与三处调用、去掉 `INDEX_*` 常量与两个新 kind，再删 vault 里的 `index.md`。事实与日记都不受影响——索引页是纯派生数据。

[impacts/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-528d62fcf07d59)
<!-- end-migrated-part: doc-69eb9deaf900e3 -->

<a id="doc-8614fbc4e2f39c"></a>

### 知识库写入在文件被占用时退避重试

来源：`llm wiki/wxbot/raw/changes/2026-11-01-knowledge-atomic-retry.md:1`。

```yaml
type: change
title: 知识库写入在文件被占用时退避重试
pages:
- tables/knowledge-vault
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
- apis/dashboard-knowledge
- symbols/knowledge-extract
```
### 知识库写入在文件被占用时退避重试

#### 目标与背景

Obsidian 打开一个 vault 后会持续索引目录。Butler 正好在这时写 `index.md` 或节点文件，`os.replace` 会抛 `PermissionError: [WinError 5] 拒绝访问`。

这不是推测：给 101 的 vault 灌演示数据时第 2 条 `add_fact` 就撞上了，`index.md.tmp` 留在 vault 根，被 Obsidian 当成一个空文件索引；删掉残留 tmp 后立即重试就成功。更麻烦的是 [concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15) 的 `_record_episode` 把异常记进日志就吞掉（`src/butler/agent/core.py:328`），代价是那一轮对话没落库，且没有任何补偿。这类冲突只持续几十毫秒，所以让写入自己等一下再试。

#### 文件与代码位置

- `src/butler/runtime/knowledge_store.py:104` — `_atomic_write(path, text, attempts=3, delay=0.05)`。原来是「写 tmp + `os.replace`」两行直写；现在把两步包进 `for attempt in range(tries)`，只捕获 `PermissionError`，最后一次仍失败时用 `suppress(OSError)` 清掉 tmp 再 `raise`。
- `src/butler/runtime/knowledge_store.py:5` — `from contextlib import closing, suppress`，新增 `suppress`：清理 tmp 失败不能把原始异常盖掉。
- 四个调用点没有改动：`_save`（`:346`）、`record`（`:440`）、`add_fact`（`:475`）、`rebuild_index`（`:573`）。`rebuild_index` 的调用点是收尾那一行（`:573`），函数定义在 `:514`。
- 本次改动让 104 行之后的符号整体下移 15 行，六个词条里指向该文件的行号同时重算：`class KnowledgeStore` 286→301、`record` 408→423、`add_fact` 430→445、`index_page_path` 312→327、`rebuild_index` 499→514、`episodes_of` 565→580、`read` 581→596、`facts` 610→625、`sessions` 648→663、`_checkpoint_legacy` 673→688、`_import_sqlite` 694→709、`_import_memory` 718→733、`migrate_legacy` 740→755、`_touch` 334→349、`_catalog` 319→334、`_recount` 355→370、`owners` 402→417、`extracted_at` 467→482、`set_extracted_at` 472→487、`prune` 482→497、`close` 561→576，以及迁移段里 `kb_episodes` 700→715、`kb_facts` 706→721、`index` 变量 763→778。

#### 接口与字段

不适用。`_atomic_write` 是模块内私有函数，新增的 `attempts` / `delay` 两个参数都有默认值，没有调用点传参；HTTP 接口、前端 GET 参数、Markdown 文件格式与事实行尾注释全部不变。

#### 数据库与迁移

不适用。知识库已不在 SQLite 里，写入目标是 Markdown 文件；重试不改变文件内容，也不额外产生文件——成功时 tmp 已被 `os.replace` 移走，放弃时被显式删掉。

#### 前端消费点

不适用。管理台对知识库只读，写入路径全在 Butler 侧。

#### 测试与异步任务

`tests/butler/test_knowledge_store.py` 新增四条：

- `:260` 前两次 `os.replace` 抛 `PermissionError`、第三次成功 → 内容落盘，且不留 `note.md.tmp`。
- `:284` `time.sleep` 收到的序列是 `[0.05, 0.1]`：退避递增，三次尝试最坏多等 150ms。
- `:303` 一直失败 → 抛 `PermissionError`，tmp 已清、目标文件没有被写成半截。
- `:317` `OSError(28)`（磁盘满）→ `os.replace` 只被调一次，不重试。

用例都通过 `monkeypatch.setattr` 替换 `os.replace` / `time.sleep`，不改真实文件系统行为；`tests/butler/test_knowledge_store.py`、`test_knowledge_extract.py`、`test_knowledge_auto.py`、`test_knowledge_capture.py` 四个文件 50 条全过。

异步任务：`_record_episode` 仍在请求返回前同步调用 `record`，单次写入的最坏耗时从「一次 `os.replace`」变成「三次 `os.replace` + 150ms」。

#### 风险与回滚

- 重试发生在 `KnowledgeStore._lock` 内（`record` / `add_fact` 的 `with self._lock` 包着 `_atomic_write`），最坏多阻塞 150ms。知识库写入是单进程调用，不阻塞对话生成，只让该轮落库晚一点。
- `PermissionError` 也可能是真实权限问题（只读目录、ACL 拒绝）。这时会白等 150ms 再抛，日志里的异常与改动前一致。
- 非 `PermissionError` 的错误（磁盘满、路径不存在）不重试，保持原来的失败速度。
- 回滚：把 `_atomic_write` 恢复成「写 tmp + `os.replace`」两行版本即可，无数据迁移、无文件格式变化；回滚后须同步把六个词条的行号减回 15。
<!-- end-migrated-part: doc-8614fbc4e2f39c -->

<a id="doc-697690fcf2df43"></a>

### L1 聊天原文落库与只读看板

来源：`llm wiki/wxbot/raw/changes/2026-11-01-knowledge-episodes.md:1`。

```yaml
type: change
title: L1 聊天原文落库与只读看板
pages: [tables/kb-episodes, apis/dashboard-knowledge, modules/butler, modules/dashboard, modules/web,
  apis/butler-handle, apis/dashboard-queue, apis/dashboard-workflow, symbols/butler-handle,
  symbols/butler-result, concepts/message-pipeline, concepts/model-error-contract]
```
### L1 聊天原文落库与只读看板

#### 目标与背景

三层知识库（L1 原文 → L2 事实 → L3 图谱）的第一步，只做原文沉淀：每轮对话写一条记录，管理台能按联系人翻看。

**边界是这次改动最重要的部分**：不抽取、不改 prompt、不新增线程、不动现有批次状态机。写库失败只记日志，绝不影响回复——上一轮的模型失败契约（[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)）不能因为多了一个落库动作而被削弱。

原文必须落在独立库：`business.sqlite3` 每次启动整库备份，把聊天原文塞进去会让备份体积随时间失控。

#### 文件与代码位置

- `src/butler/runtime/knowledge_store.py` — 新文件。`episode_owner`、`read_episodes`、`KnowledgeStore`（`_connect` / `_transaction` / `record` / `prune` / `read`），建表 SQL 在 `_SCHEMA`。
- `src/butler/agent/core.py:114` — `Butler.__init__` 构造 `self.knowledge`，`retention_days` 取自配置。
- `src/butler/agent/core.py:270` — `_handle_request` 里 `c = None` 提前初始化：异常可能发生在认人之前，落库要靠 `contact_name` 兜底。
- `src/butler/agent/core.py:293` — try 块内 `result` 赋值之后落 `ok` / `silent`。
- `src/butler/agent/core.py:298` — except 分支 `raise` 之前落 `error`，`reply=None`。
- `src/butler/agent/core.py:304` — 新增 `_record_episode`，内部 `try/except Exception` 全包，失败只 `self.log`，禁止上抛。
- `src/butler/config.py:73` — 新增 `knowledge_enabled` / `knowledge_retention_days` 两个默认值。
- `src/butler/config.py:192` — `load()` 读 `[knowledge]`，`retention_days` 校验为 1..3650 的整数。
- `src/butler/__main__.py:50` — 新增 `knowledge-prune` 子命令。
- `src/dashboard/knowledge_view.py` — 新文件，只读投影 `KnowledgeView`。
- `src/dashboard/api/knowledge.py` — 新文件，`read(ctx)` 胶水。
- `src/dashboard/routes.py:17`、`:43` — `BUSINESS_GET` 与 `ROUTES` 各加一条。
- `src/dashboard/server.py:49` — 导入 `KnowledgeView`，使其可通过 `RequestContext` 命名空间解析取到。
- `web/src/views/KnowledgeView.vue`、`web/src/styles/knowledge.css` — 新页面与窄屏样式。
- `web/src/router.js:7`、`web/src/App.vue:9`/`:18`/`:43`/`:67` — 注册页面、共享搜索框占位符、远端模式下隐藏。
- `config.butler.toml` — 新增 `[knowledge] enabled = true` / `retention_days = 90`（本地运行配置，不入 Git）。

**明确不写入的位置**：`_handle` 内部各 return 点（会重复记）、群聊的 `public` 群上下文快照（那是**其他成员**的发言，写进当前 owner 会造成跨人泄漏）、`handle()` 的 `ModelConfigurationError` 分支（没经过模型，不属于对话）。

#### 接口与字段

新增 `GET /api/knowledge`，参数 `contact`（精确）、`q`（`user_text` / `reply_text` 的 LIKE，`%` 与 `_` 转义）、`limit`（默认 50，截断 1..200）、`offset`。响应 `{available, rows[], total, contacts[], limit, offset, has_more}`，行内只有 `at` / `contact` / `channel_type` / `user_text` / `reply_text` / `outcome`；`owner` 与 `request_id` 不对外暴露。

**库不存在返回 `available: false` 而不是 404/500**：P0 默认就没有历史，空态不是错误。只有真正读不动（`sqlite3.Error`）才折成 `500` 且带 `read_only: true`，与 `/api/queue` 同形。

**`handle` 的契约一个字都没改**：请求体、响应字段、`meta.reply_complete`、`retry_safe` 全部维持原样，wxbot 适配器与队列 worker 不需要任何配合改动。

#### 数据库与迁移

新库 `cfg.data_path()/'knowledge.sqlite3'`，单表 `kb_episodes`，详见 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20)。

三个索引：`(owner, at DESC)` 供按人翻页、`(at)` 供清理扫描、部分唯一 `(owner, request_id) WHERE request_id <> ''` 供 `INSERT OR IGNORE` 去重。

**没有 schema 版本号，也没有迁移**：`CREATE TABLE IF NOT EXISTS` 一次建齐。**刻意不加 `state` 列**——P0 没有抽取流程，列一旦存在就会被误读成"这里有状态机"；P1 需要时 `ALTER TABLE ADD COLUMN state TEXT NOT NULL DEFAULT 'raw'` 补即可。

**库文件由第一次写入创建**（`KnowledgeStore._connect` 惰性连接），因此 `enabled=false` 时一个字节都不落盘。只读侧永远不建库、不建表。

#### 前端消费点

`KnowledgeView.vue` 新增 `/knowledge` 一页，登记进共享导航壳的「消息监控」组。纯只读：不提供删除、编辑、导出，也没有任何 POST 路由。

四状态齐备：加载中、空态（`available=false` 显示「尚未记录任何对话」而非报错）、错误、有数据。表格列是时间 / 联系人 / 用户 / 机器人，`outcome='error'` 的行降权并标注「本轮失败」，`silent` 标「未回复」。分页固定 50，上一页 / 下一页。

联系人筛选采用**左侧栏列表**而不是下拉框：项目 shell 本来就是侧栏制（QueueView / JobsView / ContactsView 一致），下拉会和侧栏重复同一功能，所以按现有 shell 走。

窄屏（≤560px）四列塞不进一屏，改为按行堆叠并给原文/回复补「用户」「机器人」标签，而不是让人横向拖动去找回复。

`web/dist/` 随本次一并更新。

#### 测试与异步任务

本地用例（`tests/` 不入 Git）：

- `tests/butler/test_knowledge_store.py` — 写入与 `request_id` 去重、跨 owner 同 ID 各自成立、空 ID 不去重、owner 退化四种情形、prune 边界（恰好到期保留）、分页与筛选、`limit` 上限截断、`%` 当字面量。
- `tests/dashboard/test_knowledge_view.py` — 库不存在时 `available=false` 且**不创建文件**、空文件无表按空态、不返回 `owner`/`request_id`、筛选分页、损坏文件抛 `RuntimeError`。
- `tests/butler/test_knowledge_capture.py` — 假 backend 正常一轮断言行数与 `outcome='ok'`、未知联系人落 `anon:dm:101`、后端抛错时写 `outcome='error'` 且异常照常上抛、写库自身抛异常时回复仍正常返回、`enabled=false` 时不落盘。

`web/scripts/smoke.mjs` 增加对话记录页断言：渲染行数、原文与回复可见、失败标注、分页总数、按联系人筛选。不使用真实微信、不读写真实剪贴板。

**没有异步任务**：`knowledge-prune` 是人工触发的 CLI 子命令，不挂常驻线程，也不在 `serve()` 启动时跑。P0 数据量小，等 P4 的调度器接管。

#### 风险与回滚

- 体积与保留期：原文只增不减直到执行 `knowledge-prune`，默认保留 90 天。`retention_days` 上限锁在 3650，避免配置写错成天文数字。
- 隐私：`owner` 未确认身份时落 `anon:<channel_type>:<contact>`，不会把匿名发言挂到某个真人名下；群聊只记当前轮的用户原文，不记其他成员的上下文快照。只读页不返回 `owner`，界面上看不到内部身份键。
- 写入链路：`_record_episode` 全部异常吞掉并只记一行日志，所以知识库故障不会拖垮回复；用例显式覆盖了"写库抛异常时回复照常返回"。
- 检索：`q` 走 LIKE 全表扫，P0 量级可接受；量级上来后需要换 FTS，属于 P1 的事。
- 回滚：删掉两个 dashboard 新文件与 web 页面、恢复 `routes.py` / `server.py` / `router.js` / `App.vue`，并把 `core.py` 的三处调用与 `_record_episode` 去掉即可。库文件独立，回滚不需要动 `business.sqlite3`；不删库就只是留下一个不再被读的表。
<!-- end-migrated-part: doc-697690fcf2df43 -->

<a id="doc-97b2533a5ffcf7"></a>

### 迁移改动后复核知识库词条来源

来源：`llm wiki/wxbot/raw/changes/2026-11-01-knowledge-migrate-source-recheck.md:1`。

```yaml
type: change
title: 迁移改动后复核知识库词条来源
pages:
- apis/dashboard-knowledge
- symbols/knowledge-extract
```
### 迁移改动后复核知识库词条来源

#### 目标与背景

上一条记录 [raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4) 在 `src/butler/runtime/knowledge_store.py` 的迁移段插入了 `_checkpoint_legacy`，文件 sha 变化，凡把该文件列为来源的词条都被标成 `source-drift`。本条记录专门收掉这两个词条的复核：确认它们的行号没有被推移，内容也不需要改写。

#### 文件与代码位置

- `llm wiki/wxbot/apis/dashboard-knowledge.md`
- `llm wiki/wxbot/symbols/knowledge-extract.md`

两者的 `sources` 里指向 `knowledge_store.py` 的行号分别是 `:501`（`read`）、`:530`（`facts`）、`:568`（`sessions`）与 `:485`（`episodes_of`）。插入位置在 `:593`，全部落在这之前，锚点文本未变，`last_verified` 保持 `2026-11-01`。

#### 接口与字段

不适用：没有接口或字段变化。受影响的只是词条的来源指纹。

#### 数据库与迁移

不适用：本次不改迁移逻辑，只补复核记录。迁移本身的修复见 [raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint](knowledge-vault.md#doc-06dbdfdc7302a4)。

#### 前端消费点

不适用：`FactsView.vue` / `KnowledgeView.vue` 读的仍是 `KnowledgeStore.read` 与 `.facts`，行为不变。

#### 测试与异步任务

不适用：没有新增测试。改动前的验证是 `pytest tests/butler` 全绿，见上一条记录。

#### 风险与回滚

风险：无。本条只追加 changes 条目，未改词条正文、未改代码。

回滚：删掉两个词条 `changes` 里的本记录条目即可。
<!-- end-migrated-part: doc-97b2533a5ffcf7 -->

<a id="doc-06dbdfdc7302a4"></a>

### 知识库迁移改名留底前先合并 WAL

来源：`llm wiki/wxbot/raw/changes/2026-11-01-knowledge-migrate-wal-checkpoint.md:1`。

```yaml
type: change
title: 知识库迁移改名留底前先合并 WAL
pages:
- tables/knowledge-vault
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
```
### 知识库迁移改名留底前先合并 WAL

#### 目标与背景

在真实数据上执行 `python -m butler knowledge-migrate` 后核对留底文件，发现 `episodes.sqlite3.migrated` 单独只有 2 条、`facts.sqlite3.migrated` 连 `kb_facts` 表都读不出来，而 vault 里是完整的 5 条原文 + 1 条事实。原因是旧库处于 WAL 模式：`_import_sqlite` 用 `mode=ro` 只读 URI 打开，读得到 WAL 里的行却永远不会 checkpoint 回主库；`migrate_legacy` 接着直接 `Path.replace()` 改名，`-wal` 与 `-shm` 的名字还停在旧文件名上，SQLite 不再认这对边车，留底库就成了空壳。回滚会丢掉 7 条里的 4 条。

本次改动让改名前先合并 WAL，并把真实数据目录里已经失配的边车补回去。

#### 文件与代码位置

`src/butler/runtime/knowledge_store.py`

- 新增 `_checkpoint_legacy(path)`（`:593`）：用读写连接执行 `PRAGMA wal_checkpoint(TRUNCATE)`，再删掉残留的 `-wal` / `-shm`。读写连接才会把 WAL 页写回主库；只读连接只能读。
- `migrate_legacy`（`:660`）在四处 `.replace(...)` 改名之前各插一次调用：`knowledge.sqlite3`、`p-*/episodes.sqlite3`、`p-*/facts.sqlite3`、`index.sqlite3`。

`tests/butler/test_knowledge_store.py`

- 新增 `test_migrated_backup_keeps_rows_from_an_open_wal`：在写连接仍打开时复制主库与 `-wal`（模拟进程被强杀、WAL 未合并），跑 `migrate_legacy` 后断言留底库能独立打开且仍是 3 条，同时断言没有残留 `-wal` / `-shm`。

#### 接口与字段

不适用：只改迁移内部实现，`migrate_legacy(data_dir, log=None) -> int` 的签名与返回值不变，`KnowledgeStore` 的方法集不变。

#### 数据库与迁移

留底文件的语义被修正：`*.sqlite3.migrated` 从「改名后的主库文件」变成「已合并 WAL 的完整库」。在此之前，任何 WAL 模式旧库的留底都是不完整的——`knowledge.sqlite3`、`p-*/episodes.sqlite3`、`p-*/facts.sqlite3`、`index.sqlite3` 四类都受影响。

已在真实 `data/knowledge` 上就地修复：把三个 `.migrated` 临时改回原名与边车配对，checkpoint 后再改名，复验 `episodes.sqlite3.migrated` = 5 条、`facts.sqlite3.migrated` = 1 条，`-wal` / `-shm` 全部清除。

#### 前端消费点

不适用：vault 内容与 `index.json` 未变，管理台的知识库页读到的仍是 5 条原文与 2 条事实。

#### 测试与异步任务

`pytest tests/butler` 全绿，含新增用例。新增用例的有效性用一次性脚本验证过：把 `_checkpoint_legacy` 替换成空函数后，留底库直接抛 `no such table: kb_episodes`——说明它确实能抓住这个缺陷，而不是恒真断言。

不涉及异步任务：迁移只能由人工在停服状态触发（`python -m butler knowledge-migrate`），常驻线程不调用它。

#### 风险与回滚

风险一：`PRAGMA wal_checkpoint(TRUNCATE)` 在仍有其它连接持锁时会失败。代码捕获 `sqlite3.DatabaseError` 后继续改名，此时留底仍可能不完整——但这个前提已被「迁移必须在停服状态跑」覆盖。

风险二：`-wal` / `-shm` 的删除在 Windows 上可能因文件锁失败，代码吞掉 `OSError`。留下的边车只是垃圾文件，不影响已合并的主库，但下次迁移会再扫一遍。

风险三：真实数据目录的修复是「改名 → checkpoint → 改名」，中途中断会让文件名字停在中间态。数据本身不丢（vault 已完整、主库与 WAL 都在），重跑一次即可收敛。

回滚：`_checkpoint_legacy` 是纯增量，删掉它的调用即回到旧行为（留底可能不完整，但 vault 不受影响）。已修好的留底库不需要回滚。
<!-- end-migrated-part: doc-06dbdfdc7302a4 -->

<a id="doc-ba214c308af8ff"></a>

### 会话维度：左栏按人、右栏按私聊/群聊再筛

来源：`llm wiki/wxbot/raw/changes/2026-11-01-knowledge-sessions.md:1`。

```yaml
type: change
title: 会话维度：左栏按人、右栏按私聊/群聊再筛
pages: [apis/dashboard-knowledge, tables/kb-episodes, tables/kb-facts, tables/kb-owners,
  symbols/knowledge-extract, modules/web]
```
### 会话维度：左栏按人、右栏按私聊/群聊再筛

#### 目标与背景

管理台选中「101」以后，右栏同时列出这个人的私聊与群聊原文，而左栏只有一行「101」，既看不出这个人在几个会话里说过话，也无法只看其中一个会话。原因是左栏一行代表一个 `owner`（人），而 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20) 里一个 `owner` 可以对应多个 `(contact, channel_type)`。

本批不推翻「一人一库」：左栏仍按人一行，把会话维度补成左栏副标题的说明加右栏的二次筛选。

#### 文件与代码位置

- `src/butler/runtime/knowledge_store.py`
  - `_filters`（`:107`）新增 `contact` / `channel_type` 两个可选精确匹配条件。
  - `read_episodes`（`:150`）把这两个条件透传给 `_filters`；签名从 5 参变 7 参，默认值保持向后兼容。
- `src/dashboard/knowledge_view.py`
  - 新增 `_sessions`（`:85`）、`owners(kind)`（`:103`）、`_episode_sessions`（`:186`）、`_fact_sessions`（`:194`）。
  - `read`（`:116`）加 `contact` / `channel_type`，`facts`（`:152`）加 `contact`。
  - `_fact_where`（`:207`）/ `_count_facts`（`:218`）/ `_read_facts`（`:223`）新增 `contact` 条件。
- `src/dashboard/api/knowledge.py`
  - 新增 `_session(ctx)`（`:16`）：`channel_type` 只认 `dm` / `group`，其余当没填。
  - `read`（`:25`）与 `facts`（`:36`）改成经 `_session` 取参数。
- `web/src/views/KnowledgeView.vue`、`web/src/views/FactsView.vue`
  - 新增 `session` 状态、`sessions` / `activeSession` 计算属性与 `keyOf` / `sessionText` / `sessionSummary` / `selectSession`。
  - 左栏副标题改成会话摘要；右栏标题下新增会话 chips（`KnowledgeView.vue:154`、`FactsView.vue:162`），仅当这个人有多个会话时出现。
- `web/src/styles/knowledge.css`：新增 `.session-bar` 一节，只用既有令牌（`--bg2` / `--bg3` / `--line` / `--line-2` / `--wx` / `--fg` / `--fg2` / `--fg3`）。

#### 接口与字段

两条 GET 各加两个可选查询参数，响应外层结构不变：

| 参数 | 取值 | 语义 |
|---|---|---|
| contact | 任意字符串 | 精确匹配 `kb_episodes.contact` / `kb_facts.contact`；空表示不缩 |
| channel_type | `dm` / `group` | 与 `contact` 组合定位一个会话；**只对原文生效**，事实表没有这一列 |

[apis/dashboard-knowledge](knowledge-vault.md#doc-17461d21600be6) 的 `owners[]` 每项新增 `sessions: [{contact, channel_type, count}]`，按 `count` 倒序。原文页的 `channel_type` 取自 `kb_episodes`；事实页恒为空串，因为 [tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e) 不记会话类型——页面不假装能分。

`owners` 依旧恒为全量：会话筛选只缩 `rows` 与 `total`，不把人从左栏拿走。

#### 数据库与迁移

不涉及。没有新增表、列或索引；`contact` 与 `channel_type` 都是 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20) 的既有列，[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e) 只用到既有的 `contact`。索引库 [tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb) 不参与本批改动。

#### 前端消费点

- 左栏副标题由「群聊，N 条原文」改成「私聊 101、群聊 鸭王集训营，N 条原文，0 条事实」，超过两个会话折成「等 N 个会话」。
- 右栏的会话 chips 与顶部计数 chips 同样式，用 `aria-pressed` 表达选中态，`:focus-visible` 用既有强调色内描边。
- 换人时清空会话筛选，避免把上一个人的会话条件带到下一个人。

#### 测试与异步任务

- `tests/dashboard/test_knowledge_view.py` 新增 `test_sessions_list_every_conversation_of_one_person`、`test_session_filter_narrows_rows_within_one_person`，并在事实用例与 HTTP 用例里补 `contact` / `channel_type` 断言（含非法 `channel_type` 回落成不筛）。该文件用例数由 9 增至 12。
- 未新增异步任务：筛选全部在请求内同步完成。

#### 风险与回滚

- 左栏现在要为每个 owner 多开一次 `episodes.sqlite3` / `facts.sqlite3` 只读连接来取会话清单，联系人规模大时是 O(人数) 次文件打开；库文件缺失时按空数组短路，不建文件。
- 事实页的 `channel_type` 恒为空，同名的私聊与群聊在事实页分不开。这是数据模型限制，不是实现漏项。
- 回滚只需撤掉前端 chips 与 `_sessions` 调用；`_filters` 的新参数有默认值，单独保留不改变既有行为。
<!-- end-migrated-part: doc-ba214c308af8ff -->

<a id="doc-c0bff474452694"></a>

### 知识库拆分为一人一库并新增提炼事实库

来源：`llm wiki/wxbot/raw/changes/2026-11-01-knowledge-sharding.md:1`。

```yaml
type: change
title: 知识库拆分为一人一库并新增提炼事实库
pages: [tables/kb-episodes, tables/kb-facts, tables/kb-owners, apis/dashboard-knowledge,
  apis/butler-handle, apis/dashboard-queue, apis/dashboard-workflow,
  concepts/message-pipeline, concepts/model-error-contract,
  symbols/knowledge-extract, symbols/butler-handle, symbols/butler-result,
  modules/butler, modules/dashboard, modules/web, modules/runtime]
```
### 知识库拆分为一人一库并新增提炼事实库

#### 目标与背景

上一批（[raw/changes/2026-11-01-knowledge-episodes](knowledge-vault.md#doc-697690fcf2df43)）把 L1 原文放进单库 `data/knowledge.sqlite3`。这带来两个问题：任何一个人的数据损坏、被导出或整体清空都会牵连所有人；而原文按保留期过期，正好会把「从原文提炼出来的长期事实」一起删掉。

所以本次做三件事：

1. **一人一库**：`data/knowledge/index.sqlite3` 只当目录，每个 owner 一个 `p-<slug>/` 目录，目录下原文与事实各一个库。
2. **新增 L2 事实层**：`kb_facts` 存从原文提炼出的画像、偏好、关系、约定与长期话题，不随原文过期。
3. **只读投影与管理台按新结构重做**，并新增「知识库」一页。

**边界同样重要**：仍然不改对话 prompt、不改记忆注入、不挂常驻线程。提炼是人工触发的 CLI；既有的 `business.sqlite3` 里 `memory` 表（模型在对话中主动调工具写的 L2）完全没有动。两套事实各走各的入口，本批不合并。

#### 文件与代码位置

- `src/butler/runtime/knowledge_store.py` — 全量重写（159 行 → 478 行）。
  - `:32` `EPISODES_SCHEMA`、`:49` `FACTS_SCHEMA`、`:70` `INDEX_SCHEMA` 三套建表脚本。
  - `:95` `owner_slug`，`:118` `_connect`，`:135` `_ensure_column`，`:144` `read_episodes`（现在只查单个库，不再带 owner 过滤参数以外的跨库语义）。
  - `:157` `KnowledgeStore`：`:181` `_open`（按 kind+owner 缓存连接）、`:218` `_touch_owner`、`:262` `extracted_upto` / `:270` `set_extracted_upto`、`:276` `record`、`:303` `add_fact`、`:332` `prune`、`:347` `_rebuild_counts`、`:373` `read`、`:400` `facts`、`:430` `episodes_of`。
  - `:441` `migrate_legacy(data_dir)` 模块级函数。
- `src/butler/runtime/knowledge_extract.py` — 新文件（139 行）：`:19` `PROMPT`、`:44` `parse_facts`、`:78` `render`、`:88` `extract`、`:120` `extract_all`。
- `src/butler/agent/core.py:114` — `Butler.__init__` 里库根从 `data/knowledge.sqlite3` 改成 `data/knowledge`（目录）。
- `src/butler/__main__.py:53` — `knowledge-prune` / `knowledge-migrate` 共用分支，`:66` 新增 `knowledge-extract` 分支；`:15` 命令白名单、`:22` 附近的 `--owner/--batch/--dry-run` 参数。
- `src/dashboard/knowledge_view.py` — 全量重写（39 行 → 175 行）：`:23` `_ro`、`:33` `KnowledgeView`、`:44` `_owners_from_index`、`:59` `_owners_from_disk`、`:85` `read`、`:119` `facts`。
- `src/dashboard/api/knowledge.py` — `:10` `_view`、`:16` `read`、`:25` `facts`。
- `src/dashboard/routes.py:17`（`BUSINESS_GET`）、`:43`/`:44`（两条 GET 路由）。
- `web/src/views/KnowledgeView.vue` — 左栏由 `contacts: string[]` 改为 `owners: object[]`，筛选参数 `contact` → `owner`。
- `web/src/views/FactsView.vue` — 新页面（168 行）。
- `web/src/router.js:8`、`web/src/App.vue:8`/`:18`/`:45`/`:70` — 注册「知识库」页、远端模式隐藏、搜索框占位符。
- `web/src/styles/knowledge.css` — 两页共用；补 `.fact-table` 与右栏焦点环。
- `web/scripts/smoke.mjs` — `/api/knowledge` 假数据改 `owners` 结构，新增 `/api/knowledge/facts`，导航断言 7 → 8。
- `tests/conftest.py:138` — `make_home` 造 `Config` 时补 `data_dir=str(root/'data')`。

**明确不写入的位置**：`business.sqlite3` 的 `memory` 表、`user_memory_variants`、`user_profiles.memory_version` 一律不动；`_handle_request` 的落库调用点与异常包装维持原样（只是 store 内部换了路径）。

**图谱伴生更新**：`core.py` 与 `routes.py` 本批只做了同行替换（库根路径字符串、新增两条路由），但 `source-drift` 按整文件 digest 比对，所以引用了这两个文件的 7 个词条一并复核并追加本记录：[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)。复核结论：锚点行号全部未漂移（`core.py` 的 `:65` / `:70` / `:210` / `:252` / `:266` / `:301` / `:317`，`routes.py` 的 `:39` / `:42`），正文只补了路径与端点数量，原有契约结论不变。

#### 接口与字段

`GET /api/knowledge` 与新增的 `GET /api/knowledge/facts` 对称：

- 参数由 `contact` 改为 `owner`（精确匹配身份稳定键）；`owner` 非法值只会在内存里筛出空集，不进 SQL。
- 响应里 `contacts[]` 换成 `owners[]`，每项 `{owner, name, contact, channel_type, episodes, facts, last_at}`，供左栏列出可筛选的人。
- 事实行字段：`owner` / `contact` / `kind` / `fact_key` / `fact_value` / `quote` / `episode_at` / `confidence` / `source` / `created`。`fingerprint` 与 `id` 都不对外返回：前者是内部去重键，后者只用于同一秒内的稳定排序。
- `read` 的行集合与上一批一致，仍是 `at` / `contact` / `channel_type` / `user_text` / `reply_text` / `outcome`；`owner` 仍不外露。

**库不存在仍是空态**：`available: false` 加空数组，只读侧绝不建目录建表。索引库缺失或损坏时退回扫 `p-*/episodes.sqlite3`，从库内 `distinct owner` 反推目录。

#### 数据库与迁移

```
data/knowledge/
  index.sqlite3            kb_owners：目录名、展示名、条数、时间范围、提炼游标
  p-<slug>/
    episodes.sqlite3       kb_episodes（L1 原文，按 retention_days 过期）
    facts.sqlite3          kb_facts（L2 事实，长期有效）
```

`slug = 'p-' + sha1(owner)[:16]`：`owner` 形如 `user:<uuid>` / `anon:group:产品群`，带冒号和中文，不能直接当目录名；反查由索引库负责。

索引变化：`kb_episodes_at` 改为 `(at DESC, id DESC)`（分页直接吃索引）；部分唯一索引从 `(owner, request_id)` 收紧成 `(request_id)`——每个库已经只装一个人，owner 维度冗余了。`kb_episodes_owner_at` 删除，同理。

`kb_facts` 的唯一索引建在 `fingerprint = sha1(kind|fact_key|fact_value)` 上而不是 `fact_key` 上：同一件事的同一说法只留一条，措辞不同的矛盾陈述各留一条，不互相覆盖。

扩展方式：`extracted_upto` 用 `_ensure_column` 补（`CREATE TABLE IF NOT EXISTS` 已存在时不会改结构），老索引库打开即补列。

迁移：`python -m butler knowledge-migrate` 把旧的 `data/knowledge.sqlite3` 逐条 `record` 进新结构，成功后原名改 `data/knowledge.legacy.sqlite3` 留底并清掉 `-wal/-shm`。只处理一次；旧库不存在直接返回 0，不建任何东西。

#### 前端消费点

`KnowledgeView.vue` 与新的 `FactsView.vue` 共用 `knowledge.css`：左栏 `.user` 列表、右栏表格、固定 50 条分页。

`FactsView.vue` 六列：时间 / 联系人 / 类型 / 事实 / 原话 / 置信。`kind` 映射成「身份背景 / 偏好习惯 / 关系 / 约定事件 / 关注话题」，置信度显示成百分比，低于 50% 的行降权并在页脚计数。左栏条文案是「群聊，N 条原文，M 条事实」（逗号分隔，不用中点串）。

左栏项带 `tabindex="0"` + `role="button"` + 回车/空格键处理，`:focus-visible` 用既有强调色画内焦点环——键盘也要能选人。

两页都只在 `available=false` 时显示空态与「事实由 `python -m butler knowledge-extract` 整理」的说明，**页面上没有触发按钮**：提炼要跑模型几十秒，不能挂在 HTTP 请求里。

#### 测试与异步任务

- `tests/butler/test_knowledge_store.py`（14 项）：分库落盘位置、`owner_slug` 稳定、prune 只删原文不删事实、跨库按时间归并、`add_fact` 指纹去重与矛盾陈述并存、`migrate_legacy` 拆分与留底。
- `tests/dashboard/test_knowledge_view.py`（9 项）：空态不建目录、空文件按空态、跨库分页、索引缺失降级扫目录、坏库抛 `RuntimeError`、`facts` 独立读、相对 `data_dir` 仍能 `mode=ro` 打开、两条 HTTP 路由的 200 与远端模式 503。
- `tests/butler/test_knowledge_capture.py`（6 项）：新增「两个联系人落在两个库」。
- `tests/butler/test_knowledge_extract.py`（9 项）：解析容错（围栏、坏项、非 JSON）、游标只在成功后前移、空数组算成功、重复提炼幂等、dry-run 不写库不前移、单人失败不中断整批、owner 过滤。
- `web/scripts/smoke.mjs`：8 个导航标签、两个页面的行数与关键文案。

**没有异步任务**：`knowledge-prune` / `knowledge-migrate` / `knowledge-extract` 都是人工触发的 CLI 子命令，不在 `serve()` 里挂线程。

顺带修掉一处测试污染：`tests/conftest.py` 的 `make_home` 原来没传 `data_dir`，`Config` 默认值是 `'data'`，于是每个调 `butler.handle()` 的用例都把假对话写进仓库真实的 `data/knowledge/`。补上临时目录后，全量 pytest 跑完真实库零新增。

#### 风险与回滚

- 目录数量：N 个联系人 = N 个目录 + 3 个库文件，量大时 `read()` 要遍历所有库再归并。每库各自 `LIMIT offset+limit` 后归并切片，正确但不是最优；量级上来需要索引库兜住分页。
- 索引库是单点：丢了不影响数据，但会退化成扫目录（事实条数显示为 0，因为事实库不在降级路径里反查）。
- 事实层没有写权限收口：`add_fact` 由提炼 CLI 调用，管理台只有只读路由，目前不存在从 HTTP 侧写入的可能。
- 隐私：`owner` 仍未确认身份时落 `anon:<channel_type>:<contact>`；事实行带 `quote`（用户原话片段），与原文同源同级，不外泄给未授权方。
- 回滚：删掉 `knowledge_extract.py` 与 `FactsView.vue`，把 `knowledge_store.py` 恢复成单库版本、`core.py:114` 路径改回 `data/knowledge.sqlite3`，管理台与前端去掉 facts 相关改动即可。旧库没有删除，`knowledge.legacy.sqlite3` 可直接改名回滚。
<!-- end-migrated-part: doc-c0bff474452694 -->

<a id="doc-3f269e1ad8b05e"></a>

### 知识库 vault 词条与实现对齐

来源：`llm wiki/wxbot/raw/changes/2026-11-01-knowledge-vault-alignment.md:1`。

```yaml
type: change
title: 知识库 vault 词条与实现对齐
pages:
- tables/knowledge-vault
```
### 知识库 vault 词条与实现对齐

#### 目标与背景

[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 首次入库后，用真实历史数据跑了一遍 `migrate_legacy` 演练，发现词条复述了 `knowledge_store.py` 模块 docstring 的两处**设想**，与实现行为不符：

1. docstring 说「事实可以双链溯源到当天日记」，但 `_fact_line`（`knowledge_store.py:128`）只把 `links` 里的实体名写成双链，**从不生成指向日记文件的双链**。溯源靠事实行尾注释的 `at` 与 `quote`。
2. docstring 说「事实要能点回原话才有说服力」，同样暗示了并不存在的链接关系；实际能力是「注释里保留原话片段 `quote` + 时间戳」，不是可点击的链接。

这两句会误导后来者以为 graph view 里能看到「事实指向对话」的边，实际日记文件是孤立节点。词条以代码为准，不照抄 docstring。

第三处是 `_safe()` 的描述不精确：实现是**替换成 `-`**（`re.sub`），不是「去掉」。

#### 文件与代码位置

- `src/butler/runtime/knowledge_store.py:11` — docstring 里的错误表述「事实可以双链溯源到当天日记」，本次**不改代码**，只在词条里标注它属于早期设想。
- `src/butler/runtime/knowledge_store.py:19` — docstring 里的「事实要能点回原话才有说服力」。
- `src/butler/runtime/knowledge_store.py:128` — `_fact_line`，双链只来自 `links` 参数。
- `src/butler/runtime/knowledge_store.py:69` — `_safe`，`re.sub(r'[\x00-\x1f<>:"/\\|?*#^\[\]]', '-', ...)`。
- `llm wiki/wxbot/tables/knowledge-vault.md` — 三处表述修正。

#### 接口与字段

不适用：本次只改词条，不涉及任何 HTTP 接口、DTO 或工具 schema。

#### 数据库与迁移

不适用：不涉及 schema 与迁移脚本改动。本次改动来自一次**在副本上执行的迁移演练**（把 `data/knowledge` 与 `data/business.sqlite3` 复制到临时目录后跑 `migrate_legacy`），真实数据未被触碰。

演练结果作为事实依据：5 条原文 + 1 条事实 + 1 条 `memory` 记录迁入 vault，产出 `p-*/vault/人物/101.md`、`p-*/vault/对话/2026-11-01.md` 与 `index.json`；旧库改名为 `*.migrated`。

#### 前端消费点

不适用：词条改动不影响 `KnowledgeView.vue` / `FactsView.vue`。

#### 测试与异步任务

不适用：无代码改动，无新增用例。演练脚本是一次性命令，未入库。图谱校验为 `wiki.py lint`。

#### 风险与回滚

风险：无运行时风险，纯文档订正。

遗留：`knowledge_store.py` 的 docstring 仍保留两处与实现不符的说法。本次按「代码是事实源、词条是导航」的原则在词条里显式标注差异，没有修改源码注释——改注释属于代码改动，需要单独一次变更与测试，不在文档收口范围内。

回滚：删除本条记录并把 `tables/knowledge-vault` 的三处表述改回即可；但那样会重新引入误导，不建议。

[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)
<!-- end-migrated-part: doc-3f269e1ad8b05e -->

<a id="doc-13c52ea2bba75a"></a>

### 用户知识库改为一人一个 Obsidian vault 并删除 memory 链路

来源：`llm wiki/wxbot/raw/changes/2026-11-01-knowledge-vault-graph.md:1`。

```yaml
type: change
title: 用户知识库改为一人一个 Obsidian vault 并删除 memory 链路
pages:
- tables/knowledge-vault
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
- apis/dashboard-knowledge
- symbols/knowledge-extract
- symbols/knowledge-auto
- modules/butler
- modules/runtime
- modules/dashboard
- modules/identity
- modules/plugin
- modules/web
- modules/wiki
- modules/common
- modules/models
- apis/butler-handle
- apis/butler-handle-stream
- apis/dashboard-queue
- apis/dashboard-workflow
- symbols/butler-handle
- symbols/butler-result
- symbols/local-model-backend
- concepts/message-pipeline
- concepts/identity-authority
- concepts/group-identity-evidence
- concepts/model-error-contract
```
### 用户知识库改为一人一个 Obsidian vault 并删除 memory 链路

#### 目标与背景

用户要的是**知识图谱**：实体之间由索引互相关联，能用 Obsidian 打开、看到 graph view。旧实现是三张平表（`kb_episodes` / `kb_facts` / `kb_owners`），只能存字段，存不出拓扑——`kb_facts` 里连「这条事实说的是谁」都没有独立字段，关系更无从表达。

同时项目里存在第二套互不相通的「个人记忆」：`business.sqlite3` 的 `memory` 表 + `memory_get/set/search` 三个工具 + `butler-memory` 技能 + 管理台人物详情的记忆页签。两套存储对同一个用户各记一份，改一处不同步另一处。

本次把两者合并为一套：知识库改成**一人一个 vault**（实体是 Markdown，关系是正文里的双链），并彻底删除 memory 全链路。

#### 文件与代码位置

存储层（新增）：

- `src/butler/runtime/knowledge_store.py` — `KnowledgeStore` 全部重写：`owner_slug`（`:63`）、`_safe`（`:69`）、`_atomic_write`（`:93`）、事实行序列化 `_fact_line`（`:128`）与解析 `_parse_fact_line`（`:146`）、日记块 `_episode_block`（`:216`）、`record`（`:394`）、`add_fact`（`:415`）、`episodes_of`（`:485`）、`read`（`:501`）、`facts`（`:530`）、`sessions`（`:568`）、迁移 `_import_sqlite`（`:593`）/`_import_memory`（`:617`）/`migrate_legacy`（`:639`）。

提炼链路（改）：

- `src/butler/runtime/knowledge_extract.py` — `PROMPT`（`:24`）要求模型额外输出 `subject` / `subject_type` / `links`；`parse_facts`（`:72`）校验这三项；`_links`（`:55`）归一两种写法；游标从 `extracted_upto`（原文 id）换成 `extracted_at`（时刻），`extract`（`:120`）用 `last_at = max(row['at'])` 推进。
- `src/butler/runtime/knowledge_auto.py` — `_pending`（`:145`）改用 `episodes_of(after_at=store.extracted_at(...))` 算积压；`_prune`（`:238`）只删过期日记文件。

业务侧（改）：

- `src/butler/agent/core.py` — `_recall` 改为知识召回（走 `KnowledgeStore`），`_record_episode` 改为 `record` 写 vault。
- `src/butler/agent/tools.py` — 删除 `memory_get` / `memory_set` / `memory_search` 及其 schema；`TOOL_SCHEMAS` 只剩 8 项，`READ_TOOLS` 相应收缩。
- `src/butler/agent/catalogue.py` — `validate()` 从抛 `ValueError` 改为降级剔除（白名单里未安装的技能记日志后移除），因为 `butler-memory` 技能目录已删。
- `src/butler/business.py` — 删除 `memories` / `set_memory` 等读写方法。
- `src/butler/__main__.py` — `knowledge-migrate` 子命令接 `migrate_legacy`（`:57`）。
- `src/butler/server.py` — `GET` / `POST /v1/knowledge/extract`（`:141` / `:321`）。

插件（删）：

- `plugins/butler-wechat/skills/tools/butler-memory/SKILL.md` — 整目录删除。

管理台（改）：

- `src/dashboard/knowledge_view.py` — 只读投影重写为对 `KnowledgeStore` 的委托：`owners`（`:32`）、`read`（`:46`）、`facts`（`:60`）；`_ro` / `_sessions` / `_owners_from_index` / `_owners_from_disk` / `_episode_sessions` / `_fact_sessions` 全部删除。
- `src/dashboard/api/knowledge.py` — `_view`（`:10`）直接构造 `ctx.KnowledgeView(cfg.data_path() / 'knowledge')`。
- `src/dashboard/api/contacts.py`、`src/dashboard/api/support.py` — 删除 `/api/contacts/memory` 读写与合并预览里的记忆字段。
- `src/dashboard/flow_view.py` — 阶段名 `butler_memory` 改为 `butler_knowledge`，摘要字段 `memory_count` / `memory_conflicts` 改为 `fact_count`。
- `src/dashboard/routes.py` — 知识三条 GET + 一条 POST 保持原位（`:43`–`:45`、`:66`）。

前端（改/增）：

- 新增 `web/src/views/KnowledgeView.vue`（对话记录）、`web/src/views/FactsView.vue`（知识库）、`web/src/styles/knowledge.css`。
- `web/src/components/UserDialog.vue`、`ContactMergeDialog.vue`、`ContactsView.vue` — 删除记忆页签、记忆编辑弹窗与记忆字段。
- `web/src/components/WorkflowTrace.vue`、`web/src/flow.js` — 阶段标签改「知识召回」，`memory_count` 改 `fact_count`。
- `web/scripts/smoke.mjs` — 断言改为「个人记忆入口已下线」。

文档与工具：

- `README.md` — 知识库章节改为 vault 形态与 `knowledge-migrate` 步骤。
- `tools/probe_codex.py` — 探针里去掉 memory 工具。

#### 接口与字段

对外 HTTP 契约**形状不变**，只是数据源换了：

- `GET /api/knowledge` — 原文行 7 字段 `owner` / `at` / `contact` / `channel_type` / `user_text` / `reply_text` / `outcome`。`request_id` 不再外露。
- `GET /api/knowledge/facts` — 事实行 10 字段，`node`（事实所属实体节点）虽然由 `KnowledgeStore.facts` 算出，但投影层白名单未收录，**当前不返回**。
- `GET/POST /api/knowledge/extract` — 状态字段与 202/400/409/503 语义完全不变。
- `owners[]` 每项 `{owner, name, contact, channel_type, episodes, facts, last_at, sessions}` 不变。

被删除的接口：

- `GET /api/contacts/memory`、`POST /api/contacts/memory` — 连同 `memory_set` 动作一起下线。
- 合并预览响应里的 `memory_count` / `memory_conflicts` 字段删除，`rules` 文案改为「保留目标人物；群身份与窗口并入，窗口现有策略保持原行为。」。

工具接口：

- Agent 可见工具从 11 项降到 8 项，`memory_get` / `memory_set` / `memory_search` 不再存在；策略里的 `allowed_tools` 含这些名字时按未安装处理（`catalogue.validate` 降级剔除）。

#### 数据库与迁移

三张表全部退场，改由文件承担：

| 旧 | 新 |
|---|---|
| `data/knowledge/p-*/episodes.sqlite3`（`kb_episodes`） | `p-*/vault/对话/YYYY-MM-DD.md` |
| `data/knowledge/p-*/facts.sqlite3`（`kb_facts`） | `p-*/vault/{人物,组织,话题}/*.md` 的事实行 |
| `data/knowledge/index.sqlite3`（`kb_owners`） | `data/knowledge/index.json`（可重建缓存） |
| `business.sqlite3` 的 `memory` 表 | 迁移成 `kind=profile`、`source=memory-migration` 的节点事实 |

迁移入口 `python -m butler knowledge-migrate`（`migrate_legacy`，`knowledge_store.py:639`）。**必须在停服状态下手动执行一次**，否则旧库里的原文与事实不会出现在 vault 里。迁移幂等：`record` 靠 `rid` 判重、`add_fact` 靠 `fp` 判重。原文件搬完改名留底（`knowledge.legacy.sqlite3`、`episodes.sqlite3.migrated`、`facts.sqlite3.migrated`、`index.sqlite3.migrated`），不删除。

没有 schema 版本号：Markdown frontmatter 与 `index.json` 都允许未知键原样保留。

#### 前端消费点

- `web/src/views/KnowledgeView.vue` — 对话记录页，`apiGet('/api/knowledge?...')`（`:61`）。左栏人列表 + 会话 chips，右栏原文行。
- `web/src/views/FactsView.vue` — 知识库页，`apiGet('/api/knowledge/facts?...')`（`:98`）；自动提炼状态条 `loadExtract()`（`:111`）/ `runExtract()`（`:121`）调 `/api/knowledge/extract`。
- `web/src/router.js` — 两页路由与导航标签（「对话记录」「知识库」）。
- `web/src/components/ContactsView.vue` — 人物详情 `TABS` 去掉 `memory`，不再有记忆页签。
- `web/src/components/UserDialog.vue` — 删除记忆编辑表单与「记忆编辑」按钮。
- `web/src/components/ContactMergeDialog.vue` — 合并预览不再显示记忆条数/冲突。
- `web/src/components/WorkflowTrace.vue` + `web/src/flow.js` — 工作流阶段 `butler_knowledge` 显示为「知识召回」，摘要显示 `fact_count`。

#### 测试与异步任务

本地用例（`tests/` git-ignored）：

- `tests/butler/test_knowledge_store.py` — 双链生成、指纹去重、`prune` 不动节点事实、`index.json` 重建。
- `tests/butler/test_knowledge_extract.py` — 解析容错、游标前进/不前移、幂等、dry-run。
- `tests/butler/test_knowledge_auto.py` — 调度选人、退避、HTTP 状态与单次手动触发。
- `tests/dashboard/test_knowledge_view.py` — 只读投影、空态不建目录、会话筛选、四条路由与 503 门禁。
- `tests/unit/codex/test_codex_foundation.py` — 工具集换成 `reminder_*`，`catalogue.validate` 改为降级断言。
- `tests/unit/test_project_wiki.py` — 修正写死日期的用例。
- `web/scripts/smoke.mjs` — 9 个页面渲染断言，`npm run smoke` 通过。

异步任务：提炼仍在 Butler 进程内的后台线程（`ExtractScheduler`），间隔、批量、`min_backlog`、空闲让路、指数退避全部沿用；`prune` 仍由同一把跨进程锁串行化，只删日记文件，节点事实不参与过期。

#### 风险与回滚

风险：

1. **合并用户不搬 vault**：`merge_users` 只合并身份与窗口，源 vault 仍留在磁盘且 `index.json` 仍记着它，新人看不到被合并者的历史。有意为之——文件搬动不在 SQLite 事务内，回滚会造成不可恢复的丢失。
2. **没有事务**：同一节点的并发写会丢一条；当前只有 Butler 单进程写入。
3. **游标是时刻**：同一秒内晚到的原文可能被跳过。
4. **管理台查询是 O(全部文件)**：`q` 与 `owner` 都在内存过滤，一次请求遍历所有人整个 vault。
5. **必须手动迁移**：升级后忘了跑 `knowledge-migrate`，界面会显示「还没记录过」而不是报错，容易被误判成数据丢了。

回滚：

- 代码回滚到上一版本即可恢复旧的 SQLite 读写路径；迁移把源文件改名而非删除，`knowledge.legacy.sqlite3` / `episodes.sqlite3.migrated` / `facts.sqlite3.migrated` 可直接改回原名。
- vault 目录是新增产物，回滚后不会被旧代码读取，可以直接保留或手工归档。
- `business.sqlite3` 的 `memory` 表在迁移中**只读不删**，回滚后旧代码仍能读到自己那套记忆。

[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)
<!-- end-migrated-part: doc-13c52ea2bba75a -->

<a id="doc-a582ec7ef75fe6"></a>

### 知识图谱模板外部化为 Markdown 并支持管理台在线编辑

来源：`llm wiki/wxbot/raw/changes/2026-11-02-knowledge-graph-template.md:1`。

```yaml
type: change
title: 知识图谱模板外部化为 Markdown 并支持管理台在线编辑
pages:
- tables/knowledge-vault
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
- symbols/knowledge-template
- symbols/knowledge-extract
- apis/dashboard-knowledge
- apis/dashboard-queue
- apis/dashboard-workflow
- modules/runtime
- modules/dashboard
- modules/web
- modules/plugin
- modules/wiki
```
### 知识图谱模板外部化为 Markdown 并支持管理台在线编辑

#### 目标与背景

原来的节点目录、事实分类、索引分区和提炼规则全是代码常量：`knowledge_store.py` 的 `NODE_DIRS` / `FACT_KINDS` / `FACT_SECTIONS` / `INDEX_SECTIONS`，加上 `knowledge_extract.py` 的 `KINDS` 与整段 `PROMPT`。想给某个人多加一个「项目」目录，或让提炼多守一条规矩，只能改代码再重启 Butler。

本次把口径搬到一份 Markdown 模板：新建用户 vault 时按模板建骨架，提炼时按模板拼 prompt 与白名单；模板可在管理台「知识模板」页直接改。模板只决定「写到哪里、叫什么、按什么口径提炼」，事实行尾的机器可读注释仍是解析契约，不由模板配置。

#### 文件与代码位置

新增：

- `src/butler/runtime/knowledge_template.py` — `GraphTemplate`（`:83`）、`Kind` / `NodeType`、`parse_template`（`:296`，严格，抛带 `{line, message}` 的 `TemplateError`）、`resolve_template`（`:440`，覆盖层 → 插件内置 → 代码默认）、`load_template`（`:456`，宽松，坏模板只告警一次并回退）、mtime 缓存与 `DEFAULT_TEMPLATE`（`:154`）。
- `plugins/butler-wechat/knowledge/graph-template.md` — 随插件分发的内置模板：`## 节点目录`、`## 分类`、`## 提炼规则` 三张表/清单，frontmatter 控制 `episode_dir` / `index_file` / `index_title` / `index_limit` / `index_days`。
- `src/dashboard/knowledge_template_view.py` — `KnowledgeTemplateView`（`:27`）：`read`（`:42`）返回生效来源、内容、摘要与错误；`save`（`:108`）处理 `validate` / `save` / `reset`，复用 `common.config_lock`、版本比对、写前备份与原子替换。
- `src/dashboard/api/knowledge.py` — `_template_view`（`:16`）、`template_read`（`:64`）、`template_save`（`:73`）。
- 前端 `web/src/views/KnowledgeTemplateView.vue`：左栏摘要、全文编辑器、校验 / 保存 / 恢复内置与状态行。

改造：

- `src/butler/runtime/knowledge_store.py` — 构造参数新增 `template`（`:315`），默认从 `data/knowledge/template.md` 读；`episodes_dir`（`:334`）、`node_path`（`:337`）、`index_page_path`（`:340`）改由模板决定；`_ensure_vault`（`:436`）首次写入按模板建目录；`add_fact`（`:474`）的 kind 与节点类型按模板白名单降级；`rebuild_index`（`:543`）按模板分类顺序与实际目录分区；`FACT_KINDS` / `FACT_SECTIONS` / `INDEX_SECTIONS` / `NODE_DIRS` / `EPISODE_DIR` 保留为兼容默认值（`:50`–`:57`）。
- `src/butler/runtime/knowledge_extract.py` — `PROMPT` 拆成 `PROMPT_HEAD`（`:38`）+ `build_prompt(template, contact)`（`:54`）；`parse_facts(raw, kinds=None, node_types=None)`（`:84`）接受模板白名单；`_links(raw, types=NODE_TYPES)`（`:67`）只收模板声明的节点类型；`extract`（`:140`）从 `store.template` 取模板后再拼 prompt。
- `src/dashboard/knowledge_view.py` — 新增 `taxonomy()`（`:32`），`read` / `facts` 响应带 `kinds` 与 `node_types`。
- `src/dashboard/routes.py` — 新增 `GET /api/knowledge/template`（`:46`）与 `POST /api/knowledge/template`（`:68`），并把两条路径加入 `BUSINESS_GET`（`:18`）/ `BUSINESS_POST`（`:25`）。
- `src/dashboard/server.py` — 导入 `KnowledgeTemplateView`、`TemplateConflict`、`TemplateError`，供 `ctx.*` 使用。
- `web/src/views/FactsView.vue` — `LEGACY_KINDS`（`:11`）只作兜底；`kinds`（`:39`）改为 `computed` 读接口下发的分类；`kindOf`（`:210`）优先用接口标签。
- `web/src/router.js:9`、`web/src/App.vue:11` / `:22` / `:47` / `:67` — 注册「知识模板」页、组件映射、非本机模式隐藏与全局搜索隐藏。
- `web/scripts/smoke.mjs` — 增加模板接口 mock、9 个导航标签与模板页交互断言。
- `README.md` — 模块表、接口清单、知识库章节与管理台页面表补模板说明。

#### 接口与字段

新增两条：

- `GET /api/knowledge/template` → `{available, source, override, path, active_path, version, modified_at, content, summary, errors, limits}`。`source` 是 `override` / `plugin` / `builtin`；覆盖层坏了也返回原文与逐行错误，页面才能修。`version` 是覆盖层的 sha256，没有覆盖层时为空串。
- `POST /api/knowledge/template`，请求 `{action: validate|save|reset, content, version, acknowledge: true}`，动作头 `X-Wxbot-Knowledge-Action: 1`。`validate` 不落盘；`save` 版本不符回 409，内容不合法回 400 且带 `errors[{line, message}]`；`reset` 备份后删除覆盖层。非本机模式两条都 503。

`GET /api/knowledge/facts` 与 `GET /api/knowledge` 响应**只增字段**：`kinds[{key, label, section, hint}]`、`node_types[{key, label, description}]`。旧字段形状不变。前端不再维护第二份中文分类表，新增 kind 会直接出现在筛选与「类型」列。

#### 数据库与迁移

不涉及 SQL，也不改事实行格式：`<!-- fp|key|kind|conf|at|src|quote -->` 仍是 `FACT_LINE` 的解析契约。模板覆盖层放在 `data/knowledge/template.md`，在 vault 之外，不会被 `facts()` 的 `vault/*/*.md` 扫描。

已有 vault 不需要迁移：`_ensure_vault` 只补缺失目录；`add_fact` 写新节点时 `_atomic_write` 自建父目录，所以老库也能多出新目录。模板里被删掉的旧分类不会丢历史事实，读取时按节点正文原有小节展示；新写入的未知 kind 落 `topic`（或模板第一类），索引页归入「其他」。

模板约束：必须保留 `person` 节点类型与 `topic` 分类（分别是 `subject_type` / `kind` 的兜底）；目录名不得与 `episode_dir` 重名；kind ≤ 20、节点类型 ≤ 12、规则 ≤ 20；说明与规则合计 ≤ 2400 字；文件 ≤ 256 KB。内置 6 条安全规则不可删，模板规则只追加。

#### 前端消费点

- `KnowledgeTemplateView.vue` 的 `load()`（`:43`）调 `GET /api/knowledge/template`；`submit()`（`:72`）发 POST，错误按 `errors[{line, message}]` 拼成「第 N 行：…」；`save`（`:107`）/ `reset`（`:113`）各自先确认。没有修改时保存禁用；没有覆盖层时恢复禁用。
- `FactsView.vue` 的类型列与筛选改用接口下发的 `kinds`，`LEGACY_KINDS` 仅在接口缺字段时兜底。
- 外部接入模式下 `App.vue` 的 `hidden` 集合包含 `knowledge-template`，与知识库两页一起隐藏；本页也没有全局搜索框。

#### 测试与异步任务

新增 `tests/butler/test_knowledge_template.py`（10 项）：默认模板与旧七类一致、重复分类报行号、必须保留 person/topic、目录与对话目录重名被拒、覆盖层新增目录/分类/规则真的落到 vault 骨架与索引页、`episode_dir` / `index_file` 可配置、坏覆盖层回退且只告警一次、未知 kind/type 降级、prompt 与白名单来自模板、随包模板可加载。

新增 `tests/dashboard/test_knowledge_template_view.py`（10 项）：只读不建目录、保存返回新版本、版本冲突不改文件、校验不落盘、非法内容带行号、请求体不能指定写入路径、恢复内置保留备份、缺确认头/未知动作被拒、HTTP 模板 GET/POST 与 503 门禁、facts 携带模板分类。

本次相关的 5 个测试文件（上述两个加 `test_knowledge_store.py` / `test_knowledge_extract.py` / `test_knowledge_view.py`）共 65 项全部通过。`npm.cmd --prefix web run build` 与 `npm.cmd --prefix web run smoke` 通过；smoke 现在断言 9 个导航标签，并覆盖模板页的载入、dirty、保存请求与状态反馈。

Hallmark：`KnowledgeTemplateView.vue` 静态检查 0 FAIL；真实渲染 4 个视口 0 FAIL。剩余 1 REFLEX（既有导航壳 10px 文本）与 1 WARN（既有导航 h2 渐变对比）不在本次改动范围，未扩大清理。为满足输入框边缘 3:1，`theme.css` 新增 `--line-strong` 令牌。

异步任务不变：提炼仍在 Butler 进程内的 `ExtractScheduler` 后台线程，模板只影响下一轮拼 prompt 与写入位置，不新增线程或定时器。

#### 风险与回滚

风险一：模板写坏会让索引页或 prompt 异常。运行时宽松解析失败回退插件内置；页面保存前强制严格校验并给行号；内置 6 条规则不可删。

风险二：模板是提示词注入面。只用 `kind_choices()` / `type_choices()` 拼白名单字段，限长 2400 字；模板是安装者本地文件，不是外部输入。

风险三：改模板不改历史。旧分类/目录仍按原文件展示；新 kind 未知时落兜底；不重写任何已有节点，也不删除知识。

风险四：Windows 文件占用。保存走 `config_lock` + 临时文件 + `os.replace`，失败返回 503 并保留备份。

回滚：删除 `data/knowledge/template.md` 即恢复插件内置；代码回滚后模板文件被忽略，vault 不需要迁移。前端回滚时 `GET /api/knowledge/facts` 新增字段会被旧页面忽略。

[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)
[symbols/knowledge-template](knowledge-vault.md#doc-4656beba355895)
<!-- end-migrated-part: doc-a582ec7ef75fe6 -->

<a id="doc-dde024d7417249"></a>

### 修改记录

来源：`llm wiki/wxbot/raw/changes/2026-11-05-delete-knowledge-fact.md:1`。

```yaml
type: change
title: 知识库逐条删除事实
pages:
- apis/dashboard-knowledge
- tables/knowledge-vault
- modules/web
- modules/dashboard
- modules/butler
- symbols/knowledge-auto
- symbols/knowledge-extract
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
- apis/index-tts
- apis/dashboard-workflow
- apis/dashboard-voice-assets
- apis/dashboard-queue
- apis/butler-handle
- apis/butler-handle-stream
- symbols/butler-handle
- symbols/butler-result
- concepts/model-error-contract
- concepts/development-baseline
- modules/wiki
```
### 修改记录

#### 目标与背景

在知识库按条删除事实，保留对话原文和来源归属。原页面只有事实查询，不能清理个别错误或冗余事实。

#### 文件与代码位置

- `web/src/views/FactsView.vue:155` 确认、发送及刷新；`web/src/styles/knowledge.css` 提供危险操作按钮与焦点样式，`web/dist` 随源码重建。
- `src/dashboard/routes.py:80` 与 `src/dashboard/api/knowledge.py:56` 注册本机转发。`src/dashboard/knowledge_view.py` 暴露事实编号和实时事实数。
- `src/butler/server.py:335` 提供鉴权写端点；`src/butler/runtime/knowledge_store.py:516` 删除精确事实行，更新索引。`src/butler/__main__.py` 的手动清理复用同一把提炼锁。

#### 接口与字段

`GET /api/knowledge/facts` 返回 `fact_id`，由 owner、相对节点路径和事实行生成。`POST /api/knowledge/facts/delete` 要求同源和 `X-Wxbot-Knowledge-Action`，用服务 token 转发 `/v1/knowledge/facts/delete`。请求只收 `owner/fact_id/acknowledge`；成功返回 `ok/deleted/indexes_updated`，已变更或已删 404，更新占锁 409，输入错误 400。

#### 数据库与迁移

不涉及 DB 和迁移。节点内只原子替换目标事实行，原文、其他事实、节点文件、owner 及提炼游标保留。刷新目录事实数和 vault 中心索引。若派生索引写入失败，告知已删除且索引暂未更新，管理台统计仍按实际节点读取。

#### 前端消费点

逐条按钮明确显示确认内容、处理中、成功和错误；取消不会发写请求。沿用群筛选、个人筛选和分页，末页清空时回到最后一个有数据的页。

#### 测试与异步任务

临时库 49 项离线回归、前端 build 和 smoke、Hallmark 静态检查通过。覆盖同文多节点、重试、原文、游标、确认、占锁和索引失败。浏览器进程启动受限。不新增后台任务，提炼及定期清理与删除共享锁。

#### 风险与回滚

用户点击确认后按条永久删除，恢复依赖原有备份；游标不重置，但以后新消息仍可能提炼出类似事实。回滚源码和 dist 即移除入口，不能恢复已删除内容。详见 [impacts/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-2d4c142263c11b)。
<!-- end-migrated-part: doc-dde024d7417249 -->

<a id="doc-867b5eee05957a"></a>

### 修改记录

来源：`llm wiki/wxbot/raw/changes/2026-11-05-knowledge-group-sources.md:1`。

```yaml
type: change
title: 知识库按群汇总并标记来源
pages:
- apis/dashboard-knowledge
- modules/dashboard
- modules/web
- tables/knowledge-vault
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
- symbols/knowledge-extract
```
### 修改记录

#### 目标与背景

群成员原文和事实按 owner 留在各自 vault。知识库页面曾用群窗口名显示每个 owner，多个档案看起来相同。现按群窗口汇总并展示事实所属群与归档成员。

#### 文件与代码位置

- `src/dashboard/knowledge_view.py` 的 `_identity_names` 和 `_fact_groups` 建立只读来源与汇总，`facts` 计算筛选和展示字段。`src/dashboard/api/knowledge.py` 的 `facts` 传入群筛选与本地身份库路径。
- `src/butler/runtime/knowledge_store.py:671` 的 `facts` 在原全局时间排序与分页前允许限定 owner 集合。
- `web/src/views/FactsView.vue` 以群为可筛选项，事实表「来源」显示成员和群名。`web/src/styles/knowledge.css` 允许来源列折行，随源码重建 dist。

#### 接口与字段

现有 GET `/api/knowledge/facts` 增加可选精确 `group`，优先于 `contact` 并可与 `owner` 联合过滤。响应增加 `groups[{name,facts,episodes}]`、`owners[].group_only` 和可确定群归档的事实 `source_group/source_name`。保持原文接口及已有个人过滤的形态。

#### 数据库与迁移

不涉及迁移、写库、合并联系人或改写 Markdown。群原文计数和通道来自现有日记块，事实计数来自节点 contact。保留已无原文但目录标为群聊的归档来源。某 owner 的同名群和私聊均有原文时，旧事实缺少逐条通道，不把该 owner 的同名事实归进群筛选。成员来源取业务库的已确认群昵称、人物显示名或明确的未知标签。

#### 前端消费点

知识库左栏显示每群一项，纯群归档折入群条目，混合归档可继续用个人筛选。群筛选先于分页且保留搜索；选群时原全局提炼按钮标明「立即提炼全部」。对话记录页面继续使用原投影。

#### 测试与异步任务

临时库回归覆盖多 owner、匿名、同名私聊、分页及原记录保留，20 项离线测试通过。Vite build、smoke 与 Hallmark 静态检查通过；浏览器进程启动受限。不涉及提炼调度或新增异步任务。

#### 风险与回滚

历史事实仅有归档范围，来源标签描述归档归属，无法给所有旧事实补出原消息通道。回滚源码与 dist 即恢复旧列表；不改业务数据。详见 [impacts/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-53fb2c0d450b09)。
<!-- end-migrated-part: doc-867b5eee05957a -->
