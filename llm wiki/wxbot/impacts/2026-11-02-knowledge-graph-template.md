---
type: impact
status: completed
date: '2026-11-02'
---
# 知识图谱模板外部化与在线编辑影响分析

## 需求关键词与图谱命中

需求：把知识图谱的目录、事实分类、索引分区与提炼规则从代码常量改成一份 Markdown 模板；新建每个用户的 vault 时按模板生成骨架；模板支持新增节点目录、新增分类、追加提炼规则；管理台新增「知识模板」页展示并编辑该模板。

图谱命中：[[tables/knowledge-vault]]、[[symbols/knowledge-extract]]、[[symbols/knowledge-auto]]、[[apis/dashboard-knowledge]]、[[modules/runtime]]、[[modules/dashboard]]、[[modules/web]]、[[concepts/identity-authority]]。

覆盖缺口：图谱没有「模板」这一概念，也没有 `dashboard/config_editor.py` 的写入约定（锁 + 版本 + 备份 + 原子替换）词条，本次按源码补齐并新建模板相关词条。

## 要改的文件、符号与调用方

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

## 接口与前端契约

新增 `GET /api/knowledge/template`：返回生效来源（override/plugin/builtin）、路径、version（sha256）、modified_at、content、解析摘要（kinds/node_types/rules/index_title）。

新增 `POST /api/knowledge/template`：`{action: validate|save|reset, content, version, acknowledge}`；400 返回带行号的校验错误，409 为版本冲突，503 为非本机安装。

`GET /api/knowledge/facts` 响应新增 `kinds` 与 `node_types` 两个数组（只增字段，不改旧字段），供前端动态映射分类名。

`FactsView.vue` 保留原有表格与筛选，仅把常量映射改为「接口下发 + 原始 key 兜底」。

## 数据库与字段血缘

不涉及 SQL。模板两层：`plugins/butler-wechat/knowledge/graph-template.md`（只读）与 `data/knowledge/template.md`（可写覆盖层），后者在 vault 之外，不会被 `facts()` 的 `vault/*/*.md` 扫描。

事实行格式 `<!-- fp|key|kind|conf|at|src|quote -->` 不变，仍由 `FACT_LINE` 正则读回；模板只影响目录名、小节名、索引分区名与 prompt，不改变行格式。`index.json` 结构不变，不新增字段。

## 风险、验证、异步任务与回滚

风险一：模板写坏会导致提炼 prompt 或索引页异常。对策：运行时宽松解析失败回退默认；页面保存前强制严格校验；模板规则只追加，内置 6 条不可删。

风险二：模板成为提示词注入面。对策：只用白名单字段拼 prompt，限长 2400 字，模板是安装者本地文件，不是外部输入。

风险三：改模板不改历史。旧 kind 在新模板中缺失时归入「其他」，旧节点目录若被删除仍会出现在索引页的未识别目录中，不丢数据。

风险四：Windows 下文件被占用。对策：保存走临时文件 + `os.replace` 并退避重试；失败给明确错误。

验证：新增 `tests/butler/test_knowledge_template.py`；改写或补充 `test_knowledge_store.py`、`test_knowledge_extract.py`；`tests/dashboard/test_knowledge_view.py` 补模板接口用例。全部离线，不启动服务、不发消息、不调模型。

回滚：删除 `data/knowledge/template.md` 即回到内置模板；代码回滚后模板文件被忽略，vault 不需要迁移。

## 实际改动与 raw 归档

已按方案落地，未偏离。实际改动与验证记录见 [[raw/changes/2026-11-02-knowledge-graph-template]]：

- 新增模板模块与随插件分发的 `knowledge/graph-template.md`；`KnowledgeStore` 与 `KnowledgeExtractor` 全部改读模板，默认值与旧行为一致。
- 新增两条模板路由与 `KnowledgeTemplateView`，页面支持校验、保存、恢复内置；`FactsView` 改为接口下发分类。
- 不涉及 SQL 或 vault 迁移；删除 `data/knowledge/template.md` 即回滚到内置模板。
- 验证：相关 5 个测试文件 65 项通过；`npm run build` / `npm run smoke` 通过（导航 9 项）；Hallmark 静态 0 FAIL、真实渲染 4 视口 0 FAIL，剩余 1 REFLEX + 1 WARN 属既有导航壳，已披露未清理。
