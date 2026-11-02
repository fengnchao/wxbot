---
type: symbol
module: runtime
summary: 从对话原文提炼知识图谱节点的链路，CLI 与进程内调度器共用，产出实体、关系与双链，游标只在整批成功后前移
coverage: core
last_verified: '2026-11-01'
sources:
- path: src/butler/runtime/knowledge_extract.py
  line: 21
  anchor: KINDS = ('profile', 'preference', 'personality', 'goal', 'relation', 'event', 'topic')
- path: src/butler/runtime/knowledge_extract.py
  line: 24
  anchor: PROMPT = """下面是一个人和助理的若干轮对话，每条前面有编号。当前用户的名字是「%s」。
- path: src/butler/runtime/knowledge_extract.py
  line: 73
  anchor: 'def parse_facts(raw):'
- path: src/butler/runtime/knowledge_extract.py
  line: 111
  anchor: 'def render(rows):'
- path: src/butler/runtime/knowledge_extract.py
  line: 121
  anchor: 'def extract(store, owner, contact, complete, *, batch=40, log=None, dry_run=False):'
- path: src/butler/runtime/knowledge_extract.py
  line: 155
  anchor: 'def extract_all(store, complete, *, batch=40, owner='''', log=None, dry_run=False):'
- path: src/butler/runtime/knowledge_store.py
  line: 580
  anchor: 'def episodes_of(self, owner, after_at=0.0, limit=200):'
- path: src/butler/__main__.py
  line: 66
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
calls: []
called_by:
- symbols/knowledge-auto
---
# knowledge_extract

## 签名与职责

```
parse_facts(raw) -> list[dict]
render(rows) -> str
extract(store, owner, contact, complete, *, batch=40, log=None, dry_run=False) -> (read, written, parsed)
extract_all(store, complete, *, batch=40, owner='', log=None, dry_run=False) -> list[dict]
```

职责只有一句：把 [[tables/knowledge-vault]] 里**还没提炼过**的对话交给模型，把结果写成知识图谱的节点、事实行与 `[[双链]]`。

`complete` 是由调用方注入的回调（`prompt -> str`），本模块不认识 Hermes、Codex 或任何后端——CLI 传真实模型，测试传假实现。这是本模块能被用例覆盖而不联网的原因。

`parse_facts`（`:73`）从模型输出里取第一个 `[` 到最后一个 `]` 之间的 JSON：容忍代码围栏和前后废话，坏项（非对象、空 value）直接丢，`kind` 越界回落 `topic`，`subject_type` 越界回落 `person`，`confidence` 非数字回落 0.5 并夹在 0..1。`kind` 白名单 `KINDS`（`:21`）是七类：`profile` / `preference` / `personality` / `goal` / `relation` / `event` / `topic`，与 [[tables/knowledge-vault]] 的 `FACT_KINDS` 逐字一致——两边不同步会让分类落到 `topic`。`_links`（`:56`）允许 `"李四"` 与 `{"name":"李四","type":"person"}` 两种写法，最多收 `MAX_LINKS`（8）个。

`render`（`:111`）把原文排成 `[id] 用户：…` / `助理：…` 两行一组。编号是给模型对 `quote` 用的，也方便人回看；编号来自 `episodes_of` 返回时补的序号，不是数据库自增 id。

**产出比 SQLite 时代多了三个字段**：`subject`（这条事实挂到哪个节点）、`subject_type`（`person` / `org` / `topic`）、`links`（正文里生成哪些双链）。前两个决定 `add_fact` 写哪个文件，第三个决定 graph view 连不连得上——没有它们写出来的只是一堆孤立事实行。

## 所属模块

[[modules/runtime]]。放在 `butler/runtime/` 而不是 `agent/`：它不参与对话，不接触 prompt 编排，也不在 `serve()` 的请求路径上。

## 调用方与反向引用

三个入口，都只经过本模块这一条写路径：

- `python -m butler knowledge-extract`（`src/butler/__main__.py:66`）：人工跑一趟。CLI 构造临时 `Contact`（`uid='knowledge-extract'`）承载 profile，把 `hermes.chat(..., session_kind='extract')` 作为 `complete` 传进来；跑之前先 `acquire` 跨进程锁（`:74`），抢不到就报「自动提炼正在运行」并返回 1。
- [[symbols/knowledge-auto]] 的 `run_once`（`src/butler/runtime/knowledge_auto.py:182`）：常驻调度器逐个 owner 调 `extract`，`complete` 同样是 `hermes.chat(..., session_kind='extract')`，每轮 `reset` 一次会话。
- 管理台「立即提炼」不是第四个入口：`POST /v1/knowledge/extract` 交给调度器的 `trigger()` 在后台线程执行，HTTP 只拿 202。

HTTP 请求里**不直接跑提炼**：一轮要几十秒到几分钟，挂在请求上必然超时。

## 调用了谁

- `KnowledgeStore.extracted_at` / `set_extracted_at`（`:482` / `:487`，时刻游标，不是行号游标）
- `KnowledgeStore.episodes_of`（`:580`，按 `at > 游标` 取一批新原文，上限 1000）
- `KnowledgeStore.add_fact`（写节点事实行，靠指纹去重）
- `KnowledgeStore.owners`（`extract_all` 遍历目录）

不调用模型 SDK、不读配置、不发网络请求。

## 副作用（文件/事件/网络）

写 [[tables/knowledge-vault]] 的实体节点 Markdown（每条事实一行，行尾注释带 `fp` / `key` / `kind` / `conf` / `at` / `src` / `quote`），并推进 `index.json` 里的 `extracted_at` 游标。

**不写对话日记**、不改 prompt、不写 `business.sqlite3`。`dry_run=True` 时两样都不写，只把结果打到日志。

## 契约、测试与风险

游标契约：

- 整批成功才 `set_extracted_at(owner, last_at)`，`last_at` 是本批**最大的 `at` 时间戳**（`:133`），不是行数、不是 id。
- 模型输出里**完全没有方括号**→ 判为解析失败，游标不前移，下次重来（`:136`）。
- 输出里方括号存在但内容不是 JSON、或确实是 `[]` → 按「这批量没有值得记的内容」处理，游标照常前移，避免同一批反复烧模型。
- `dry_run` 不前移游标，否则会跳过一段没写进 vault 的对话。
- 游标是时刻而非位置，所以**同一秒内晚到的原文可能被跳过**；`record` 写入时间由 `at` 决定，正常的顺序写入没有这个问题。

`extract_all` 单人异常只记进 `report[owner]['error']`（异常类型名），继续下一个人。

本地用例 `tests/butler/test_knowledge_extract.py`：围栏与废话容错、坏项丢弃、写入与游标前进、重复提炼幂等（同一 `fp` 不写第二行）、无法解析时游标不动、空数组算成功、dry-run 不写库、单人失败不中断、`owner` 过滤。

风险：提炼质量完全取决于模型；`PROMPT` 里「不推测、不补全、助理的话不作事实来源」「矛盾陈述各写一条」是硬约束，改提示词等于改数据质量。批量上限 `batch` 夹在 1..200（`MAX_BATCH`），字段长度上限见 `MAX_VALUE`(500) / `MAX_KEY`(80) / `MAX_QUOTE`(300) / `MAX_LINKS`(8)。`subject` 清洗后会决定文件名，同名不同实体将合并进同一个节点——这是 `_safe()` 的已知边界。

## 代码依据与修改来源

- `src/butler/runtime/knowledge_extract.py:21` — `KINDS = ('profile', 'preference', 'personality', 'goal', 'relation', 'event', 'topic')`
- `src/butler/runtime/knowledge_extract.py:24` — `PROMPT = """下面是一个人和助理的若干轮对话，每条前面有编号。当前用户的名字是「%s」。`
- `src/butler/runtime/knowledge_extract.py:56` — `def _links(raw):`
- `src/butler/runtime/knowledge_extract.py:73` — `def parse_facts(raw):`
- `src/butler/runtime/knowledge_extract.py:111` — `def render(rows):`
- `src/butler/runtime/knowledge_extract.py:121` — `def extract(store, owner, contact, complete, *, batch=40, log=None, dry_run=False):`
- `src/butler/runtime/knowledge_extract.py:155` — `def extract_all(store, complete, *, batch=40, owner='', log=None, dry_run=False):`
- `src/butler/runtime/knowledge_store.py:482` — `def extracted_at(self, owner):`
- `src/butler/runtime/knowledge_store.py:487` — `def set_extracted_at(self, owner, at):`
- `src/butler/runtime/knowledge_store.py:580` — `def episodes_of(self, owner, after_at=0.0, limit=200):`
- `src/butler/__main__.py:66` — `if args.command=='knowledge-extract':`
- `src/butler/runtime/knowledge_auto.py:182` — `read, written, parsed = extract(`

[[raw/changes/2026-11-01-knowledge-sharding]]
[[raw/changes/2026-11-01-knowledge-sessions]]
[[raw/changes/2026-11-01-knowledge-auto]]
[[raw/changes/2026-11-01-knowledge-vault-graph]]
[[raw/changes/2026-11-01-knowledge-atlas-index]]
[[raw/changes/2026-11-01-knowledge-atomic-retry]]
