---
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
---
# 知识图谱模板外部化为 Markdown 并支持管理台在线编辑

## 目标与背景

原来的节点目录、事实分类、索引分区和提炼规则全是代码常量：`knowledge_store.py` 的 `NODE_DIRS` / `FACT_KINDS` / `FACT_SECTIONS` / `INDEX_SECTIONS`，加上 `knowledge_extract.py` 的 `KINDS` 与整段 `PROMPT`。想给某个人多加一个「项目」目录，或让提炼多守一条规矩，只能改代码再重启 Butler。

本次把口径搬到一份 Markdown 模板：新建用户 vault 时按模板建骨架，提炼时按模板拼 prompt 与白名单；模板可在管理台「知识模板」页直接改。模板只决定「写到哪里、叫什么、按什么口径提炼」，事实行尾的机器可读注释仍是解析契约，不由模板配置。

## 文件与代码位置

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

## 接口与字段

新增两条：

- `GET /api/knowledge/template` → `{available, source, override, path, active_path, version, modified_at, content, summary, errors, limits}`。`source` 是 `override` / `plugin` / `builtin`；覆盖层坏了也返回原文与逐行错误，页面才能修。`version` 是覆盖层的 sha256，没有覆盖层时为空串。
- `POST /api/knowledge/template`，请求 `{action: validate|save|reset, content, version, acknowledge: true}`，动作头 `X-Wxbot-Knowledge-Action: 1`。`validate` 不落盘；`save` 版本不符回 409，内容不合法回 400 且带 `errors[{line, message}]`；`reset` 备份后删除覆盖层。非本机模式两条都 503。

`GET /api/knowledge/facts` 与 `GET /api/knowledge` 响应**只增字段**：`kinds[{key, label, section, hint}]`、`node_types[{key, label, description}]`。旧字段形状不变。前端不再维护第二份中文分类表，新增 kind 会直接出现在筛选与「类型」列。

## 数据库与迁移

不涉及 SQL，也不改事实行格式：`<!-- fp|key|kind|conf|at|src|quote -->` 仍是 `FACT_LINE` 的解析契约。模板覆盖层放在 `data/knowledge/template.md`，在 vault 之外，不会被 `facts()` 的 `vault/*/*.md` 扫描。

已有 vault 不需要迁移：`_ensure_vault` 只补缺失目录；`add_fact` 写新节点时 `_atomic_write` 自建父目录，所以老库也能多出新目录。模板里被删掉的旧分类不会丢历史事实，读取时按节点正文原有小节展示；新写入的未知 kind 落 `topic`（或模板第一类），索引页归入「其他」。

模板约束：必须保留 `person` 节点类型与 `topic` 分类（分别是 `subject_type` / `kind` 的兜底）；目录名不得与 `episode_dir` 重名；kind ≤ 20、节点类型 ≤ 12、规则 ≤ 20；说明与规则合计 ≤ 2400 字；文件 ≤ 256 KB。内置 6 条安全规则不可删，模板规则只追加。

## 前端消费点

- `KnowledgeTemplateView.vue` 的 `load()`（`:43`）调 `GET /api/knowledge/template`；`submit()`（`:72`）发 POST，错误按 `errors[{line, message}]` 拼成「第 N 行：…」；`save`（`:107`）/ `reset`（`:113`）各自先确认。没有修改时保存禁用；没有覆盖层时恢复禁用。
- `FactsView.vue` 的类型列与筛选改用接口下发的 `kinds`，`LEGACY_KINDS` 仅在接口缺字段时兜底。
- 外部接入模式下 `App.vue` 的 `hidden` 集合包含 `knowledge-template`，与知识库两页一起隐藏；本页也没有全局搜索框。

## 测试与异步任务

新增 `tests/butler/test_knowledge_template.py`（10 项）：默认模板与旧七类一致、重复分类报行号、必须保留 person/topic、目录与对话目录重名被拒、覆盖层新增目录/分类/规则真的落到 vault 骨架与索引页、`episode_dir` / `index_file` 可配置、坏覆盖层回退且只告警一次、未知 kind/type 降级、prompt 与白名单来自模板、随包模板可加载。

新增 `tests/dashboard/test_knowledge_template_view.py`（10 项）：只读不建目录、保存返回新版本、版本冲突不改文件、校验不落盘、非法内容带行号、请求体不能指定写入路径、恢复内置保留备份、缺确认头/未知动作被拒、HTTP 模板 GET/POST 与 503 门禁、facts 携带模板分类。

本次相关的 5 个测试文件（上述两个加 `test_knowledge_store.py` / `test_knowledge_extract.py` / `test_knowledge_view.py`）共 65 项全部通过。`npm.cmd --prefix web run build` 与 `npm.cmd --prefix web run smoke` 通过；smoke 现在断言 9 个导航标签，并覆盖模板页的载入、dirty、保存请求与状态反馈。

Hallmark：`KnowledgeTemplateView.vue` 静态检查 0 FAIL；真实渲染 4 个视口 0 FAIL。剩余 1 REFLEX（既有导航壳 10px 文本）与 1 WARN（既有导航 h2 渐变对比）不在本次改动范围，未扩大清理。为满足输入框边缘 3:1，`theme.css` 新增 `--line-strong` 令牌。

异步任务不变：提炼仍在 Butler 进程内的 `ExtractScheduler` 后台线程，模板只影响下一轮拼 prompt 与写入位置，不新增线程或定时器。

## 风险与回滚

风险一：模板写坏会让索引页或 prompt 异常。运行时宽松解析失败回退插件内置；页面保存前强制严格校验并给行号；内置 6 条规则不可删。

风险二：模板是提示词注入面。只用 `kind_choices()` / `type_choices()` 拼白名单字段，限长 2400 字；模板是安装者本地文件，不是外部输入。

风险三：改模板不改历史。旧分类/目录仍按原文件展示；新 kind 未知时落兜底；不重写任何已有节点，也不删除知识。

风险四：Windows 文件占用。保存走 `config_lock` + 临时文件 + `os.replace`，失败返回 503 并保留备份。

回滚：删除 `data/knowledge/template.md` 即恢复插件内置；代码回滚后模板文件被忽略，vault 不需要迁移。前端回滚时 `GET /api/knowledge/facts` 新增字段会被旧页面忽略。

[[tables/knowledge-vault]]
[[symbols/knowledge-template]]
