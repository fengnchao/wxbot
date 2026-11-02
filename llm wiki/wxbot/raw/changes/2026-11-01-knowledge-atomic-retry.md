---
type: change
title: 知识库写入在文件被占用时退避重试
pages:
- tables/knowledge-vault
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
- apis/dashboard-knowledge
- symbols/knowledge-extract
---
# 知识库写入在文件被占用时退避重试

## 目标与背景

Obsidian 打开一个 vault 后会持续索引目录。Butler 正好在这时写 `index.md` 或节点文件，`os.replace` 会抛 `PermissionError: [WinError 5] 拒绝访问`。

这不是推测：给 101 的 vault 灌演示数据时第 2 条 `add_fact` 就撞上了，`index.md.tmp` 留在 vault 根，被 Obsidian 当成一个空文件索引；删掉残留 tmp 后立即重试就成功。更麻烦的是 [[concepts/message-pipeline]] 的 `_record_episode` 把异常记进日志就吞掉（`src/butler/agent/core.py:328`），代价是那一轮对话没落库，且没有任何补偿。这类冲突只持续几十毫秒，所以让写入自己等一下再试。

## 文件与代码位置

- `src/butler/runtime/knowledge_store.py:104` — `_atomic_write(path, text, attempts=3, delay=0.05)`。原来是「写 tmp + `os.replace`」两行直写；现在把两步包进 `for attempt in range(tries)`，只捕获 `PermissionError`，最后一次仍失败时用 `suppress(OSError)` 清掉 tmp 再 `raise`。
- `src/butler/runtime/knowledge_store.py:5` — `from contextlib import closing, suppress`，新增 `suppress`：清理 tmp 失败不能把原始异常盖掉。
- 四个调用点没有改动：`_save`（`:346`）、`record`（`:440`）、`add_fact`（`:475`）、`rebuild_index`（`:573`）。`rebuild_index` 的调用点是收尾那一行（`:573`），函数定义在 `:514`。
- 本次改动让 104 行之后的符号整体下移 15 行，六个词条里指向该文件的行号同时重算：`class KnowledgeStore` 286→301、`record` 408→423、`add_fact` 430→445、`index_page_path` 312→327、`rebuild_index` 499→514、`episodes_of` 565→580、`read` 581→596、`facts` 610→625、`sessions` 648→663、`_checkpoint_legacy` 673→688、`_import_sqlite` 694→709、`_import_memory` 718→733、`migrate_legacy` 740→755、`_touch` 334→349、`_catalog` 319→334、`_recount` 355→370、`owners` 402→417、`extracted_at` 467→482、`set_extracted_at` 472→487、`prune` 482→497、`close` 561→576，以及迁移段里 `kb_episodes` 700→715、`kb_facts` 706→721、`index` 变量 763→778。

## 接口与字段

不适用。`_atomic_write` 是模块内私有函数，新增的 `attempts` / `delay` 两个参数都有默认值，没有调用点传参；HTTP 接口、前端 GET 参数、Markdown 文件格式与事实行尾注释全部不变。

## 数据库与迁移

不适用。知识库已不在 SQLite 里，写入目标是 Markdown 文件；重试不改变文件内容，也不额外产生文件——成功时 tmp 已被 `os.replace` 移走，放弃时被显式删掉。

## 前端消费点

不适用。管理台对知识库只读，写入路径全在 Butler 侧。

## 测试与异步任务

`tests/butler/test_knowledge_store.py` 新增四条：

- `:260` 前两次 `os.replace` 抛 `PermissionError`、第三次成功 → 内容落盘，且不留 `note.md.tmp`。
- `:284` `time.sleep` 收到的序列是 `[0.05, 0.1]`：退避递增，三次尝试最坏多等 150ms。
- `:303` 一直失败 → 抛 `PermissionError`，tmp 已清、目标文件没有被写成半截。
- `:317` `OSError(28)`（磁盘满）→ `os.replace` 只被调一次，不重试。

用例都通过 `monkeypatch.setattr` 替换 `os.replace` / `time.sleep`，不改真实文件系统行为；`tests/butler/test_knowledge_store.py`、`test_knowledge_extract.py`、`test_knowledge_auto.py`、`test_knowledge_capture.py` 四个文件 50 条全过。

异步任务：`_record_episode` 仍在请求返回前同步调用 `record`，单次写入的最坏耗时从「一次 `os.replace`」变成「三次 `os.replace` + 150ms」。

## 风险与回滚

- 重试发生在 `KnowledgeStore._lock` 内（`record` / `add_fact` 的 `with self._lock` 包着 `_atomic_write`），最坏多阻塞 150ms。知识库写入是单进程调用，不阻塞对话生成，只让该轮落库晚一点。
- `PermissionError` 也可能是真实权限问题（只读目录、ACL 拒绝）。这时会白等 150ms 再抛，日志里的异常与改动前一致。
- 非 `PermissionError` 的错误（磁盘满、路径不存在）不重试，保持原来的失败速度。
- 回滚：把 `_atomic_write` 恢复成「写 tmp + `os.replace`」两行版本即可，无数据迁移、无文件格式变化；回滚后须同步把六个词条的行号减回 15。
