# 本次验证记录

日期：2026-10-31。运行命令中的临时目录均在项目下，不访问真实微信剪贴板、联系人数据库或服务。

## 本次功能

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_project_wiki.py --basetemp .tmp-wiki-tests-code-green --tb=short
```

结果：16 passed。覆盖双向链接查询、保存 draft、安全路径/来源、raw 禁止覆盖、入库幂等、代码摘要漂移、未登记词条、断链/锚点、反向调用、依赖环、孤立词条及代码块中的示例不误判为链接。

后续若审查修正代码，在本页追加新验证结果，并在最终入库前以实际结果为准。

## 整库回归的限制

执行项目全量 `python -m pytest --basetemp .tmp-wiki-full-suite --tb=short`：在约 10% 已有多项失败，随后长时间没有输出，因此中止本次启动的测试进程，未得到完整结果。没有停止或重启业务服务。

用 `python -m pytest --basetemp .tmp-wiki-suite-first-failure --maxfail=1 --tb=short` 重新定位：53 passed，1 failed。失败为：

`tests/butler/identity/test_contact_migration.py::test_nonlocal_install_preserves_channel_management_and_rejects_cutover[deepseek]`

在该文件第 412 行，期望 `not is_unified(database)`，实际为 True。本次没有修改身份迁移实现或测试；不能据本次结果宣称整个工作树通过，也未在知识图谱任务中扩展修复身份模块。

## 图谱实际核对

入库后执行 status、真实关键词 query、lint、编译和 diff 空白检查。来源限公开源码，Obsidian GUI 未做自动化验收；双链结构由本地巡检验证。

## 审查后的最终专项回归

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_project_wiki.py --basetemp .tmp-wiki-tests-final-review --tb=short
```

结果：**20 passed，1 skipped**。新增验证增量入库保留旧记录、历史来源不可丢失，以及来源和 Markdown 路径解析后的重定向拒绝。创建真实 Windows 目录联接的测试因当前沙箱不支持而跳过；确定性路径解析回归已验证拒绝逻辑。独立只读审查复核后无剩余重要发现。

交付前使用 `.tmp-wiki-tests-delivery` 再次执行专项回归：20 passed / 1 skipped。首批入库 27 pages、1 条修改记录，pending changes: 0；再次 ingest 输出 already-ingested，未重复写日志；实际 lint 输出 OK。真实关键词查询命中处理接口并展开关联消费方。脚本编译和限定本次范围的 diff 空白检查通过；未做 Obsidian GUI 验收。

后续再次巡检实际检出 queue-batches.md 的表格排版变化；保留该编辑，以 [[raw/changes/2026-10-31-queue-batches-format]] 追加登记。事实和业务代码未变，记录数由 1 增至 2。
