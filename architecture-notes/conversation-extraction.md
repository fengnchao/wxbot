# 聊天记录提炼

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 聊天记录提炼

从对话记录中提炼可长期保留的事实，写入知识库。

## 技术资料

- [knowledge_auto](#doc-8d31785e6eb1e7) · `llm wiki/wxbot/symbols/knowledge-auto.md`
- [knowledge_extract](#doc-7d9303870f5774) · `llm wiki/wxbot/symbols/knowledge-extract.md`

<a id="doc-8d31785e6eb1e7"></a>

### knowledge_auto

来源：`llm wiki/wxbot/symbols/knowledge-auto.md:1`。

```yaml
type: symbol
module: runtime
summary: Butler 进程内的定时提炼调度器，一轮只喂模型一批，并与 CLI 共用跨进程单飞锁
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/runtime/knowledge_auto.py
  line: 29
  anchor: 'def acquire(path):'
- path: src/butler/runtime/knowledge_auto.py
  line: 71
  anchor: 'class ExtractScheduler:'
- path: src/butler/runtime/knowledge_auto.py
  line: 163
  anchor: 'def run_once(self, owner='''', batch=None, dry_run=False):'
- path: src/butler/runtime/knowledge_auto.py
  line: 258
  anchor: 'def _round(self):'
- path: src/butler/runtime/knowledge_auto.py
  line: 320
  anchor: 'def trigger(self, owner='''', batch=None, dry_run=False):'
- path: src/butler/server.py
  line: 520
  anchor: knowledge_extract = ExtractScheduler(butler, cfg, log=_log)
- path: src/butler/__main__.py
  line: 100
  anchor: lock=acquire(cfg.knowledge_extract_lock_path())
changes:
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
calls:
- symbols/knowledge-extract
called_by: []
```
### knowledge_auto

#### 签名与职责

```
acquire(path) -> str | None
release(handle) -> None
ExtractScheduler(butler, cfg, log=None)
  .status() -> dict
  .run_once(owner='', batch=None, dry_run=False) -> dict
  .trigger(owner='', batch=None, dry_run=False) -> (bool, str)
  .start() / .stop()
```

职责只有一句：决定**什么时候**把 [tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20) 里还没提炼的原文交给
[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)，以及把结果与下次时间记下来。

`_round`（`:258`）的判定顺序是硬契约：开关 → 到点 → 最近 `idle_seconds` 秒内没人说话 → 有积压 →
抢到跨进程锁。前四条任意一条不满足都只推迟（`deferred` / `no_backlog` / `skipped`），不累加失败；
只有模型调用与写库异常才记 `failures` 并按 `min(6h, retry_minutes * 2^(failures-1))` 退避（`:199`）。

`_pending`（`:145`）按 `KnowledgeStore.owners()` 的最近说话顺序取人，每人要求游标之后至少有
`min_backlog` 条原文；不指定 `owner` 时一轮最多 `max_owners` 人。

#### 所属模块

[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)。它不是 HTTP 处理器，也不在请求路径上：`serve()` 只负责构造、`start()` 与 `stop()`
（`src/butler/server.py:520`、`:487`、`:495`）。

放这里而不是 `agent/`：它不参与 prompt 编排，只调度 [symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)。

#### 调用方与反向引用

- `butler.server.serve()`：进程内唯一的生产调用方，随 serving 生命周期启停。
- `butler/__main__.py:74`：人工命令 `knowledge-extract` 先用同一把锁，抢不到直接报错退出，
  避免和定时轮同时喂同一批原文。
- 管理台经 `POST /v1/knowledge/extract` 走 `trigger()`，由后台线程执行，不阻塞 HTTP 响应。

#### 调用了谁

- `knowledge_extract.extract`（单个 owner 一批）与 `MAX_BATCH`
- `KnowledgeStore.owners` / `episodes_of` / `extracted_at`（时刻游标）/ `prune`
- `HermesClient.reset` / `chat`，固定 `session_kind='extract'`

`prune` 删完成天日记后会把每人的 `vault/index.md` 重画一遍（[tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 的 `rebuild_index`）。两件事共用一条线程：`start()` 要求 `auto_extract=true`，所以提炼关着时清理也不会跑；跑到一轮后是否顺便清理再由 `auto_prune` 决定（`_prune_due`，`:233`）。

#### 副作用（库/文件/事件/网络）

- 写 [tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e) 与 [tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb) 的游标，全部经 [symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774)。
- 写 `data/cache/knowledge_extract_state.json`（原子替换）、`knowledge_extract_audit.jsonl`（追加）、
  `knowledge_extract.lock`（O_EXCL 创建，退出时删除）。
- 调用模型：每轮最多 `batch` 条原文 × `max_owners` 人。
- 不写微信队列、不碰 UI、不发微信消息。

#### 契约、测试与风险

- 锁：`acquire`（`:29`）用 `O_CREAT|O_EXCL`，锁文件 mtime 超过 `LOCK_STALE_SECONDS`（1800 秒）视为上次进程
  崩溃并回收；内容只写 `pid 时间戳`，不含任何原文。
- 默认关：`start()` 在 `knowledge.enabled=false` 或 `knowledge.auto_extract=false` 时只记一条日志并返回，
  不创建线程（`tests/butler/test_knowledge_auto.py` 有对应用例）。
- `trigger()` 用 `threading.Lock.acquire(blocking=False)` 单飞，忙时返回 `(False, 'busy')`，
  HTTP 层映射成 409，不排队。
- `dry_run` 不留状态：空跑不写 `last_run_at` / `next_run_at`，避免污染下次计划时间。
- 审计只记事件名、人数、条数与异常类型，不写模型输出与原文。

`tests/butler/test_knowledge_auto.py`（9 项）覆盖：无积压不调模型、写入与游标、`min_backlog`、
失败退避不前移游标、CLI 持锁时跳过、`trigger` 忙、默认关、最近活动顺延、配置越界。

#### 代码依据与修改来源

- `src/butler/runtime/knowledge_auto.py:29` — `def acquire(path):`
- `src/butler/runtime/knowledge_auto.py:71` — `class ExtractScheduler:`
- `src/butler/runtime/knowledge_auto.py:163` — `def run_once(self, owner='', batch=None, dry_run=False):`
- `src/butler/runtime/knowledge_auto.py:258` — `def _round(self):`
- `src/butler/runtime/knowledge_auto.py:320` — `def trigger(self, owner='', batch=None, dry_run=False):`
- `src/butler/server.py:520` — `knowledge_extract = ExtractScheduler(butler, cfg, log=_log)`
- `src/butler/__main__.py:100` — `lock=acquire(cfg.knowledge_extract_lock_path())`

[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)

[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。

#### 本次核对

删除事实及手动清理复用调度器和提炼 CLI 的跨进程锁。删除保留游标，见 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd)。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

已对照当前共享源码复核本词条的接口或调用位置。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。
<!-- end-migrated-part: doc-8d31785e6eb1e7 -->

<a id="doc-7d9303870f5774"></a>

### knowledge_extract

来源：`llm wiki/wxbot/symbols/knowledge-extract.md:1`。

```yaml
type: symbol
module: runtime
summary: 从对话原文提炼知识图谱节点的链路，模板决定分类、节点类型与追加规则，CLI 与进程内调度器共用，游标只在整批成功后前移
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/runtime/knowledge_extract.py
  line: 25
  anchor: KINDS = LEGACY_KINDS
- path: src/butler/runtime/knowledge_extract.py
  line: 29
  anchor: CORE_RULES = (
- path: src/butler/runtime/knowledge_extract.py
  line: 38
  anchor: PROMPT_HEAD = """下面是一个人和助理的若干轮对话，每条前面有编号。当前用户的名字是「%s」。
- path: src/butler/runtime/knowledge_extract.py
  line: 54
  anchor: 'def build_prompt(template, contact):'
- path: src/butler/runtime/knowledge_extract.py
  line: 67
  anchor: 'def _links(raw, types=NODE_TYPES):'
- path: src/butler/runtime/knowledge_extract.py
  line: 84
  anchor: 'def parse_facts(raw, kinds=None, node_types=None):'
- path: src/butler/runtime/knowledge_extract.py
  line: 130
  anchor: 'def render(rows):'
- path: src/butler/runtime/knowledge_extract.py
  line: 140
  anchor: 'def extract(store, owner, contact, complete, *, batch=40, log=None, dry_run=False):'
- path: src/butler/runtime/knowledge_extract.py
  line: 175
  anchor: 'def extract_all(store, complete, *, batch=40, owner='''', log=None, dry_run=False):'
- path: src/butler/runtime/knowledge_store.py
  line: 677
  anchor: 'def episodes_of(self, owner, after_at=0.0, limit=200):'
- path: src/butler/__main__.py
  line: 92
  anchor: 'if args.command==''knowledge-extract'':'
- path: src/butler/runtime/knowledge_auto.py
  line: 182
  anchor: read, written, parsed = extract(
changes:
- raw/changes/2026-11-01-knowledge-sharding
- raw/changes/2026-11-01-knowledge-sessions
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-migrate-source-recheck
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-01-knowledge-atomic-retry
- raw/changes/2026-11-02-knowledge-graph-template
- raw/changes/2026-11-05-knowledge-group-sources
- raw/changes/2026-11-05-delete-knowledge-fact
- raw/changes/2026-11-05-resident-xiaochao
calls:
- symbols/knowledge-template
called_by:
- symbols/knowledge-auto
```
### knowledge_extract

#### 签名与职责

```
build_prompt(template, contact) -> str
parse_facts(raw, kinds=None, node_types=None) -> list[dict]
render(rows) -> str
extract(store, owner, contact, complete, *, batch=40, log=None, dry_run=False) -> (read, written, parsed)
extract_all(store, complete, *, batch=40, owner='', log=None, dry_run=False) -> list[dict]
```

职责只有一句：把 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 里**还没提炼过**的对话交给模型，把结果写成知识图谱的节点、事实行与 `[[双链]]`。

`complete` 是由调用方注入的回调（`prompt -> str`），本模块不认识 Hermes、Codex 或任何后端——CLI 传真实模型，测试传假实现。这是本模块能被用例覆盖而不联网的原因。

`parse_facts`（`:84`）从模型输出里取第一个 `[` 到最后一个 `]` 之间的 JSON：容忍代码围栏和前后废话，坏项（非对象、空 value）直接丢，`kind` 越界回落 `topic`，`subject_type` 越界回落 `person`，`confidence` 非数字回落 0.5 并夹在 0..1。白名单不再写死：`parse_facts(raw, template.kind_keys, template.node_type_keys)`（`:155`）由调用方传模板分类与节点类型；`KINDS`（`:25`）只是兼容默认值。`_links`（`:67`）允许 `"李四"` 与 `{"name":"李四","type":"person"}` 两种写法，最多收 `MAX_LINKS`（8）个，`type` 不在模板节点类型内时回落 `person`。

`build_prompt`（`:54`）用模板的 `kind_choices()` / `type_choices()` 填 `PROMPT_HEAD`（`:38`），再把 `CORE_RULES`（`:29`，6 条）与模板追加规则一起编号。内置规则永远在前，模板只能加不能减。

`render`（`:130`）把原文排成 `[id] 用户：…` / `助理：…` 两行一组。编号是给模型对 `quote` 用的，也方便人回看；编号来自 `episodes_of` 返回时补的序号，不是数据库自增 id。

**产出比 SQLite 时代多了三个字段**：`subject`（这条事实挂到哪个节点）、`subject_type`（`person` / `org` / `topic`）、`links`（正文里生成哪些双链）。前两个决定 `add_fact` 写哪个文件，第三个决定 graph view 连不连得上——没有它们写出来的只是一堆孤立事实行。

#### 所属模块

[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)。放在 `butler/runtime/` 而不是 `agent/`：它不参与对话，不接触 prompt 编排，也不在 `serve()` 的请求路径上。

#### 调用方与反向引用

三个入口，都只经过本模块这一条写路径：

- `python -m butler knowledge-extract`（`src/butler/__main__.py:92`）：人工跑一趟。CLI 构造临时 `Contact`（`uid='knowledge-extract'`）承载 profile，把 `hermes.chat(..., session_kind='extract')` 作为 `complete` 传进来；跑之前先 `acquire` 跨进程锁（`:74`），抢不到就报「自动提炼正在运行」并返回 1。
- [symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7) 的 `run_once`（`src/butler/runtime/knowledge_auto.py:182`）：常驻调度器逐个 owner 调 `extract`，`complete` 同样是 `hermes.chat(..., session_kind='extract')`，每轮 `reset` 一次会话。
- 管理台「立即提炼」不是第四个入口：`POST /v1/knowledge/extract` 交给调度器的 `trigger()` 在后台线程执行，HTTP 只拿 202。

HTTP 请求里**不直接跑提炼**：一轮要几十秒到几分钟，挂在请求上必然超时。

#### 调用了谁

- `KnowledgeStore.extracted_at` / `set_extracted_at`（`:511` / `:516`，时刻游标，不是行号游标）
- `KnowledgeStore.episodes_of`（`:626`，按 `at > 游标` 取一批新原文，上限 1000）
- `KnowledgeStore.add_fact`（`:474`，写节点事实行，靠指纹去重）
- `KnowledgeStore.owners`（`:430`，`extract_all` 遍历目录）
- `store.template`（[symbols/knowledge-template](knowledge-vault.md#doc-4656beba355895)）：分类、节点类型与追加规则都从这里取，不再读模块常量。

不调用模型 SDK、不读配置、不发网络请求。

#### 副作用（文件/事件/网络）

写 [tables/knowledge-vault](knowledge-vault.md#doc-dc9956670d38fd) 的实体节点 Markdown（每条事实一行，行尾注释带 `fp` / `key` / `kind` / `conf` / `at` / `src` / `quote`），并推进 `index.json` 里的 `extracted_at` 游标。

**不写对话日记**、不改 prompt、不写 `business.sqlite3`。`dry_run=True` 时两样都不写，只把结果打到日志。

#### 契约、测试与风险

游标契约：

- 整批成功才 `set_extracted_at(owner, last_at)`，`last_at` 是本批**最大的 `at` 时间戳**（`:152`），不是行数、不是 id。
- 模型输出里**完全没有方括号**→ 判为解析失败，游标不前移，下次重来（`:156`）。
- 输出里方括号存在但内容不是 JSON、或确实是 `[]` → 按「这批量没有值得记的内容」处理，游标照常前移，避免同一批反复烧模型。
- `dry_run` 不前移游标，否则会跳过一段没写进 vault 的对话。
- 游标是时刻而非位置，所以**同一秒内晚到的原文可能被跳过**；`record` 写入时间由 `at` 决定，正常的顺序写入没有这个问题。

`extract_all` 单人异常只记进 `report[owner]['error']`（异常类型名），继续下一个人。

本地用例 `tests/butler/test_knowledge_extract.py`：围栏与废话容错、坏项丢弃、写入与游标前进、重复提炼幂等（同一 `fp` 不写第二行）、无法解析时游标不动、空数组算成功、dry-run 不写库、单人失败不中断、`owner` 过滤。

风险：提炼质量完全取决于模型；`CORE_RULES` 里「不推测、不补全、助理的话不作事实来源」「矛盾陈述各写一条」是硬约束，改提示词等于改数据质量。模板能把分类/类型/追加规则改坏，但保存前有严格校验，运行时解析失败回退内置模板（[symbols/knowledge-template](knowledge-vault.md#doc-4656beba355895)）。批量上限 `batch` 夹在 1..200（`MAX_BATCH`），字段长度上限见 `MAX_VALUE`(500) / `MAX_KEY`(80) / `MAX_QUOTE`(300) / `MAX_LINKS`(8)。`subject` 清洗后会决定文件名，同名不同实体将合并进同一个节点——这是 `_safe()` 的已知边界。

#### 代码依据与修改来源

- `src/butler/runtime/knowledge_extract.py:25` — `KINDS = LEGACY_KINDS`
- `src/butler/runtime/knowledge_extract.py:29` — `CORE_RULES = (`（6 条不可删的安全规则）
- `src/butler/runtime/knowledge_extract.py:38` — `PROMPT_HEAD = """下面是一个人和助理的若干轮对话，每条前面有编号。当前用户的名字是「%s」。`
- `src/butler/runtime/knowledge_extract.py:54` — `def build_prompt(template, contact):`
- `src/butler/runtime/knowledge_extract.py:67` — `def _links(raw, types=NODE_TYPES):`
- `src/butler/runtime/knowledge_extract.py:84` — `def parse_facts(raw, kinds=None, node_types=None):`
- `src/butler/runtime/knowledge_extract.py:130` — `def render(rows):`
- `src/butler/runtime/knowledge_extract.py:140` — `def extract(store, owner, contact, complete, *, batch=40, log=None, dry_run=False):`
- `src/butler/runtime/knowledge_extract.py:175` — `def extract_all(store, complete, *, batch=40, owner='', log=None, dry_run=False):`
- `src/butler/runtime/knowledge_store.py:511` — `def extracted_at(self, owner):`
- `src/butler/runtime/knowledge_store.py:516` — `def set_extracted_at(self, owner, at):`
- `src/butler/runtime/knowledge_store.py:677` — `def episodes_of(self, owner, after_at=0.0, limit=200):`
- `src/butler/__main__.py:92` — `if args.command=='knowledge-extract':`
- `src/butler/runtime/knowledge_auto.py:182` — `read, written, parsed = extract(`

[raw/changes/2026-11-01-knowledge-sharding](knowledge-vault.md#doc-c0bff474452694)
[raw/changes/2026-11-01-knowledge-sessions](knowledge-vault.md#doc-ba214c308af8ff)
[raw/changes/2026-11-01-knowledge-auto](conversation-extraction.md#doc-4f707cfb04b69a)
[raw/changes/2026-11-01-knowledge-vault-graph](knowledge-vault.md#doc-13c52ea2bba75a)
[raw/changes/2026-11-01-knowledge-atlas-index](knowledge-vault.md#doc-69eb9deaf900e3)
[raw/changes/2026-11-01-knowledge-atomic-retry](knowledge-vault.md#doc-8614fbc4e2f39c)

#### 本次核对

群汇总与来源标记属于只读投影，提炼调用和游标保持原行为。 来源 [raw/changes/2026-11-05-knowledge-group-sources](knowledge-vault.md#doc-867b5eee05957a)。

#### 本次核对

单条事实删除沿用提炼跨进程锁，提炼规则与游标推进未改。 来源 [raw/changes/2026-11-05-delete-knowledge-fact](knowledge-vault.md#doc-dde024d7417249)。

#### 常驻角色接入核对

已对照当前共享源码复核本词条的接口或调用位置。 来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。
<!-- end-migrated-part: doc-7d9303870f5774 -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [自动提炼：进程内调度器、跨进程单飞与管理台状态](#doc-4f707cfb04b69a) · `llm wiki/wxbot/raw/changes/2026-11-01-knowledge-auto.md`

<a id="doc-4f707cfb04b69a"></a>

### 自动提炼：进程内调度器、跨进程单飞与管理台状态

来源：`llm wiki/wxbot/raw/changes/2026-11-01-knowledge-auto.md:1`。

```yaml
type: change
title: 自动提炼：进程内调度器、跨进程单飞与管理台状态
pages: [apis/butler-handle, apis/butler-handle-stream, apis/dashboard-knowledge, apis/dashboard-queue,
  apis/dashboard-workflow, concepts/model-error-contract, modules/butler, modules/dashboard,
  modules/models, modules/runtime, modules/web, modules/wiki, symbols/butler-handle,
  symbols/butler-result, symbols/knowledge-auto, symbols/knowledge-extract, tables/kb-episodes,
  tables/kb-facts, tables/kb-owners]
```
### 自动提炼：进程内调度器、跨进程单飞与管理台状态

#### 目标与背景

[symbols/knowledge-extract](conversation-extraction.md#doc-7d9303870f5774) 之前只有一条人工链路：`python -m butler knowledge-extract`。
没人记得敲命令，[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20) 里的原文就一直不变成 [tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e) 里的事实；
本地实测 2 条原文、0 条事实。

本轮把「什么时候提炼」交给 Butler 进程内的一个单线程调度器（方案 A），并把过期原文清理并入同一调度器；
人工命令保留，但和调度器共用一把跨进程锁，避免同一批原文被送两次模型。

#### 文件与代码位置

- `src/butler/runtime/knowledge_auto.py`（新增）
  - `LOCK_STALE_SECONDS`（`:21`）、`acquire`（`:29`）、`release`（`:62`）：O_EXCL 建锁，mtime 超过 30 分钟视为上次进程崩溃并回收。
  - `ExtractScheduler`（`:71`）：`status`（`:124`）、`_pending`（`:145`）、`run_once`（`:163`）、
    `_record`（`:199`）、`_prune`（`:238`）、`_round`（`:258`）、`_loop`（`:276`）、`start`、`stop`、`trigger`（`:320`）。
- `src/butler/config.py`
  - `Config` 新增 9 个字段（`:75`–`:84`）：`knowledge_auto_extract`、`knowledge_extract_interval_minutes`、
    `knowledge_extract_batch`、`knowledge_extract_max_owners`、`knowledge_extract_min_backlog`、
    `knowledge_extract_idle_seconds`、`knowledge_extract_retry_minutes`、`knowledge_auto_prune`、
    `knowledge_prune_interval_hours`。
  - 路径方法 `knowledge_extract_state_path`（`:172`）、`knowledge_extract_audit_path`（`:176`）、
    `knowledge_extract_lock_path`（`:179`）。
  - `load()` 新增 `bounded`（`:221`）逐项校验区间；`auto_extract` / `auto_prune` 默认 `False`（`:228`、`:229`）。
- `src/butler/server.py`
  - GET `/v1/knowledge/extract`（`:142`）、POST 同名（`:322`）。
  - `make_handler(..., extract=None)`（`:51`）；`serve()` 构造（`:477`）、`start()`（`:488`）、`stop()`（`:496`）。
- `src/butler/agent/hermes.py:73` 与 `src/butler/runtime/concurrency.py:17`：`extract` 不再落进 `chat` 作用域，
  与 `heartbeat` 并列单列，避免常驻提炼累积聊天上下文、也避免和回复抢同一把会话锁。
- `src/butler/__main__.py:74`：CLI 提炼先抢同一把锁，抢不到输出 `自动提炼正在运行，稍后再试` 并返回 1。
- `src/dashboard/api/knowledge.py`：`extract_status`（`:47`）、`extract_trigger`（`:57`）。
- `src/dashboard/api/support.py`：把心跳那次的转发抽成 `_butler_post` 公共函数，`trigger_butler_heartbeat` 与新的 `trigger_butler_extract` 共用；非本机模式的报错文案顺带从「当前模式的心跳由对端管理台维护」统一成「当前模式由对端管理台维护」。
- `src/dashboard/routes.py`：GET 路由（`:47`）、POST 路由（`:68`），并加入 GET/POST 门禁清单（`:18`、`:25`）。
- `src/dashboard/config_view.py:53`：`BT_DEFAULTS['knowledge']`，配置页可编辑这组开关。
- `src/dashboard/config_schema.py:92`–`:101`：字段中文名、含义与取值范围。
- `web/src/views/FactsView.vue`：`extractLine`（`:53`）、`loadExtract`（`:111`）、`runExtract`（`:121`）、
  状态条模板（`:259`）。
- `web/src/styles/knowledge.css:41`：`.extract-bar` 一节，只用既有令牌。
- `web/src/views/ConfigurationView.vue:14`、`:134`：新增「知识库」分类并归位 `butler.knowledge`。

##### 连带修正的词条锚点

本批往 `server.py`（新增两个路由分支与两个参数）、`routes.py`（新增三行 GET、一行 POST）、
`config_schema.py`（新增知识库字段表）、`config_view.py`（新增分类）、`README.md`（新增知识库一节）
里插了行，一批既有词条的行号因此后移。这里只改锚点与代码依据，不改结论：
[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)、[apis/dashboard-queue](queue-storage.md#doc-0b08697b4d4a4f)、[apis/dashboard-workflow](dashboard.md#doc-0d1f17e6436714)、
[symbols/butler-handle](butler.md#doc-eba67ca6f97d80)、[symbols/butler-result](butler.md#doc-a9181bbf2979fd)、[concepts/model-error-contract](model-backends.md#doc-77e385a27b73a6)、[modules/butler](butler.md#doc-38393df7a7b4da)、
[modules/dashboard](dashboard.md#doc-bb47c9474691fe)、[modules/models](model-backends.md#doc-69928b2a06b8f9)、[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47)、[tables/kb-facts](knowledge-vault.md#doc-eae62eb158097e)。

#### 接口与字段

Butler 新增两个端点，都要求既有 Bearer token：

| 方法 | 路径 | 语义 |
|---|---|---|
| GET | `/v1/knowledge/extract` | `enabled`、`knowledge_enabled`、`auto_extract`、`auto_prune`、`interval_minutes`、`batch`、`max_owners`、`min_backlog`、`idle_seconds`、`next_run_at`、`last_run_at`、`last_report`、`failures`、`last_error`、`next_prune_at` |
| POST | `/v1/knowledge/extract` | `{owner?, batch?, dry_run?}`；202 启动，409 `busy`，503 调度器未启用 |

管理台 `GET /api/knowledge/extract` 透传 Butler 响应并补 `available`；Butler 不可达时返回
`{available: false, error}`（200，不是 500），前端按降级处理。`POST /api/knowledge/extract` 只透传
`owner` / `batch` / `dry_run`；参数合法性由 Butler 判（非整数 `batch`、非布尔 `dry_run`、超长 `owner` 各回 400），
管理台把 400/409 原样往上递。

单轮判定顺序写在 `_round`（`src/butler/runtime/knowledge_auto.py:258`）：开关 → 到点 → 最近
`idle_seconds` 内无人说话 → 有积压 → 抢到跨进程锁。前四条不满足只推迟（`deferred` / `no_backlog` / `skipped`），
不算失败；只有模型调用与写库异常才累加 `failures` 并按
`min(6h, retry_minutes * 2^(failures-1))` 退避。

#### 数据库与迁移

不涉及。没有新增表、列或索引，[tables/kb-owners](knowledge-vault.md#doc-68c7e63f609bfb) 的 `extracted_upto` 仍是唯一游标，
[tables/kb-episodes](knowledge-vault.md#doc-84df4a3514bf20) 的 `at` 仍是 prune 的唯一依据。

新增的是运行时文件，都在 `data/cache/`：`knowledge_extract_state.json`（下次时间、失败计数、上次报告）、
`knowledge_extract_audit.jsonl`（只记事件、条数与错误类型）、`knowledge_extract.lock`（跨进程单飞）。
它们不入库、不进发布包。

#### 前端消费点

- 知识库页顶部新增一行状态：开关是否打开、上次提炼时间与写入条数、下次时间；失败时显示错误类型与重试时间。
  实现是 `extractLine` 计算属性，不摆装饰性状态灯。
- 「立即提炼」按钮只在拿到 Butler 状态时出现；触发后先给即时反馈，4 秒刷新状态、15 秒刷新事实表格。
  Butler 无此端点（旧进程）时显示「读不到自动提炼状态」并隐藏按钮，页面其余部分照常只读展示。
- 配置管理新增「知识库」分类，11 个字段可编辑；`auto_extract` / `auto_prune` 以布尔下拉呈现，
  保存后提示需自行重启 Butler。
- `web/scripts/smoke.mjs` 新增 `/api/knowledge/extract` 假数据与 `/api/configuration` 的 knowledge 段，
  断言状态条文案、按钮存在且可点、点击后确实发了一次 POST，以及「知识库」分类能显示字段。

#### 测试与异步任务

- 新增 `tests/butler/test_knowledge_auto.py`（10 项）：无积压不调模型、写事实后游标前移且使用 `extract` 会话、
  `min_backlog` 门禁、模型失败指数退避且不前移游标、CLI 持锁时调度器跳过、`trigger` 忙时返回 `busy`、
  默认关不启线程、最近有消息时顺延、配置越界报错，以及一条真 HTTP 用例（状态可读、三种非法参数各 400、
  合法触发 202 且后台释放单飞锁、忙时 409）。
- `tests/dashboard/test_knowledge_view.py` 的真 HTTP 用例扩到四条路由：自动提炼 GET 包 `available`、
  POST 去空白后转发、409 透传、Butler 不可达时 GET 仍 200 而 POST 503、远程模式四条全 503。
- 既有 `tests/butler`、`tests/dashboard`、`tests/integration` 全部通过；`npm run build` 与 `npm run smoke` 通过。
- 新增异步任务：`butler-knowledge-extract`（定时轮）与 `butler-knowledge-extract-manual`（手动触发）
  两个 daemon 线程，随 `serve()` 启停；它们不写微信队列、不碰 UI。

#### 风险与回滚

- 调度器在 Butler 进程内，**必须重启 Butler 才会启用**；旧进程不认新端点，管理台自动降级为只读状态。
- 模型费用：只在「有积压 + 消息间隙 + 抢到锁」时调用；失败退避上限 6 小时，不会每分钟重试。
- 提炼与回复共用模型后端，`ReloadableBackend.request()` 只做引用计数，后台提炼不阻塞回复；
  但切换模型需要等在飞的提炼调用结束。
- 锁文件残留在 `data/cache/` 时，30 分钟后自动回收，不需要人工删除。
- 回滚：把 `[knowledge] auto_extract` 改回 `false` 重启 Butler 即可停线程；撤掉新端点与前端状态条不影响既有
  CLI 与只读页面。
<!-- end-migrated-part: doc-4f707cfb04b69a -->
