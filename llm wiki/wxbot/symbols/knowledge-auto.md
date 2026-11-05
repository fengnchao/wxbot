---
type: symbol
module: runtime
summary: Butler 进程内的定时提炼调度器，一轮只喂模型一批，并与 CLI 共用跨进程单飞锁
coverage: core
last_verified: '2026-11-04'
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
  line: 490
  anchor: knowledge_extract = ExtractScheduler(butler, cfg, log=_log)
- path: src/butler/__main__.py
  line: 74
  anchor: lock=acquire(cfg.knowledge_extract_lock_path())
changes:
- raw/changes/2026-11-01-knowledge-auto
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-01-knowledge-atlas-index
- raw/changes/2026-11-04-index-tts-skill
calls:
- symbols/knowledge-extract
called_by: []
---
# knowledge_auto

## 签名与职责

```
acquire(path) -> str | None
release(handle) -> None
ExtractScheduler(butler, cfg, log=None)
  .status() -> dict
  .run_once(owner='', batch=None, dry_run=False) -> dict
  .trigger(owner='', batch=None, dry_run=False) -> (bool, str)
  .start() / .stop()
```

职责只有一句：决定**什么时候**把 [[tables/kb-episodes]] 里还没提炼的原文交给
[[symbols/knowledge-extract]]，以及把结果与下次时间记下来。

`_round`（`:258`）的判定顺序是硬契约：开关 → 到点 → 最近 `idle_seconds` 秒内没人说话 → 有积压 →
抢到跨进程锁。前四条任意一条不满足都只推迟（`deferred` / `no_backlog` / `skipped`），不累加失败；
只有模型调用与写库异常才记 `failures` 并按 `min(6h, retry_minutes * 2^(failures-1))` 退避（`:199`）。

`_pending`（`:145`）按 `KnowledgeStore.owners()` 的最近说话顺序取人，每人要求游标之后至少有
`min_backlog` 条原文；不指定 `owner` 时一轮最多 `max_owners` 人。

## 所属模块

[[modules/runtime]]。它不是 HTTP 处理器，也不在请求路径上：`serve()` 只负责构造、`start()` 与 `stop()`
（`src/butler/server.py:490`、`:487`、`:495`）。

放这里而不是 `agent/`：它不参与 prompt 编排，只调度 [[symbols/knowledge-extract]]。

## 调用方与反向引用

- `butler.server.serve()`：进程内唯一的生产调用方，随 serving 生命周期启停。
- `butler/__main__.py:74`：人工命令 `knowledge-extract` 先用同一把锁，抢不到直接报错退出，
  避免和定时轮同时喂同一批原文。
- 管理台经 `POST /v1/knowledge/extract` 走 `trigger()`，由后台线程执行，不阻塞 HTTP 响应。

## 调用了谁

- `knowledge_extract.extract`（单个 owner 一批）与 `MAX_BATCH`
- `KnowledgeStore.owners` / `episodes_of` / `extracted_at`（时刻游标）/ `prune`
- `HermesClient.reset` / `chat`，固定 `session_kind='extract'`

`prune` 删完成天日记后会把每人的 `vault/index.md` 重画一遍（[[tables/knowledge-vault]] 的 `rebuild_index`）。两件事共用一条线程：`start()` 要求 `auto_extract=true`，所以提炼关着时清理也不会跑；跑到一轮后是否顺便清理再由 `auto_prune` 决定（`_prune_due`，`:233`）。

## 副作用（库/文件/事件/网络）

- 写 [[tables/kb-facts]] 与 [[tables/kb-owners]] 的游标，全部经 [[symbols/knowledge-extract]]。
- 写 `data/cache/knowledge_extract_state.json`（原子替换）、`knowledge_extract_audit.jsonl`（追加）、
  `knowledge_extract.lock`（O_EXCL 创建，退出时删除）。
- 调用模型：每轮最多 `batch` 条原文 × `max_owners` 人。
- 不写微信队列、不碰 UI、不发微信消息。

## 契约、测试与风险

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

## 代码依据与修改来源

- `src/butler/runtime/knowledge_auto.py:29` — `def acquire(path):`
- `src/butler/runtime/knowledge_auto.py:71` — `class ExtractScheduler:`
- `src/butler/runtime/knowledge_auto.py:163` — `def run_once(self, owner='', batch=None, dry_run=False):`
- `src/butler/runtime/knowledge_auto.py:258` — `def _round(self):`
- `src/butler/runtime/knowledge_auto.py:320` — `def trigger(self, owner='', batch=None, dry_run=False):`
- `src/butler/server.py:490` — `knowledge_extract = ExtractScheduler(butler, cfg, log=_log)`
- `src/butler/__main__.py:74` — `lock=acquire(cfg.knowledge_extract_lock_path())`

[[raw/changes/2026-11-01-knowledge-auto]]

[[raw/changes/2026-11-01-knowledge-atlas-index]]


## 本次核对

[[raw/changes/2026-11-04-index-tts-skill]]：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [[apis/index-tts]]，其余已述契约未改。
