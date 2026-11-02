---
type: symbol
module: runtime
summary: 知识图谱模板的解析与加载——一份 Markdown 决定节点目录、事实分类、索引分区与提炼规则，覆盖层优先，坏模板回退内置
coverage: core
last_verified: '2026-11-02'
sources:
- path: src/butler/runtime/knowledge_template.py
  line: 28
  anchor: BUILTIN_TEMPLATE = REPO_ROOT
- path: src/butler/runtime/knowledge_template.py
  line: 59
  anchor: 'class TemplateError(ValueError):'
- path: src/butler/runtime/knowledge_template.py
  line: 83
  anchor: 'class GraphTemplate:'
- path: src/butler/runtime/knowledge_template.py
  line: 154
  anchor: DEFAULT_TEMPLATE = GraphTemplate(
- path: src/butler/runtime/knowledge_template.py
  line: 296
  anchor: 'def parse_template(text):'
- path: src/butler/runtime/knowledge_template.py
  line: 440
  anchor: 'def resolve_template(override=None, log=None):'
- path: src/butler/runtime/knowledge_template.py
  line: 456
  anchor: 'def load_template(override=None, log=None):'
- path: plugins/butler-wechat/knowledge/graph-template.md
  line: 21
  anchor: '## 节点目录'
changes:
- raw/changes/2026-11-02-knowledge-graph-template
calls: []
called_by:
- symbols/knowledge-extract
---
# knowledge_template

## 签名与职责

```
parse_template(text) -> GraphTemplate          # 严格；任何问题抛 TemplateError([{line, message}])
resolve_template(override=None, log=None) -> (GraphTemplate, source, path)
load_template(override=None, log=None) -> GraphTemplate   # 宽松；失败回退，绝不抛
```

模板决定四件事：新 vault 有哪些节点目录、事实分哪些类（节点小节与索引分类）、索引页怎么分区、提炼 prompt 的分类/类型说明与追加规则。它**不决定**事实行的机器可读注释——那是 `FACT_LINE` 的解析契约，改了就读不回历史事实。

## 两层来源与回退

| 优先级 | 路径 | 来源标记 | 谁写 |
|---|---|---|---|
| 1 | `data/knowledge/template.md` | `override` | 管理台「知识模板」页 |
| 2 | `plugins/butler-wechat/knowledge/graph-template.md` | `plugin` | 随插件分发，只读 |
| 3 | 代码里的 `DEFAULT_TEMPLATE`（`:154`） | `builtin` | 两层都读不到时兜底 |

覆盖层存在但解析失败时，真实生效的是插件内置模板，所以 `resolve_template` 返回的 `source` 是 `plugin`，并把覆盖层的错误原文留在页面上供修。坏模板只告警一次（按 mtime + size 缓存），不会每次写入都刷日志。

缓存键是 `(路径, mtime_ns, 大小)`：编辑保存后下一次读取自然失效，不需要重启 Butler。

## 模板结构

frontmatter 控制 `id` / `version` / `episode_dir` / `index_file` / `index_title` / `index_note` / `index_limit` / `index_days`。正文三个二级标题：

- `## 节点目录`：表格 `type | 目录 | 说明`，type 是小写 key，目录是 vault 里的文件夹名。
- `## 分类`：表格 `kind | 节点小节 | 索引分类 | 提炼指引`；节点小节与索引分类刻意分开，节点里叫「身份」、索引页叫「用户信息」。
- `## 提炼规则`：`- ` 开头的列表，追加在内置 6 条安全规则之后。

列名允许中英别名（`类型` / `目录` / `分类` / `小节` / `索引` / `指引`），但 key 必须匹配 `^[a-z][a-z0-9_]{0,31}$`。目录名不能含 `[] | # ^`、路径分隔符或控制字符，也不能与 `episode_dir` 重名。

## 约束与兜底

- 必须保留 `person` 节点类型与 `topic` 分类：`parse_facts` 与 `add_fact` 用它们做越界值的兜底。
- 上限：kind ≤ 20、节点类型 ≤ 12、规则 ≤ 20；单条指引 ≤ 120 字、单条规则 ≤ 200 字；说明与规则合计 ≤ 2400 字（`MAX_PROMPT`）；文件 ≤ 256 KB。
- 内置的 6 条安全规则（只提取用户说过的话、不推测、矛盾各记一条、助理回复不作事实来源、links 不编造、没有内容输出 `[]`）写死在 `knowledge_extract.CORE_RULES`，模板只能追加。
- 未知 kind / 节点类型在写入时降级到 `topic` / `person`；模板里被删掉的旧分类不会改写已有节点，索引页把它们归入「其他」。

## 调用方

- `KnowledgeStore.__init__`（`knowledge_store.py:315`）默认 `load_template(root / 'template.md')`，之后 `episodes_dir` / `node_path` / `index_page_path` / `add_fact` / `rebuild_index` 都读 `self.template`。见 [[tables/knowledge-vault]]。
- `knowledge_extract.build_prompt`（`:54`）与 `parse_facts` 白名单来自模板；见 [[symbols/knowledge-extract]]。
- 管理台 `KnowledgeTemplateView` 用严格解析做保存前校验；`GET /api/knowledge/facts` 的 `kinds` / `node_types` 来自 `GraphTemplate.summary()`，见 [[apis/dashboard-knowledge]]。

## 测试与风险

`tests/butler/test_knowledge_template.py` 覆盖：默认模板与旧七类一致、重复分类报行号、必须保留 person/topic、目录与对话目录重名被拒、覆盖层新增目录/分类/规则落到 vault、`episode_dir` / `index_file` 可配置、坏覆盖层回退且只告警一次、未知 kind/type 降级、prompt 与白名单来自模板、随包模板可加载。

风险：模板是提示词注入面，但只拼白名单字段并限长，且文件由安装者本地持有；模板改动不迁移历史，旧分类仍按原文件展示；共享缓存是进程内的，多个进程各自按 mtime 失效，不共享状态。

## 代码依据

- `src/butler/runtime/knowledge_template.py:28` — `BUILTIN_TEMPLATE = REPO_ROOT / 'plugins' / ...`
- `src/butler/runtime/knowledge_template.py:59` — `class TemplateError(ValueError):`
- `src/butler/runtime/knowledge_template.py:83` — `class GraphTemplate:`
- `src/butler/runtime/knowledge_template.py:154` — `DEFAULT_TEMPLATE = GraphTemplate(`
- `src/butler/runtime/knowledge_template.py:296` — `def parse_template(text):`
- `src/butler/runtime/knowledge_template.py:440` — `def resolve_template(override=None, log=None):`
- `src/butler/runtime/knowledge_template.py:456` — `def load_template(override=None, log=None):`
- `plugins/butler-wechat/knowledge/graph-template.md:21` — `## 节点目录`

[[raw/changes/2026-11-02-knowledge-graph-template]]
