# 查图与维护

用 Obsidian 打开本目录 `llm wiki/wxbot/`，从 [[index]] 开始；关系图使用 `[[目录/词条]]` 双链。沿用已有 `.obsidian` 配置，与代码一起由项目 Git 管理，不初始化嵌套仓库。

代码是事实源，图谱保存经模型核对的结构知识，raw 修改记录保存每次入库的依据。项目操作说明仍以根 README.md 为准。

## 改前查询

在项目根使用已有虚拟环境：

```powershell
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" status
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" query reply_complete /v1/handle --depth 1
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" query outbox --depth 2 --save outbox-review
```

`query` 对文件名、简介和正文做关键词匹配，多个关键词按任一命中排序；`--limit` 限制初始命中，随后展开双向关联。默认只读；`--save` 创建当天的 draft 影响报告、刷新索引并追加 query 日志，文件存在则拒绝覆写。它提供候选和提纲，**不会自动得出完整影响结论**。

读词条并核对当前代码，报告要改的位置、调用方、前后端字段契约、数据库血缘、测试/异步任务、风险和回滚。未覆盖部分先查源码并建档，明确记录缺口。跨模块或高风险报告保存在 `impacts/`。已明确授权的任务按范围继续；用户要求先确认或范围尚未授权时等待确认。

## 改后记录与入库

```powershell
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" change handle-contract --title "调整消息处理契约"
# 填完新建的 raw/changes/YYYY-MM-DD-handle-contract.md，核对 diff/源码并更新词条
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" ingest YYYY-MM-DD-handle-contract
.\.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" lint
```

1. 修改记录填写七项事实；不涉及的项目明确写“不涉及”和原因。
2. 在 raw 元信息的 `pages` 列出全部本次核对的词条 ID，如 `apis/butler-handle`，相对库根、不含扩展名。
3. **模型**读代码/diff，整合模块职责、API 字段、表结构/字段血缘、符号调用和副作用；修正行号/锚点，更新 `last_verified`、反向关系，在词条 `changes` 追加本条 raw ID，正文也链接该记录。
4. `ingest` 仅为记录所列词条登记来源快照，刷新 [[index]]，追加 [[changelog]]；不调用模型生成内容、不改源码，不能替代第 3 步。
5. 执行全图 `lint`，评审代码、raw、词条、索引、日志、`ingest-state.json`。`ingest` 的 OK 不代表全图已通过巡检。

`change` 创建骨架时追加 change 日志；手写 raw 时由模型追加同格式日志。查询、巡检默认只读；需要归档巡检时由模型保存待办并追加 lint 日志。

## 追加历史与冲突

raw 命名 `YYYY-MM-DD-短主题.md`；raw 与 changelog 只追加。已入库 raw 与代码冲突时，以代码为准，**新增更正记录**，在 `supersedes` 写旧记录 ID，正文列出旧结论、新结论和证据，再更新词条入库。这解决原方案“只追加”和“回写修正”的矛盾，禁止手改快照绕过 raw 保护。

新旧事实有冲突时在词条“冲突与待确认”中说明依据；不静默覆盖。多条 raw 按日期及依赖顺序逐条入库。重命名/删除词条须先修复引用，写迁移记录；当前工具报 `page-missing`，不会自动清除历史状态。

## 巡检边界

机器检查元信息、断链、来源文件/行号/锚点、完整文件摘要漂移、词条未入库、raw 改写/丢失/漏入库、显式 `calls/called_by` 对称、`depends_on` 依赖环及孤立词条。只允许公开源码、示例配置和开发文档，不读取认证、运行时配置、数据库、data/cache。

来源摘要统一 CRLF/LF，按完整文件计算，因此文件中无关改动也会触发 `source-drift`。模型须复核后写新记录，不能直接更新摘要消除提示。`anchor` 必须是来源指定行的非空原文片段，用于发现移动。

语义巡检由模型检查：接口与前端契约、迁移后的最终表结构、字段跨层含义、调用方遗漏、重要符号缺页、重复字段/逻辑、业务规则过时及测试覆盖。**机械 lint 不能证明这些结论。**

## 格式

同一时间只由一个开发者/模型写入图谱。入库必须保留词条的历史 `changes`；来源与词条路径均拒绝符号链接/目录联接重定向，防止从源码名或 Markdown 别名读到私有文件。

用小写英文短名和稳定目录 ID；中文写标题/正文。模板见 `templates/`。YAML 的 `sources` 为 `{path, line, anchor}` 列表，path 相对项目根；`changes` 为相对库根的 raw ID 列表。概览标 `coverage: overview`，核心链路标 `coverage: core`。新增词条与所属模块互相链接。

代码位置显示为 `src/.../file.py:123`，编辑器按位置打开；Obsidian 代码跳转可另配插件。禁止 Token、真实联系人、聊天正文、生产数据入库。个人 Obsidian 工作区/缓存不入 Git。
