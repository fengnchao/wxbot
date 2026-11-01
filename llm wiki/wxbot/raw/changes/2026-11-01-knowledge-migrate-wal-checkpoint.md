---
type: change
title: 知识库迁移改名留底前先合并 WAL
pages:
- tables/knowledge-vault
- tables/kb-episodes
- tables/kb-facts
- tables/kb-owners
---
# 知识库迁移改名留底前先合并 WAL

## 目标与背景

在真实数据上执行 `python -m butler knowledge-migrate` 后核对留底文件，发现 `episodes.sqlite3.migrated` 单独只有 2 条、`facts.sqlite3.migrated` 连 `kb_facts` 表都读不出来，而 vault 里是完整的 5 条原文 + 1 条事实。原因是旧库处于 WAL 模式：`_import_sqlite` 用 `mode=ro` 只读 URI 打开，读得到 WAL 里的行却永远不会 checkpoint 回主库；`migrate_legacy` 接着直接 `Path.replace()` 改名，`-wal` 与 `-shm` 的名字还停在旧文件名上，SQLite 不再认这对边车，留底库就成了空壳。回滚会丢掉 7 条里的 4 条。

本次改动让改名前先合并 WAL，并把真实数据目录里已经失配的边车补回去。

## 文件与代码位置

`src/butler/runtime/knowledge_store.py`

- 新增 `_checkpoint_legacy(path)`（`:593`）：用读写连接执行 `PRAGMA wal_checkpoint(TRUNCATE)`，再删掉残留的 `-wal` / `-shm`。读写连接才会把 WAL 页写回主库；只读连接只能读。
- `migrate_legacy`（`:660`）在四处 `.replace(...)` 改名之前各插一次调用：`knowledge.sqlite3`、`p-*/episodes.sqlite3`、`p-*/facts.sqlite3`、`index.sqlite3`。

`tests/butler/test_knowledge_store.py`

- 新增 `test_migrated_backup_keeps_rows_from_an_open_wal`：在写连接仍打开时复制主库与 `-wal`（模拟进程被强杀、WAL 未合并），跑 `migrate_legacy` 后断言留底库能独立打开且仍是 3 条，同时断言没有残留 `-wal` / `-shm`。

## 接口与字段

不适用：只改迁移内部实现，`migrate_legacy(data_dir, log=None) -> int` 的签名与返回值不变，`KnowledgeStore` 的方法集不变。

## 数据库与迁移

留底文件的语义被修正：`*.sqlite3.migrated` 从「改名后的主库文件」变成「已合并 WAL 的完整库」。在此之前，任何 WAL 模式旧库的留底都是不完整的——`knowledge.sqlite3`、`p-*/episodes.sqlite3`、`p-*/facts.sqlite3`、`index.sqlite3` 四类都受影响。

已在真实 `data/knowledge` 上就地修复：把三个 `.migrated` 临时改回原名与边车配对，checkpoint 后再改名，复验 `episodes.sqlite3.migrated` = 5 条、`facts.sqlite3.migrated` = 1 条，`-wal` / `-shm` 全部清除。

## 前端消费点

不适用：vault 内容与 `index.json` 未变，管理台的知识库页读到的仍是 5 条原文与 2 条事实。

## 测试与异步任务

`pytest tests/butler` 全绿，含新增用例。新增用例的有效性用一次性脚本验证过：把 `_checkpoint_legacy` 替换成空函数后，留底库直接抛 `no such table: kb_episodes`——说明它确实能抓住这个缺陷，而不是恒真断言。

不涉及异步任务：迁移只能由人工在停服状态触发（`python -m butler knowledge-migrate`），常驻线程不调用它。

## 风险与回滚

风险一：`PRAGMA wal_checkpoint(TRUNCATE)` 在仍有其它连接持锁时会失败。代码捕获 `sqlite3.DatabaseError` 后继续改名，此时留底仍可能不完整——但这个前提已被「迁移必须在停服状态跑」覆盖。

风险二：`-wal` / `-shm` 的删除在 Windows 上可能因文件锁失败，代码吞掉 `OSError`。留下的边车只是垃圾文件，不影响已合并的主库，但下次迁移会再扫一遍。

风险三：真实数据目录的修复是「改名 → checkpoint → 改名」，中途中断会让文件名字停在中间态。数据本身不丢（vault 已完整、主库与 WAL 都在），重跑一次即可收敛。

回滚：`_checkpoint_legacy` 是纯增量，删掉它的调用即回到旧行为（留底可能不完整，但 vault 不受影响）。已修好的留底库不需要回滚。
