```
# CLAUDE.md｜LLM Code Wiki 项目知识图谱 Schema 规范
> 本文件为 Claude Code 专用约束文档，强制遵循【LLM Code Wiki】范式。
> 核心铁则：**任何代码修改动作之前，必须先执行 Query 影响评估流程，从图谱获取改动范围、依赖链路、表信息；图谱为双向关联知识底座，源码为唯一可信源。**
> 禁止跳过图谱查询直接生成代码；禁止修改原始源码、DDL、原始接口文档；所有图谱变更、实体维护、链路更新必须遵守下面 Schema。

## 一、全局约束与行为规则
1. 可信源隔离：`/src/`（源码仓库）只读，你只能读取、解析、diff，**严禁写入、修改源码**。
2. 图谱根目录：`/code-wiki/`，所有Markdown实体、index.md、shturl 都放在这个目录。
3. 双向链路强制：所有关联关系必须双向维护。A调用B → A.depends += B，B.called_by += A；A读写Table X → A.read_write += X，X.read_by / write_by += A。单向链路属于缺陷，Lint阶段必须修复。
4. 人工备注隔离：页面内 `> 人工备注：` 区块属于人工业务经验，**自动更新时禁止覆盖、删除、修改**，仅追加新内容。
5. 废弃标记规则：实体下线/删除时，不直接删除Wiki页面，设置 `status: deprecated`，并填写 `deprecated_at`、`deprecated_reason`。
6. 索引与日志强制更新：每次 Ingest / Query归档 / Lint 修复完成，必须同步更新 `index.md` 和追加一条记录到 `shturl`。
7. 动态逻辑兜底：反射、动态SQL、动态路由、动态代理、MQ动态消费等无法静态解析的链路，自动标记 `static_analysis_uncertain: true`，并在页面备注提醒人工补全。
8. 输出优先级：需求变更先输出【影响评估报告】，经确认后，再生成代码修改方案。

## 二、目录结构约定
```

code-wiki/
├── index.md                # 全局实体索引
├── shturl.md               # 时序操作日志
├── modules/                # module 模块词条
├── files/                  # file 代码文件词条
├── apis/                   # api 接口词条（HTTP/RPC/MQ）
├── tables/                 # table 数据表 / 视图词条
├── enums/                  # enum 枚举词条
├── tasks/                  # task 定时 / 异步任务词条
├── biz_flows/              # biz_flow 业务流程词条
├── third_deps/             # third_dep 第三方依赖 / 外部服务词条
├── risks/                  # risk 历史风险、坑点、兼容问题
└── assets/                 # 附图、ER 图、时序图

```

## 三、实体类型、YAML Frontmatter 模板
> 所有页面头部必须带YAML，字段严格对齐；不存在的字段留空，不要删掉key。
> 关系字段全部填写内部链接 `[[xxx]]`

### 3.1 module｜模块/包
```yaml
---
type: module
name: ""
module_path: ""
belong_to: []
contains: []
depends: []
called_by: []
status: active # active / deprecated
last_sync: ""
static_analysis_uncertain: false
tags: []
---
# {{name}} 模块
## 概述
一句话业务描述。

## 子实体
- 包含文件：
- 包含接口：
- 包含数据表：

## 依赖说明
依赖模块：
被上游调用：

> 人工备注：
```

### 3.2 file｜代码文件（Controller / Service / Mapper / Vue 页面 / JS 等）

```
---
type: file
name: ""
file_path: ""
belong_module: []
class_or_func: []
depends: []
called_by: []
read_tables: []
write_tables: []
apis_provide: []
apis_consume: []
tasks: []
status: active
last_sync: ""
static_analysis_uncertain: false
tags: []
---
# {{name}}
## 位置
`{{file_path}}`

## 内部核心方法/类
- 类名/方法：作用简述

## 对外提供接口
- [[api/xxx]]

## 消费的接口
- [[api/xxx]]

## 读写表
读：[[table/xxx]]
写：[[table/xxx]]

## 依赖文件/模块
- [[file/xxx]]

## 调用方
- [[file/xxx]]

> 人工备注：
```

### 3.3 api｜接口（HTTP / RPC / MQ 生产消费）

```
---
type: api
name: ""
api_type: http # http / rpc / mq_produce / mq_consume / dubbo
path_or_topic: ""
method: ""
belong_module: []
provider: []
consumer: []
read_tables: []
write_tables: []
request_params: []
response_params: []
front_binding: []
status: active
deprecated_at: ""
deprecated_reason: ""
last_sync: ""
static_analysis_uncertain: false
tags: []
---
# {{name}}
## 基础信息
类型：{{api_type}}
地址/topic：{{path_or_topic}}
请求方式：{{method}}

## 入参
| 参数名 | 类型 | 是否必填 | 说明 |
|--------|------|----------|------|

## 出参
| 参数名 | 类型 | 说明 |
|--------|------|------|

## 提供方
- [[file/xxx]]

## 消费方
- [[file/xxx]]

## 读写数据表
读：
写：

## 绑定前端页面
- [[file/xxx]]

> 人工备注：
```

### 3.4 table｜数据表 / 视图

```
---
type: table
name: ""
table_comment: ""
schema: ""
engine: ""
columns: []
indexes: []
relate_table: []
read_by: []
write_by: []
status: active
last_sync: ""
static_analysis_uncertain: false
tags: []
---
# {{name}}
## 表说明
{{table_comment}}

## 字段清单
| 字段名 | 类型 | 主键 | 非空 | 业务含义 |
|--------|------|------|------|----------|

## 索引
- 索引名：字段，唯一/普通

## 关联表
- [[table/xxx]]

## 读取来源（哪些接口/文件读这张表）
- [[api/xxx]]
- [[file/xxx]]

## 写入来源（哪些接口/文件写这张表）
- [[api/xxx]]
- [[file/xxx]]

> 人工备注：
```

### 3.5 enum｜枚举

```
---
type: enum
name: ""
file_path: ""
belong_module: []
used_by: []
status: active
last_sync: ""
tags: []
---
# {{name}}
## 枚举值
| code | desc | 业务含义 |
|------|------|----------|

## 使用方
- [[file/xxx]]
- [[api/xxx]]

> 人工备注：
```

### 3.6 task｜定时任务 / 异步任务

```
---
type: task
name: ""
cron_or_trigger: ""
belong_module: []
execute_file: []
read_tables: []
write_tables: []
depends: []
status: active
last_sync: ""
tags: []
---
# {{name}}
## 触发规则
{{cron_or_trigger}}

## 执行入口
[[file/xxx]]

## 读写表
读：
写：

## 依赖接口/服务
- [[api/xxx]]

> 人工备注：
```

### 3.7 biz_flow｜业务流程

```
---
type: biz_flow
name: ""
flow_desc: ""
steps: []
relate_api: []
relate_table: []
relate_file: []
status: active
last_sync: ""
tags: []
---
# {{name}}
## 流程简述
{{flow_desc}}

## 步骤
1. 步骤1：调用 [[api/xxx]]，操作 [[table/xxx]]
2. ...

## 关联实体
接口：
表：
代码文件：

> 人工备注：
```

### 3.8 third_dep｜第三方依赖、外部服务

```
---
type: third_dep
name: ""
vendor: ""
caller: []
interface_doc: ""
status: active
last_sync: ""
tags: []
---
# {{name}}
## 说明
外部服务、SDK、第三方接口。

## 调用方
- [[file/xxx]]
- [[api/xxx]]

> 人工备注：
```

### 3.9 risk｜风险、坑点、历史兼容问题

```
---
type: risk
name: ""
risk_level: high # high / medium / low
relate_entity: []
symptom: ""
cause: ""
solution: ""
regression_point: []
status: open # open / fixed
last_sync: ""
tags: []
---
# {{name}}
## 风险等级：{{risk_level}}
## 关联实体
- [[api/xxx]]
- [[table/xxx]]

## 现象
{{symptom}}

## 根因
{{cause}}

## 处理方案
{{solution}}

## 回归检查点
-

> 人工备注：
```

## 四、三大核心流程执行规范

### 4.1 Ingest｜导入 & 增量同步图谱

触发条件：全仓扫描 / 指定模块 / 文件扫描 /git diff 增量同步 / 导入 DDL/OpenAPI
执行步骤：

1. 读取可信源（源码、SQL、openapi），AST / 静态解析识别全部实体
2. 提取元数据、签名、入参出参、读写表、调用关系
3. 新建 / 更新对应实体页面，填充 YAML 与正文
4. **双向回写所有关联关系**
5. 标记 `static_analysis_uncertain: true` 给动态逻辑
6. 更新 index.md
7. 在 shturl 追加一条 ingest 日志
8. 输出摘要：本次新增 / 更新实体数量、发现的动态无法识别点

> 
> 禁止：Ingest 阶段直接修改源码。

### 4.2 Query｜需求变更评估（最重要，改代码前必跑）

触发条件：用户给出功能需求、改动关键字、变更需求
执行步骤：

1. 读取 index.md，检索匹配相关实体，沿着双向链路递归遍历依赖、调用、读写关系
2. 收集全部关联实体，输出标准化【影响评估报告】，固定包含下面栏目：
   - 需求简述
   - ✅ 需要改动的文件、精确路径、类 / 方法位置
   - ✅ 直接影响的上下游代码、调用方、被调用方
   - ✅ 前后端交互链路：前端页面、接口、入参出参
   - ✅ 涉及数据表、字段、读写行为（读 / 增 / 改 / 删）
   - ✅ MQ、定时任务、缓存、第三方依赖
   - ✅ 历史风险、同类变更记录、兼容提醒
   - ✅ 风险等级、回归范围建议
3. 将本次评估新识别到的链路、新增风险，归档写入对应实体页面
4. 更新 index.md
5. shturl 追加 query 日志
6. 等待用户确认评估报告，**用户确认后，才允许生成代码修改方案**

> 
> 禁止：跳过评估直接写代码。

### 4.3 Lint｜图谱巡检、一致性修复

触发条件：定期巡检、版本上线前、用户手动触发
检查清单（逐条校验）：

1. 图谱记录的调用关系和源码事实不一致
2. 源码已删除，但图谱未标记 deprecated
3. 孤立实体：无入链、无出链
4. 单向引用，缺少反向关联
5. 字段注释、接口参数、读写标记缺失
6. 动态逻辑未标注 `static_analysis_uncertain: true`
7. risk 清单过期、已修复风险未更新 status
8. index.md 条目缺失、链接失效

执行步骤：

1. 对比源码可信源，批量检出问题
2. 输出巡检报告，区分【自动修复】和【需要人工确认】项
3. 自动修复安全项，更新实体页面、双向链路
4. 需要人工确认的问题，列出清单交给用户
5. 更新 index.md
6. shturl 追加 lint 日志

## 五、index.md 格式规范

```
# 实体总索引
> 自动维护，不要手动大量修改

## module 模块
- [[modules/xxx]] | 简述 | 最后同步：xxx | 状态：active

## file 文件
- [[files/xxx]] | 简述 | module:[[modules/xxx]] | 状态：active

## api 接口
- [[apis/xxx]] | 简述 | type:http | 状态：active

## table 数据表
- [[tables/xxx]] | 简述 | schema:xxx | 状态：active

## enum 枚举
- [[enums/xxx]]

## task 任务
- [[tasks/xxx]]

## biz_flow 业务流程
- [[biz_flows/xxx]]

## third_deps 第三方依赖
- [[third_deps/xxx]]

## risk 风险清单
- [[risks/xxx]] | level:high
```

## 六、shturl 日志格式规范

每条日志固定模板，追加式，不修改历史行

```
## [YYYY-MM-DD HH:MM:SS] ingest | 描述：xxx，新增：x，更新：x
## [YYYY-MM-DD HH:MM:SS] query | 需求：xxx，评估影响实体：xxx
## [YYYY-MM-DD HH:MM:SS] lint | 巡检：全量，自动修复：x，待人工确认：x
## [YYYY-MM-DD HH:MM:SS] manual | 人工修正：xxx
```

## 七、标签 tag 推荐（统一标签体系）

`#high-risk` `#legacy` `#cache-related` `#mq` `#rpc` `#front` `#back` `#deprecated` `#dynamic-sql` `#reflection`

## 八、禁止行为清单

- ❌ 跳过 Query 评估直接生成代码
- ❌ 修改原始源码、DDL、原始接口文档
- ❌ 覆盖人工备注区块
- ❌ 只维护单向链路
- ❌ 删除已经下线的实体页面，只允许标记 deprecated
- ❌ 把密钥、敏感业务数据写入图谱