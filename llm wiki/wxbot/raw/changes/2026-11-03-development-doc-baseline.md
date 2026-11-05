---
type: change
title: 统一当前开发基线、配置来源与发送实现文档
pages:
- concepts/development-baseline
- modules/wiki
---
# 统一当前开发基线、配置来源与发送实现文档

## 目标与背景

逐项核对用户列出的八项旧说明，以当前工作分支源码为准纠正文档、模块说明和前端元数据；不重建已退场的包或文档。
当前根目录为 codex-butler-distribution @ 7a2ccd0；开发 worktree 的 codex/grok-setup @ db26164 多一个 WEB-001 提交。
此处仅为核对快照，不把分支名、两个 tip 同 SHA 或进程已加载版本当作长期事实。

实际处置：
1. butler/README.md 与 PROJECT_MEMORY.md 已不存在；根 README 记录当前 src/ 布局和历史说明的边界。
2. config.butler.example.toml 等示例文件已不存在；根 README 改为默认值／安装向导生成，明确实际三个配置文件名。
3. 明确正文使用剪贴板租约 + Ctrl+V + 读回校验，默认分批间隔从旧说明 0.5 秒更正为代码的 0.25 秒。
4. 区分生产默认 wxbot→Butler 与 wxbot 直接后端旁路；不把 Butler 自身的 provider 误标为调试功能。
5. 旧嵌套包目录当前不存在，不执行删除；heartbeat/ 当前含受版本控制的辅助脚本，保留其源码，不整目录忽略。
6. requirements.txt 删除“整个 Butler 无第三方依赖”的旧注释，依赖声明和版本约束不变。
7. web/package.json 描述、Vite 配置注释和流水日志模块说明统一指向 src/dashboard。
8. 新增工作树、SHA、修改状态、解释器路径与 REPO_ROOT 核对流程，正式／开发目录分叉时重新核对差异。

额外发现原目录 .venv 的 common.paths 实际导入自开发 worktree；早期未显式指定根目录的图谱查询结果不能作为当前仓库证据。
后续查询、change、ingest、lint 均显式传 --repo-root D:/work/code/wxbot；未修改可编辑安装，不把工具根目录限定当作运行环境修复。

## 文件与代码位置

- README.md：总览、生产默认与旁路、开发基线、配置来源、正文发送和维护边界。
- requirements.txt：仅头部和 tomlkit 行注释；所有依赖项不变。
- src/wxbot/config.py:1：模块说明改用实际 config.wxbot.toml；load_config 在 :110 的逻辑不变。
- src/butler/runtime/flowlog.py:1：仅模块说明中的管理台名称与解析器路径。
- web/package.json:6：仅 description；web/vite.config.js 仅更正两处注释。
- llm wiki/wxbot/concepts/development-baseline.md：补齐原图谱中的工作树／解释器基线覆盖缺口。
- llm wiki/wxbot/modules/wiki.md：互链、README 来源锚点和复核日期；coverage.md、index.md、changelog.md、ingest-state.json 随记录维护。
- 影响分析见 [[impacts/2026-11-03-development-doc-baseline]]。

## 接口与字段

不涉及 HTTP/API/DTO 或配置字段、默认值的改动；配置名、backend 层级和发送机制的说明对齐现有实现。
Python 模块执行 AST 去掉模块文档字符串后与 HEAD 相同；Vite 去掉整行注释后的执行配置相同。

## 数据库与迁移

不涉及数据库、表、字段血缘或迁移；未读取真实配置、凭据、消息或业务数据。
未删除任何历史目录、看门狗脚本或运行产物，未改变 .gitignore。

## 前端消费点

无 UI 或交互变更。package.json 除 description 外解析结果与 HEAD 相同；Vite 仅注释变化。
src/dashboard/http.py:84 的 WEBAPP_DIR 指向 web/dist，托管 /app/ 的事实未变。
构建输出写入 cache 下的临时目录，不覆盖已提交 web/dist；无新增依赖或前端字段。

## 测试与异步任务

无新增测试、异步任务或后台进程。静态语义等价检查通过：两个 Python 模块执行 AST、Vite 执行配置、requirements 依赖项均不变。
package.json 仅 description 变化；pyproject.toml、uv.lock、web/package-lock.json、.gitignore 和已提交 web/dist 未变。
使用便携 Node 24，node --check web/vite.config.js、前端 build（临时输出）和既有假数据 smoke 均通过。
本轮不执行后端回归，不能宣称后端回归通过；业务逻辑未变且未启动服务或发送微信。
图谱 ingest/lint 与 git diff --check 为本轮交付检查，结果以实际工具输出为准。

## 风险与回滚

风险是按历史资料、分支名或错误的可编辑安装识别基线；文档加入实际目录／提交／解释器核对，图谱操作显式指定当前根目录。
原目录 .venv 的绑定问题仍需独立处理，未静默修改运行环境。
回滚仅撤销本轮文档、注释、元数据和配套图谱记录的变更；无需数据库迁移或服务重启。
