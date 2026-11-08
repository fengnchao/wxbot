# 联系人身份与业务工具

窗口名、群昵称和头像是身份观察；服务端解析联系人并签发本轮工具上下文。每次执行复核能力、有效期和现行策略，提示词与 API Key 不能授予业务权限。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 使用说明

- [wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / identity/ —— 联系人身份](#doc-43f53b95c0c803) · `README.md`
- [wxbot / Butler / 管理台 / 联系人管理规则](#doc-979c90a4e6a946) · `README.md`

<a id="doc-43f53b95c0c803"></a>

### wxbot / Butler / 模块与文件职责 / src/butler —— 编排层 / identity/ —— 联系人身份

来源：`README.md:190`。

###### identity/ —— 联系人身份

| 文件 | 职责 |
|---|---|
| `identity/contacts.py` | 联系人映射：微信聊天窗口标题 → Hermes Profile / uid / 会话键 |
| `identity/contact_store.py` | 权威的本地会话与联系人设置，归 Butler 所有 |
| `identity/contact_identity.py` | 事务内的「同一个人」匹配，成员关系证据留在绑定上 |
| `identity/contact_admin.py` | 面向业务的统一联系人管理；路径只从服务端配置来 |
| `identity/contact_migration.py` | 从旧联系人来源到单一业务库的显式离线切换（预览 + 迁移） |
| `identity/user_registry.py` | 管理员持有的身份与知识库归属；头像哈希是证据不是 ID |
| `identity/user_api.py` | 带类型的运维操作，调用方必须先通过服务 token |
| `identity/directory.py` | Butler 自己的本地通道目录；不授予身份或工具权限 |
| `identity/groups.py` | 用户分组（订阅字典）：`messageType` → 绑定的联系人 |
| `identity/group_context.py` | 公开群观察、有界的请求快照和按线程的游标 |
<!-- end-migrated-part: doc-43f53b95c0c803 -->

<a id="doc-979c90a4e6a946"></a>

### wxbot / Butler / 管理台 / 联系人管理规则

来源：`README.md:678`。

##### 联系人管理规则

- 人物显示名、微信窗口名称、群成员昵称分别维护。“微信窗口名称”用于在微信主窗口定位聊天，不是真实微信账号。
- 修改人物姓名或群昵称不会合并人物；不同人物在同一群可以重名，管理页面保留各自入口。仅有群身份无需创建私聊。
- 角色与允许功能显示最终配置及来源；会话单独设置优先于联系人默认设置，明确取消继承的会话不会误显示默认角色。
- 联系人可手动新增。统一联系人模式下，Butler 处理已采集的私聊新消息时会补建缺失的私聊窗口，群聊归档也会补建群窗口。删除后再次收到消息可重新建档，窗口标记为待补充，按现行监听范围采集。补建保留已有窗口和停用状态，新增窗口的单独监听、订阅和技能授权需管理员设置。
- 在「联系人 → AI 设置」的允许功能中管理 IndexTTS 授权。在「基本资料 → 编辑窗口与收发设置」可管理语音发送模式和本地自动回复音色。
- 主动消息按窗口维护订阅和自动问候，显示发送目标与运行记录；手动触发会先明确确认可能发送消息。
- 移除一条成员身份只清除该绑定及识别证据，最后一条被移除后也保留人物和窗口。“删除联系人”会清理该人物的全部身份、私聊窗口和头像，操作不可撤销；知识库里的 Markdown 文件不跟着删。
- 联系人详情头部直接提供“删除联系人”，群聊详情提供“移除群聊”，所有详情分区均可使用，执行前保留原有确认提示。
- 身份关联和合并统一先读取 `GET /api/contacts/merge-preview?source_id=...&target_id=...`。返回双方身份、窗口、默认策略、`version` 和 `preview_version`；联系人写动作 `merge`（以及兼容的 `link_binding`）必须提交对应的 `preview_version`。提交前事务内重算版本摘要；绑定或配置变化返回 409，需重新预览。
- 同名和相似头像仅作为管理候选；新增窗口/群身份不会隐式合并现有人物。旧管理员用户接口的 `create` 不复用同名人物，统一模式下旧 `link` 请改用上述合并预览流程。微信自动观察识别算法不在本轮重构范围内。
- 未命名空档案清理移至身份管理下的全局维护工具，展示服务端 `can_cleanup` 候选；`person_cleanup` 必须带明确的 `ids` 列表（最多 1000）。服务器在事务中再次排除带窗口、已确认身份或身份重定向的档案。
- 本轮无数据库迁移。后端改动由使用者手动重启 Butler 和管理台后加载；前端 `web/dist` 已构建，刷新页面加载。无需为本轮改动重启 wxbot。

前端纯规则回归可运行 `cd web` 后的 `node --test scripts/contactPresentation.test.mjs`；页面交互仍通过 `npm run build` 与 `npm run smoke` 校验，全部使用假数据。
<!-- end-migrated-part: doc-979c90a4e6a946 -->

## 技术资料

- [联系人策略保存](#doc-fdc456753803cc) · `llm wiki/wxbot/apis/dashboard-contact-policy.md`
- [群成员身份：昵称优先，头像退为证据](#doc-82631ed77ef07a) · `llm wiki/wxbot/concepts/group-identity-evidence.md`
- [观察证据与身份权限](#doc-8dc39a23945b37) · `llm wiki/wxbot/concepts/identity-authority.md`
- [联系人身份与权限](#doc-5e308350a1ba25) · `llm wiki/wxbot/modules/identity.md`

<a id="doc-fdc456753803cc"></a>

### 联系人策略保存

来源：`llm wiki/wxbot/apis/dashboard-contact-policy.md:1`。

```yaml
type: api
module: identity
summary: 联系人策略事务外校验、并发版本复查及未安装技能显式取消
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/identity/contact_admin.py
  line: 345
  anchor: 'def save(self, payload):'
- path: src/butler/identity/contact_admin.py
  line: 384
  anchor: validated_policy = None
- path: src/butler/identity/contact_admin.py
  line: 508
  anchor: "elif action in {'binding','binding_enable','binding_disable'}:"
- path: web/src/views/ContactsView.vue
  line: 270
  anchor: async function enableBinding(member)
- path: src/dashboard/http.py
  line: 168
  anchor: 'def _contact_admin(self):'
- path: src/dashboard/api/contacts.py
  line: 29
  anchor: 'def save(ctx):'
- path: src/butler/identity/contact_store.py
  line: 27
  anchor: 'def clean_policy(value):'
- path: web/src/components/ContactDialog.vue
  line: 268
  anchor: 'function submitPolicy()'
- path: web/src/components/ContactDialog.vue
  line: 414
  anchor: 'v-for="name in unavailableSkills"'
changes:
- raw/changes/2026-11-05-contact-policy-save
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-05-enable-group-binding
depends_on:
- modules/identity
- modules/dashboard
- modules/web
```
### 联系人策略保存

#### 方法、路径与鉴权

POST /api/contacts 由 dashboard.api.contacts.save 接收（src/dashboard/api/contacts.py:29），仍要求可信本机同源、JSON 和 X-Wxbot-Contact-Action。属于 [modules/dashboard](dashboard.md#doc-bb47c9474691fe) 与 [modules/identity](identity-tools.md#doc-5e308350a1ba25) 的管理操作，不是模型凭提示授予权限。

#### 请求字段与响应

策略写入使用 action=person 或 conversation、id、整数 version、policy。policy 为 null（清除覆盖）或包含 role_skill、allowed_skills、heartbeat_enabled 的对象；结构与规范化来自 src/butler/identity/contact_store.py:27 clean_policy。角色必须属于当前安装目录的角色，技能必须是已安装工具；未知名称仍拒绝，并在错误中列出具体名字（src/dashboard/http.py:168）。没有新增字段或放宽授权。

成功返回完整联系人快照供前端替换；非法输入 400，版本冲突 409，表单保留错误供使用者处理（src/dashboard/api/contacts.py:29、web/src/contactState.js:132 submitDialog 与 :143 contactSave）。

#### 实现链与锁边界

ContactDialog.submitPolicy → contactSave → POST /api/contacts → ContactAdmin.save。save 先用只读快照检查目标、版本并确定校验路由，关闭连接后调用目录验证器；然后开始写事务，重新读取并比较 version，再应用策略（src/butler/identity/contact_admin.py:384）。人物默认策略与会话覆盖使用同一边界；会话改名/profile 等仍用请求更新后的路由验证，心跳目的地约束仍在事务内检查。

目录验证会经 dashboard 的配置读取再次访问 DirectoryStore → ContactStore；原实现把验证放在 BEGIN IMMEDIATE 内，第二条连接再次申请写锁，导致超时回滚。事务外验证消除这条自锁链；验证期间其他保存若提交，新写事务必须报版本冲突，不能覆盖较新数据。

#### 数据血缘

人物策略写 unified_contacts.payload.person_policies[id]；会话策略写 conversations[].policy；version 提交时增长（contact_store.py:122 _save）。无新表、字段或迁移。运行时工具仍由 SkillPolicyStore/ToolService 验证，不根据 UI 勾选直接执行。

#### 前端与已有未安装技能

属于 [modules/web](dashboard.md#doc-aeec90dfe23cd3)，复用既有布局和 user-skill 原生复选框。技能目录加载后保留已有 allowed_skills，把目录里缺失的名字显示为“未安装”（ContactDialog.vue:117、:414）。默认不取消、不静默删除；使用者明确取消勾选后才从提交数组移除。保存按钮等待回执时显示“保存中…”，成功才关闭；重新打开从返回快照加载新策略。语音能力由 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) 与 [apis/dashboard-voice-assets](delivery-voice.md#doc-d265cc1e47a521) 说明。

#### 测试与风险

tests/dashboard/test_contact_admin.py 的人物/会话同库目录验证回归在修复前均以 database is locked 失败，修复后可持久化并重新读取；并发保存回归保证旧请求冲突而非覆盖。现有非法目录、同源、版本和原子回滚测试继续执行。web/scripts/smoke.mjs 覆盖未安装技能保留、显式取消、保存等待和重新打开。

无消息发送、定时任务或后台消费者变更。需使用者自行重启管理台加载后端，刷新前端加载 dist；不自动重启服务，不改生产策略。回滚对应源码与 dist，无数据回滚或迁移。

来源 [raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)。

#### 本次核对

会话弹窗的独立 IndexTTS 控件已退场，授权统一由 AI 设置消费现有策略保存契约。 来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 单条群身份启用

POST /api/contacts 的 `binding_enable` 沿用 `id`、`binding_id`、`version`、同源确认与完整快照。写事务中核对归属和 `channel_type=group`，仅启用 `user_bindings` 的目标行、推进版本，并在 `user_audit` 记录 `enabled` 动作。群身份确认与窗口策略独立管理。消费与数据边界见 [modules/web](dashboard.md#doc-aeec90dfe23cd3)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)，来源 [raw/changes/2026-11-05-enable-group-binding](identity-tools.md#doc-6f2fac571f1610)。
<!-- end-migrated-part: doc-fdc456753803cc -->

<a id="doc-82631ed77ef07a"></a>

### 群成员身份：昵称优先，头像退为证据

来源：`llm wiki/wxbot/concepts/group-identity-evidence.md:1`。

```yaml
type: concept
module: identity
summary: 群成员先按同群 member_key 与昵称认人，头像 dhash 只作证据且不足以区分个体
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/butler/identity/user_registry.py
  line: 375
  anchor: def observe(
- path: src/butler/identity/user_registry.py
  line: 239
  anchor: def _learn_nickname(
- path: src/wxbot/inbox.py
  line: 120
  anchor: def sync_users(
- path: src/wxbot/inbox.py
  line: 23
  anchor: def member_nickname(
- path: src/wxbot/queue_store.py
  line: 192
  anchor: def identity_observations(
- path: src/common/avatar_identity.py
  line: 57
  anchor: def avatar_is_informative(
- path: src/wxbot/wechat/chat_window.py
  line: 252
  anchor: def _runtime_avatar(
- path: src/wxbot/wechat/main_window.py
  line: 29
  anchor: 'def plausible_nickname(name: str) -> bool:'
changes:
- raw/changes/2026-11-03-feat-voice-003-voice-assets
- raw/changes/2026-11-03-feat-voice-001-anchor-refresh
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-10-31-identity-placeholder-names
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-01-citation-sweep
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-residue-reverify
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-05-group-auto-voice
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
```
### 群成员身份：昵称优先，头像退为证据

#### 业务规则

群成员认人的顺序是「已登记的 `member_key` → 同群昵称 → 新建」。头像只用来补证据和展示，不参与判定是不是同一个人。档案已存在时，群目录后来学到的昵称会补上（`_learn_nickname`），不再让它永远停在 `待命名-`；管理员确认过的昵称不会被群昵称覆盖。

#### 输入到输出

`POST /api/users/observe` 仍只收 `member_key` / `member_name` / `avatar`。空白的 `avatar` 会被丢弃，`member_name` 缺失只更新证据、不新建带名字的档案；同群出现同名且只有一条既有档案时，把新的 `member_key` 并到那条档案的别名里。

#### 实测边界

同一人不同次截图的 dhash 距离 10~35，不同人之间 23~32，两者重叠，**dhash 无法区分同一个人和不同的人**；`_avatar_score` 的距离 ≤ 4 实际等价于「只认同一张截图」。亮度标准差和比特位数同样重叠（坏图 28~29 位、正常图 19~33 位）。因此颜色数是唯一可用判据：窗口被遮挡时截到的纯色块只有 1 种颜色，真实的纯色块图形头像有十几种颜色，按色彩丰富度过滤会误杀真实头像。

wxbot 启动时 `sync_users` 会重放 `inbox` 里的头像证据，这是「每次启动多几条待命名」的来源。重放只用于补证据，因此空白头像和没有昵称的群成员观测都不重放：它们建不出能核对的人，真正的资料等这个人下次发言再补。截图读不出真名时会写下 `成员-<ID前8位>` 占位名，它和空名字等价，不能当昵称上送。

#### 已知取舍

同群两个人用完全相同的昵称会被并成一条，接受这个取舍：现有头像证据本来就没有区分度，靠相似度防误并只会让重复继续增长。

昵称来自消息预览时另受 `preview_sender` 的格式约束（`src/wxbot/wechat/main_window.py:45`）：长度超过 16（微信昵称上限）、含换行或句读、以 `[` 开头、以「你/我」开头且含空白的整句都不当昵称（`plausible_nickname`，`src/wxbot/wechat/main_window.py:29`）。这条约束是 2026-11-01 补的：此前「你收到一笔群分红 请在手机上查看」这类卡片文案被学成成员昵称，进而成为 `mention_name`，让 @ 永远选不中候选。人工在管理台确认的昵称不受此约束。

#### 代码依据

- `src/butler/identity/user_registry.py:350` — `def observe(`
- `src/butler/identity/user_registry.py:239` — `def _learn_nickname(`
- `src/wxbot/inbox.py:120` — `def sync_users(`
- `src/wxbot/inbox.py:23` — `def member_nickname(`
- `src/wxbot/queue_store.py:192` — `def identity_observations(`
- `src/common/avatar_identity.py:57` — `def avatar_is_informative(`
- `src/wxbot/wechat/chat_window.py:252` — `def _runtime_avatar(`
- `src/wxbot/wechat/main_window.py:29` — `def plausible_nickname(name: str) -> bool:`
- `src/wxbot/wechat/main_window.py:45` — `def preview_sender(preview: str, text: str) -> str | None:`

#### 入库来源

[raw/changes/2026-10-31-group-identity-nickname](identity-tools.md#doc-f39c15a6fe0885)

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[raw/changes/2026-11-01-citation-sweep](wxbot.md#doc-4d0e5fc0ed39d9)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-mention-residue-reverify](wechat-ui.md#doc-989f2003dec3a1)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 群聊采集与自动语音复核（2026-11-05）

采集前的越屏恢复和 row_offscreen 显式拒绝见 [concepts/capture-viewport](wechat-ui.md#doc-62362beb7f9b66)；不放宽 gutter 阈值，不推进未知发送方快照。语音准备期间继续采集，恢复录音任务后本轮不再切换收件会话，见 [concepts/automatic-voice-reply](delivery-voice.md#doc-070a8b5f81ad00)。来源 [raw/changes/2026-11-05-group-auto-voice](delivery-voice.md#doc-264d648c9acbbe)。

#### 本次核对

群归档新增缺失群窗口登记，群成员昵称与身份匹配的规则沿用。 来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。
<!-- end-migrated-part: doc-82631ed77ef07a -->

<a id="doc-8dc39a23945b37"></a>

### 观察证据与身份权限

来源：`llm wiki/wxbot/concepts/identity-authority.md:1`。

```yaml
type: concept
module: identity
summary: 窗口/头像/昵称是证据，服务签发上下文才是工具授权边界
coverage: core
last_verified: '2026-11-04'
sources:
- path: src/butler/agent/tools.py
  line: 47
  anchor: def issue(
- path: src/butler/agent/tools.py
  line: 55
  anchor: def verify(
- path: src/butler/agent/tools.py
  line: 89
  anchor: def call(
- path: src/wxbot/queue_store.py
  line: 361
  anchor: member_name = str(mention_name or '').strip()
changes:
- raw/changes/2026-11-03-feat-voice-001-anchor-refresh
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-details-whitelist-reverify
- raw/changes/2026-11-02-mention-residue-reverify
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
```
### 观察证据与身份权限

#### 业务规则

[modules/identity](identity-tools.md#doc-5e308350a1ba25) 解析人物、绑定和记忆归属；ToolService 的 issue / verify / call 对服务签发身份、时效与权限进行校验。模型提示、运行时 Skill 分类、联系人同名和头像相似均不授予工具权限。

头像只是证据，不是权限：遮挡窗口截到的纯色块（颜色数不超过 `BLANK_AVATAR_COLORS`）会被丢弃，不进入档案；群成员靠 member_key 与昵称认人，见 [concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)。

#### 输入到输出

[apis/butler-handle](butler.md#doc-4f70359e7ae440) 的 member_key/member_name/avatar 是来自 [modules/wxbot](wxbot.md#doc-8508032cbe5131) 的观察；[symbols/butler-handle](butler.md#doc-eba67ca6f97d80) 解析后才提供身份相关 meta。[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1) 仅使用服务给出的 mention_name 给第一分句设置 @；不能用模型文本/本地猜测替换收件身份。2026-11-02 复核：`queue_store.py` 只扩展了投递事件细节白名单，`member_name` 只取服务给出的 mention_name 这一条未变。

#### 开发与运行边界

[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd) 使用同一能力边界；生成参数不含身份、目标、URL 或路径。只读能力仅列预设，耗时生成后再次 verify（含动态策略撤销）。operations 按 owner/request/call_id 绑定指纹，并登记同内容别名；最终状态同步更新别名，投递未知不重复发送。

[modules/plugin](resident-skills.md#doc-709338d3e083eb) 的角色/工具 Markdown 是运行资产，[modules/wiki](wxbot.md#doc-ed5d88ddcd1b47) 是开发知识，不作为运行时权限来源。不能因图谱写着“允许”就绕过业务校验。详细身份表与管理端合并契约仍在 [coverage](wxbot.md#doc-3d945de7c38143) 待建档清单。

#### 代码依据

- `src/butler/agent/tools.py:47` — `def issue(`
- `src/butler/agent/tools.py:55` — `def verify(`
- `src/butler/agent/tools.py:89` — `def call(`
- `src/wxbot/queue_store.py:361` — `member_name = str(mention_name or '').strip()`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)

[raw/changes/2026-11-01-mention-fallback-unread-retry](wechat-ui.md#doc-a5d65ee79e182a)

[raw/changes/2026-11-02-ui-snapshot-ref-contract](delivery-pump.md#doc-5688ce5c14b7b6)

[raw/changes/2026-11-02-details-whitelist-reverify](delivery-pump.md#doc-ae7b71a2b37518)

[raw/changes/2026-11-02-mention-residue-reverify](wechat-ui.md#doc-989f2003dec3a1)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。
<!-- end-migrated-part: doc-8dc39a23945b37 -->

<a id="doc-5e308350a1ba25"></a>

### 联系人身份与权限

来源：`llm wiki/wxbot/modules/identity.md:1`。

```yaml
type: module
module: identity
summary: 统一人物、窗口和成员绑定，身份能力由服务端签发
coverage: overview
last_verified: '2026-11-05'
sources:
- path: src/butler/identity/user_registry.py
  line: 350
  anchor: def enroll_conversation(
- path: src/butler/identity/contact_store.py
  line: 37
  anchor: 'class ContactStore:'
- path: src/butler/identity/user_registry.py
  line: 24
  anchor: 'class UserRegistry:'
- path: src/butler/agent/tools.py
  line: 47
  anchor: def issue(
- path: src/butler/agent/tools.py
  line: 55
  anchor: def verify(
- path: src/butler/identity/user_registry.py
  line: 375
  anchor: def observe(
- path: src/butler/identity/user_registry.py
  line: 239
  anchor: def _learn_nickname(
- path: src/butler/identity/contact_admin.py
  line: 345
  anchor: 'def save(self, payload):'
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-policy-save
- raw/changes/2026-11-05-contact-enrollment-and-tts-ui
- raw/changes/2026-11-05-enable-group-binding
```
### 联系人身份与权限

#### 范围

`src/butler/identity/` 维护窗口联系人、统一人物、绑定与记忆归属；ContactStore 使用配置确定的业务库，UserRegistry 完成人物/绑定身份解析。

#### 权限及关联

属于 [modules/butler](butler.md#doc-38393df7a7b4da)。ToolService.issue / verify 处理服务签发上下文，模型提示和同名/头像观察都不能授予工具权限。见 [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。

#### 群成员认人顺序

群成员按「已登记 member_key → 同群昵称 → 新建」认人，头像只补证据和展示。群目录后来学到的昵称会补到待命名档案上，管理员确认过的名字不被覆盖；同群同名且唯一时会并回既有档案。实测 dhash 无法区分同一个人和不同的人，不能用头像相似度防误并。规则与实测数据见 [concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)。

#### 新消息补建窗口

已登记人物与已登记窗口分别来自 user_profiles/user_bindings 和 unified_contacts.payload.conversations。Butler 正常处理新消息或归档群消息时调用 UserRegistry.enroll_conversation。它在业务事务内检查窗口名、活跃模式与私聊启用绑定，补建待补充的窗口，既有窗口和策略保留。历史身份同步只登记证据。消费点见 [modules/web](dashboard.md#doc-aeec90dfe23cd3)，入站链路见 [concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)。来源 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。

#### 群身份开关

停用记录可通过 [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc) 的单绑定动作恢复，更新 `user_bindings.enabled`，并保留身份确认标记、昵称、识别证据与会话设置。来源 [raw/changes/2026-11-05-enable-group-binding](identity-tools.md#doc-6f2fac571f1610)。

#### 待建档

完整业务表、合并预览/版本摘要契约、用户 API/管理台消费点尚未在本批逐项建立；修改这些功能必须先查源码扩展，不能从概览推断字段。

#### 代码依据

- `src/butler/identity/contact_store.py:37` — `class ContactStore:`
- `src/butler/identity/user_registry.py:24` — `class UserRegistry:`
- `src/butler/agent/tools.py:47` — `def issue(`
- `src/butler/agent/tools.py:55` — `def verify(`
- `src/butler/identity/user_registry.py:375` — `def observe(`
- `src/butler/identity/user_registry.py:239` — `def _learn_nickname(`

#### 入库来源

[raw/changes/2026-10-31-knowledge-graph-bootstrap](wxbot.md#doc-f0c0814f02ebe4)


#### 本次核对

[raw/changes/2026-11-04-index-tts-skill](index-tts.md#doc-a62e0514c7634a)：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)，其余已述契约未改。


#### 联系人语音配置核对

[raw/changes/2026-11-04-webui-preset-binding](index-tts.md#doc-14cc58d084986d)：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)。


图谱契约说明来源：[raw/changes/2026-11-04-webui-preset-graph-note](index-tts.md#doc-a877b64be56f43)。


#### 策略保存复核（2026-11-05）

联系人策略保存的事务外目录校验、事务内版本复查及未安装技能的显式取消入口见 [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)。保留原角色与工具权限规则，无数据库迁移，不自动删除已有技能引用。来源 [raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)。
<!-- end-migrated-part: doc-5e308350a1ba25 -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [群成员身份改用昵称优先，头像退为证据](#doc-fbe924ce9641ad) · `llm wiki/wxbot/impacts/2026-10-31-group-identity-nickname.md`
- [新消息补建会话与移除会话 IndexTTS 专区](#doc-98f596dd5f8d22) · `llm wiki/wxbot/impacts/2026-11-05-contact-enrollment-and-tts-ui.md`
- [联系人策略保存超时影响分析与实施计划](#doc-62206a40735cb5) · `llm wiki/wxbot/impacts/2026-11-05-contact-policy-save.md`
- [启用停用的群成员身份](#doc-b934820de6d35e) · `llm wiki/wxbot/impacts/2026-11-05-enable-group-binding.md`
- [群成员身份改用昵称优先，头像只作证据](#doc-f39c15a6fe0885) · `llm wiki/wxbot/raw/changes/2026-10-31-group-identity-nickname.md`
- [截图占位名不再当作群昵称重放](#doc-f3232d3cef51df) · `llm wiki/wxbot/raw/changes/2026-10-31-identity-placeholder-names.md`
- [修改记录](#doc-f267229129f9a4) · `llm wiki/wxbot/raw/changes/2026-11-05-contact-enrollment-and-tts-ui.md`
- [修复联系人策略保存锁等待与不可见旧技能](#doc-ef8af1106d1713) · `llm wiki/wxbot/raw/changes/2026-11-05-contact-policy-save.md`
- [修改记录](#doc-6f2fac571f1610) · `llm wiki/wxbot/raw/changes/2026-11-05-enable-group-binding.md`

<a id="doc-fbe924ce9641ad"></a>

### 群成员身份改用昵称优先，头像退为证据

来源：`llm wiki/wxbot/impacts/2026-10-31-group-identity-nickname.md:1`。

```yaml
type: impact
status: done
date: '2026-10-31'
```
### 群成员身份改用昵称优先，头像退为证据

目标：启动时不再自动冒出新「待命名-」档案，同一个人不因头像像素抖动被拆成多条。

#### 查询与覆盖

已查询关键词“群成员身份/头像/昵称/member_key/观测”，图谱未命中；[modules/butler](butler.md#doc-38393df7a7b4da) 只覆盖联系人档案的对外行为，`wxbot` 侧的观测采集与重放无词条。本次按源码补报告，并新建词条。

#### 现象与证据

真实库 `data/business.sqlite3` 实测：5 条 `待命名-*` 全部 `channel_type=group`、`identity_confirmed=0`，创建时间集中在同一秒；`user_audit` 显示 20:41 手动删除 4 条后，20:43 用**完全相同的 member_key** 又建回来。

`data/cache/wxbot_queue.sqlite3` 的 `inbox` 表里，只有 `0000000000000000` 是空白截图：解码后 1 种颜色，正是 `normalize_avatar` 的兜底填充色 `#1F1F1F`。另外 4 条都是**真实头像**——18~19 色的那三条是纯色块图形头像（亮度标准差 49.7/59.0/56.6，与正常头像 34.9~78.4 完全重叠，不是坏图）。

主因不是坏图，是**昵称没传到**：`178c1373d18dadec` 在 wxbot 侧已映射到「挽风」，butler 却建了 `待命名-178c1373d18d`；`a6a65012cd323637` 对应「我干嘛」同样没有传过去；剩下的 `2425da15c8313767`、`2425da3489763652` 群目录里确实没有名字。

同一个人不同次截图的 dhash 距离实测 10~35，不同人之间 23~32，**没有区分度**；现有 `_avatar_score` 要求距离 ≤ 4，等价于「只认同一张截图」。

#### 根因

1. `src/wxbot/inbox.py:99` 启动时 `sync_users()` 把 `inbox` 表里每个 `(会话, member_key)` 的最新一条带头像记录重新上送 butler（`queue_store.py:192-199`，只增不减）。删除档案后证据仍在，下次启动必然重建。
2. `inbox` 里存的是入库那一刻的昵称快照，之后 `DirectoryStore` 学到映射也不回填；`sync_users()` 直接读快照，于是上送昵称为空 → `named=False` → 新建 `待命名-<hash>`。
3. `src/wxbot/wechat/chat_window.py:236` 只用 `1 < bit_count < 63` 挡纯黑纯白，挡不住遮挡时截到的纯色块，坏图因此进入 `inbox` 并永久重放。
4. `src/butler/identity/user_registry.py:355` 只把头像 hash 当身份标识；hash 一变即新建，名字撞车再拼 `（uuid前12位）`。
5. `src/butler/identity/contact_admin.py:296` 取头像只认 `identity_confirmed=1`，待命名档案永远拿不到头像。
6. 重放没有语义过滤：没有昵称、也没有既有档案的观测也会被建成新身份，所以删掉之后下次启动必然再冒出一条。
7. 快照重放读的是截图原始行，截图读不出真名时写的是 `成员-<ID前8位>` 占位名。它是非空字符串，能绕过“无名不重放”的守卫，butler 端的 `normalize_name` 又会把它判成无名——结果照样新建 `待命名-`。这一条是清完旧数据后仍会冒新条目的最后一个缺口。

#### 文件、调用与边界

- `src/common/avatar_identity.py:57`：新增 `avatar_is_informative`，只拒绝颜色数不超过 `BLANK_AVATAR_COLORS`（=2）的纯色块。第一版用颜色数 ≥64 作判据，测试实测发现会误杀 3 色的图形头像，已纠正；亮度标准差与比特位数实测同样无区分度，不能改用。
- `src/wxbot/wechat/chat_window.py:236` `_runtime_avatar`：源头拒绝空白块。
- `src/wxbot/queue_store.py:192` `identity_observations`：只取有头像的证据，不再用 base64 长度做启发式判据，图片质量只由 `avatar_is_informative` 一处决定。
- `src/wxbot/inbox.py:109` `sync_users`：丢弃空白头像；昵称取群目录当前映射而不是入库快照；没有昵称的群成员观测不重放。
- `src/wxbot/inbox.py:23` 新增 `member_nickname`：把 `成员-<ID前8位>` 占位名等同于无名。`_capture` 与启动重放共用这一处判断，避免两边口径不一。
- `src/butler/identity/user_registry.py:355` `observe`：空白头像置空；已存在档案学到群昵称时补名字；新 key 命中同群同名且唯一时并回原档案。新增 `_learn_nickname`，不覆盖管理员确认过的昵称。
- 不改 `_avatar_score` 的严格阈值，也不让头像相似度参与身份合并。

#### 验证

`tests/butler/identity` + `tests/unit/wxbot` 共 298 项全过，含新增用例：空白块拒绝、3 色图形头像保留、归一化后空白块仍为空、启动重放跳过无名观测、启动重放不把截图占位名当昵称。全套 `tests` 剩 3 条与本改动无关的旧失败（队列状态机 `_recompute_batch` 与输入时序）。

真实数据仿真：把 `business.sqlite3` 与 `wxbot_queue.sqlite3` 复制到临时目录，用真实 `MainInbox.sync_users` + `UserRegistry.observe` 跑完整重放，`user_profiles` 23→23、`user_bindings` 13→13，零新建。第一版仿真拿 `user_bindings.nickname` 当昵称来源，不是真实链路（真实来源是 `unified_contacts.aliases`），因此误报了两个新建，记录在此避免重犯。

#### 接口与数据

`POST /api/users/observe` 字段不变（`member_key`/`member_name`/`avatar`），只是 `avatar` 可能为空、`member_name` 更完整。`GET /api/contacts` 的 `avatar` 字段语义不变，昵称补全后头像自然出现。

业务表结构不变；只新增 `user_audit` 动作 `nickname_learned` 与 `avatar_alias`。

#### 风险与回滚

- 同群同名的两个人会被并成一条：接受。头像 dhash 实测无法区分同一个人和不同人，用相似度防误并只会让真实重复继续增长。同名冲突已有 `ambiguous` 语义保护。
- 管理员手工确认过的昵称不被群昵称覆盖。
- 回滚：撤销上述 6 处改动即可；数据库只多出审计行，无结构变更。
- 已授权清理完成：`user_profiles` 28→23，删掉 5 条无名字的 `待命名-*`；`inbox` 里那条空白证据（`0000000000000000`，正文保留）只清空 `avatar` 字段。保留 2 条 `display_name` 仍为 `待命名-` 开头的档案，它们分别对应「我」与「老登看剑」，`identity_confirmed=1` 且界面已按昵称展示，属于有效档案而非脏数据。
- 清理前的备份在 `data/backups/identity-cleanup-20261031T130450Z/`。
<!-- end-migrated-part: doc-fbe924ce9641ad -->

<a id="doc-98f596dd5f8d22"></a>

### 新消息补建会话与移除会话 IndexTTS 专区

来源：`llm wiki/wxbot/impacts/2026-11-05-contact-enrollment-and-tts-ui.md:1`。

```yaml
type: impact
status: completed
date: 2026-11-05
```
### 新消息补建会话与移除会话 IndexTTS 专区

#### 需求关键词与图谱命中

查询 contact_store、contact_admin、IndexTTS、dashboard-contact-policy，核对 [modules/identity](identity-tools.md#doc-5e308350a1ba25)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc)、[apis/index-tts](index-tts.md#doc-fdc576d6ee7fbd)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)。图谱缺少自动身份登记和窗口管理投影的区别。`user_registry.py:275` 私聊观察只创建人物/绑定，`contact_admin.py:294` 从 `conversations` 投影窗口，`contactPresentation.js:26` 据此筛选私聊。只有私聊绑定的记录甚至可能没有前端待确认原因。

#### 要改的文件、符号与调用方

- `src/butler/agent/core.py:181,273`：群聊归档（含静默批次）及正常处理入站消息时补建，沿用身份解析结果。启动快照走 `observe_users`，心跳走 `heartbeat_contact`，两者不补建窗口。专用 HTTP 转发继续绕开身份流程。
- `src/butler/identity/user_registry.py:350` 附近：同一业务库事务内检查已存在窗口和启用的私聊绑定，复用 `src/butler/identity/contact_store.py:122` 提交。
- `web/src/components/ContactDialog.vue:155,317,477`、`web/src/views/ContactsView.vue:152`、`web/src/styles/contacts.css:28`：移除会话专用授权和预设区及其请求，保留 AI 设置与语音回复控件，按 Hallmark 的现有管理台局部修改范围处理。

#### 接口、字段与风险

HTTP 请求和响应格式保持兼容。现有 `GET /api/contacts` 返回补建后的会话。`unified_contacts.payload.conversations` 使用实际窗口名称、默认路由字段、私聊 `person_id` 与 `needs_route` 标记。复用业务库的版本控制，无迁移，不写手工监听、订阅或技能授权。原 `GET/POST /api/tts-presets` 与保存的预设继续供已有运行时使用，重命名会话时本弹窗不再复制旧名称的网页预设。已有本地音色资产保存与改名仍走原接口。

#### 验证、异步任务与回滚

在临时库验证删除、重收、幂等、停用、群聊静默归档；用管理台假数据验证无预设请求且普通语音设置仍可保存。沿用现有队列，不新增后台任务。回滚源码和 dist 即停止补建，已经登记的会话可从联系人页面管理。

#### 实际改动与 raw 归档

实现与验证见 [raw/changes/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-f267229129f9a4)。
<!-- end-migrated-part: doc-98f596dd5f8d22 -->

<a id="doc-62206a40735cb5"></a>

### 联系人策略保存超时影响分析与实施计划

来源：`llm wiki/wxbot/impacts/2026-11-05-contact-policy-save.md:1`。

### 联系人策略保存超时影响分析与实施计划

#### 目标与基线

修复保存策略长时间等待后未持久化，并让已有但未安装的技能可见、可明确取消。
当前目录 D:/work/code/wxbot，分支 codex/index-tts-skill，HEAD a1f40c38e120376f992d69628f0e8aec308f1d76；保留已有未提交修改。

#### 已核对的调用与原因

- `web/src/components/ContactDialog.vue:369` submitPolicy → `web/src/contactState.js:143` contactSave → POST /api/contacts。
- `src/dashboard/api/contacts.py:32` save → `src/butler/identity/contact_admin.py:345` ContactAdmin.save。
- 原 save 在 BEGIN IMMEDIATE 内调用 _policy；dashboard/http.py:172 的验证回调调用 api/support.py:61 _load_butler_config。
- DirectoryStore.snapshot 经 ContactStore 构造函数再次 BEGIN IMMEDIATE（contact_store.py:38），同库另一连接等待 30 秒，保存回滚。
- ContactDialog.loadSkills 保留已有 allowed_skills，但只渲染安装目录中的技能，未安装的已有值不可见，服务端严格校验仍会拒绝。
- 图谱 modules/identity 和 modules/dashboard 尚未详细覆盖联系人策略写入；本次补充专门 API 词条并反向关联。

#### 修改位置与契约

- ContactAdmin.save：事务外根据只读快照和目标预验证策略；写事务内重新检查版本、目标和心跳约束。验证器签名、角色/工具白名单规则不变。
- ContactDialog.vue：显示已有未安装技能，保持勾选；只有使用者明确取消才从请求移除；显示保存中状态。
- dashboard/http.py：校验错误指出具体未知技能，方便定位；仍拒绝新添加的未知技能。
- 请求仍为 action/id/version/policy，policy 仍为 role_skill/allowed_skills/heartbeat_enabled；成功仍返回完整联系人快照，冲突 409，非法策略 400。
- 数据落入 unified_contacts.payload 的 conversations[].policy 或 person_policies，version 用于并发控制；无表/字段变更、无迁移。

#### 执行与验证

- [x] 临时 SQLite 回归：验证器读取同库目录时，人物/会话策略可保存并重新读取。
- [x] 临时 SQLite 回归：验证期间有并发修改时拒绝旧版本，不覆盖新值；非法技能不落盘。
- [x] 将验证移出写事务，保留事务内版本与目标校验。
- [x] 前端冒烟：未安装技能可见且不会静默删除，取消后保存并重开保持新策略；错误保留弹窗。
- [x] pytest 全离线、web build/smoke、Hallmark component 检查、源码编译和 diff 检查。
- [x] 追加 raw、更新 API/模块知识页、ingest、lint。

#### 风险与边界

预验证与写入间配置可能变化，以事务内版本检查拒绝并发旧写；不放宽服务端能力权限。
无异步任务、消息投递或模型调用改动。测试不访问真实剪贴板或发送微信。
不修改生产策略，不删除任何已有权限；不重启已有进程。代码加载需使用者自行重启管理台，前端需刷新。
回滚本次源码和对应 web/dist 即可，无数据迁移。


#### 验证结果与保留事项

联系人管理 16 项通过；web build/smoke、compileall、diff 检查通过。全量测试 4 项失败与 Hallmark 共享主题既有 findings 见 [raw/changes/2026-11-05-contact-policy-save](identity-tools.md#doc-ef8af1106d1713)，不宣称全量通过。

图谱已登记 7 页；最终 lint 保留两个既有 pending-change（2026-11-03-feat-voice-002-indextts、2026-11-03-indextts-enqueue-media），以及 symbols/model-worker 的 page/source drift；本次受影响页无新增巡检问题。
<!-- end-migrated-part: doc-62206a40735cb5 -->

<a id="doc-b934820de6d35e"></a>

### 启用停用的群成员身份

来源：`llm wiki/wxbot/impacts/2026-11-05-enable-group-binding.md:1`。

```yaml
type: impact
status: completed
date: 2026-11-05
```
### 启用停用的群成员身份

#### 需求与现有路径

核对 [modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/web](dashboard.md#doc-aeec90dfe23cd3)、[apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc) 与 [concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)。联系人已能编辑群绑定，但现有 `binding` 动作会同时确认身份与昵称。`src/butler/identity/contact_admin.py:507` 的 `binding_disable` 则只改开关，适合作为启用动作的对称入口。

#### 文件、调用与数据

- `web/src/views/ContactsView.vue:269,442`：群成员列表、联系人群身份及折叠绑定列表提供「启用」，沿用 `web/src/contactState.js:45` 的请求与版本冲突反馈。
- `src/butler/identity/contact_admin.py:345,507`：在 `POST /api/contacts` 下添加 `binding_enable`，要求人物 `id`、`binding_id`、`version`，沿用本机同源确认和完整快照响应。事务中核对群绑定及人物归属，只写 `user_bindings.enabled/version`、`user_audit` 和现有联系人版本。保留确认标记、昵称和会话开关，无迁移。

#### 验证与回滚

临时业务库测试仅恢复目标群绑定、保留身份状态、拒绝错归属和旧版本；假数据 smoke 测试启用按钮及刷新。没有新增异步任务。回滚源文件和 dist 即移除按钮与动作，已有开关仍可经现有管理流程调整。

实际改动见 [raw/changes/2026-11-05-enable-group-binding](identity-tools.md#doc-6f2fac571f1610)。
<!-- end-migrated-part: doc-b934820de6d35e -->

<a id="doc-f39c15a6fe0885"></a>

### 群成员身份改用昵称优先，头像只作证据

来源：`llm wiki/wxbot/raw/changes/2026-10-31-group-identity-nickname.md:1`。

```yaml
type: change
title: 群成员身份改用昵称优先，头像只作证据
pages:
- concepts/group-identity-evidence
- concepts/identity-authority
- concepts/delivery-state
- concepts/message-pipeline
- modules/common
- modules/identity
- modules/wxbot
- symbols/queue-finish
- symbols/queue-store
- tables/queue-batches
- tables/queue-inbox
- tables/queue-outbox
```
### 群成员身份改用昵称优先，头像只作证据

#### 目标与背景

诊断「每次启动 wxbot 就多出几条待命名联系人、还没有头像」时查到四层原因：启动重放把 `inbox` 里的头像证据反复上送；上送用的是入库那一刻的昵称快照，群目录后来学到的名字不回填；空白截图（遮挡窗口）被当成合法证据永久重放；butler 只拿头像 hash 当身份标识。改法是让群成员按「已登记 member_key → 同群昵称 → 新建」认人，头像退为展示证据。完整诊断与实测数据见 [impacts/2026-10-31-group-identity-nickname](identity-tools.md#doc-fbe924ce9641ad)。

#### 文件与代码位置

- `src/common/avatar_identity.py:57` 新增 `avatar_is_informative` 与 `BLANK_AVATAR_COLORS`。
- `src/wxbot/wechat/chat_window.py:236` `_runtime_avatar` 在源头丢弃空白块。
- `src/wxbot/queue_store.py:192` `identity_observations` 去掉 base64 长度启发式。
- `src/wxbot/inbox.py:103` `sync_users` 补昵称、丢空白头像、跳过无名观测。
- `src/butler/identity/user_registry.py:355` `observe` 与新增的 `:244` `_learn_nickname`。
- 规则与实测边界写进新建的 [concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a)，并同步 [modules/common](wxbot.md#doc-dd2bd595b3d8f8)、[modules/identity](identity-tools.md#doc-5e308350a1ba25)、[modules/wxbot](wxbot.md#doc-8508032cbe5131)、[concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。
- 顺带修正 [concepts/delivery-state](delivery-pump.md#doc-1e3fe9ed2e96f6)、[concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15)、[symbols/queue-finish](outbox-text.md#doc-b3c365f5c9fdf1)、[symbols/queue-store](queue-storage.md#doc-37f6245b143a25)、[tables/queue-batches](queue-worker.md#doc-8e6cc338038d9a)、[tables/queue-inbox](inbox.md#doc-6529d9966e604a)、[tables/queue-outbox](queue-storage.md#doc-6dd6d137f99cdf) 里已经过期的 `queue_store.py` / `inbox.py` 来源行号（此前队列改动留下的偏移，`wiki.py lint` 一直报 source-anchor）。

#### 接口与字段

`POST /api/users/observe` 字段不变，只是 `avatar` 可能为空、`member_name` 更完整。`GET /api/contacts` 的 `avatar` 语义不变。没有新增或删除 HTTP 接口。

#### 数据库与迁移

无结构变更。只新增 `user_audit` 动作 `nickname_learned` 与 `avatar_alias`。现有 5 条 `待命名-*` 与 `inbox` 里的空白头像证据需要一次性清理，属于运维动作，需单独授权后执行；清理后重放不会再把它们建回来。

#### 前端消费点

无前端代码改动。管理台联系人列表「头像不显示」的根因之一（待命名档案 `identity_confirmed=0` 拿不到头像）随昵称补全自动缓解，不需要改 `src/dashboard/` 或 `web/`。

#### 测试与异步任务

`tests/butler/identity` + `tests/unit/wxbot` 共 297 项全过。新增用例：空白块拒绝、3 色图形头像保留、归一化后空白块仍为空、启动重放跳过无名群成员观测。第一版判据是「颜色数 ≥64」，被测试实测证伪（3 色 fixture 被误杀），已改为只拒绝颜色数 ≤2；亮度标准差与 dhash 位数实测同样无区分度，记录在词条里避免以后重犯。

全套 `tests` 仍有 3 条与本次无关的旧失败：`test_queue_admin` 与 `test_queue_store` 的批次状态被判成 `done`、`test_typing` 的时序断言。本次没有触碰 `_recompute_batch` 与输入时序，属于既有问题，未在本记录内修复。

#### 风险与回滚

同群两个人用完全相同的昵称会被并成一条，这是有意的取舍：dhash 实测无法区分同一个人和不同的人。管理员确认过的昵称不会被群昵称覆盖；同名冲突仍走 `ambiguous`。回滚只需撤销上述 5 处改动，数据库无结构变更。
<!-- end-migrated-part: doc-f39c15a6fe0885 -->

<a id="doc-f3232d3cef51df"></a>

### 截图占位名不再当作群昵称重放

来源：`llm wiki/wxbot/raw/changes/2026-10-31-identity-placeholder-names.md:1`。

```yaml
type: change
title: 截图占位名不再当作群昵称重放
pages:
- concepts/group-identity-evidence
- concepts/message-pipeline
- modules/wxbot
```
### 截图占位名不再当作群昵称重放

#### 目标与背景

[raw/changes/2026-10-31-group-identity-nickname](identity-tools.md#doc-f39c15a6fe0885) 落地后清空了 5 条待命名档案，随后用真实数据库跑启动重放仿真，发现还会再冒两条：`待命名-178c1373d18d` 与 `待命名-22591d351243`。

原因不在头像，而在名字的判定口径。启动重放读的是 `observations.snapshot` 里的截图原始行，截图读不出真名时写的是 `成员-<ID前8位>`。它是非空字符串，能穿过「没有昵称就不重放」的守卫；而 butler 端 `contact_identity.normalize_name` 把 `成员-` 前缀视为无名，于是 `named=False`，转而新建 `待命名-<hash>`。同一件事两边口径不一致，档案就来回长。

完整诊断与清理记录见 [impacts/2026-10-31-group-identity-nickname](identity-tools.md#doc-fbe924ce9641ad)。

#### 文件与代码位置

- `src/wxbot/inbox.py:23` 新增 `member_nickname`：`成员-<ID前8位>` 与空名字等价。
- `src/wxbot/inbox.py:109` `sync_users` 的两个循环都改用它取昵称，快照分支不再把占位名上送。
- `src/wxbot/inbox.py:253` `_capture` 改用同一函数，去掉原来内联的判断，两处口径合一。
- 规则写进 [concepts/group-identity-evidence](identity-tools.md#doc-82631ed77ef07a) 与 [modules/wxbot](wxbot.md#doc-8508032cbe5131)；顺带修正 `inbox.py` 增行后 [concepts/message-pipeline](wxbot.md#doc-6cbfc97cc45d15) 的 `_capture` 行号。

#### 接口与字段

无接口改动。`POST /api/users/observe` 的 `member_name` 可能为空——这正是本次要的效果：宁可等下一次发言补真名，也不要用占位名建档案。

#### 数据库与迁移

无结构变更，无迁移。

#### 前端消费点

无前端改动。管理台不再出现新的 `待命名-` 行。

#### 测试与异步任务

`tests/butler/identity` + `tests/unit/wxbot` 共 298 项全过。新增 `test_startup_identity_sync_does_not_treat_a_screenshot_placeholder_as_a_name`。

用真实数据库副本跑完整重放（真实 `MainInbox.sync_users` + `UserRegistry.observe`）：`user_profiles` 23→23、`user_bindings` 13→13，零新建。此前一版仿真拿 `user_bindings.nickname` 当昵称来源，而真实来源是 `unified_contacts.aliases`，因此误报两个新建；这个坑记在影响面报告里。

#### 风险与回滚

真名一直读不出来的成员不会被启动重放建档，要等他下次发言。这是有意的：占位名建出来的档案无法核对。回滚只需撤销 `inbox.py` 三处改动。
<!-- end-migrated-part: doc-f3232d3cef51df -->

<a id="doc-f267229129f9a4"></a>

### 修改记录

来源：`llm wiki/wxbot/raw/changes/2026-11-05-contact-enrollment-and-tts-ui.md:1`。

```yaml
type: change
title: 新消息补建联系人窗口与移除会话 IndexTTS 专区
pages:
- modules/identity
- concepts/message-pipeline
- symbols/butler-handle
- modules/web
- apis/index-tts
- apis/dashboard-contact-policy
- apis/dashboard-voice-assets
- apis/butler-handle
- concepts/development-baseline
- concepts/group-identity-evidence
- concepts/model-error-contract
- modules/butler
- modules/wiki
- symbols/butler-result
supersedes:
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
```
### 修改记录

#### 目标与背景

私聊新消息可登记人物与身份，但缺失管理台私聊分类要求的窗口字段。删除后再次收到消息仍可能看不到联系人。补建缺失窗口，并移除「编辑窗口与收发设置」的 IndexTTS 授权和预设专区。对上面两条历史记录的更正仅涉及页面入口与其调用，后端接口与运行时语音行为仍按原契约。

#### 文件与代码位置

- `src/butler/identity/user_registry.py:350` `enroll_conversation` 用既有业务库事务建立窗口。`src/butler/agent/core.py:181` `archive_group` 与 `:275` `_handle_request` 调用。
- `web/src/components/ContactDialog.vue:236` `submitConversation` 只提交窗口资料与语音回复设置；`:373` 语音回复 fieldset 仍在。`web/src/views/ContactsView.vue:152` `openConversation` 不再传专用的有效策略参数。`web/src/styles/contacts.css:28` 删除退场的专用样式。README 更新操作路径，`web/dist` 已重建。

#### 接口与字段

不涉及新增 HTTP 路由或 DTO。正常 `/v1/handle`、流式处理和群归档补建窗口，`GET /api/contacts` 按现有字段投影。仅处理群归档的对方消息；历史快照 `/v1/users/observe`、心跳和专用 HTTP 转发不补建。原 `/api/tts-presets` 仍支持兼容客户端。

#### 数据库与迁移

不涉及新表或迁移。`unified_contacts.payload.conversations` 补建唯一窗口名的条目，私聊取同库启用绑定的 `user_id` 作 `person_id`，群条目没有人物归属。采用窗口名与 default profile 的原回退路由，状态 `needs_route=true`，初始独立监听关闭、无订阅、无策略且不继承已有个人策略。复核与保存同事务，已有窗口包括停用、同名异类型窗口均保留。

#### 前端消费点

联系人会话列表使用原 `conversations[]`，无需客户端补造记录。会话弹窗停止读取技能目录和预设接口，也停止提交网页预设或技能策略；AI 设置仍可单独保存技能授权。本地语音模式、音色绑定和异步保存的固定目标逻辑仍可用。旧网页预设按旧窗口名称保留，改名不再自动复制。

#### 测试与异步任务

本地 `tests/butler/identity/test_identity_runtime.py` 先复现私聊和群聊缺窗口，再通过删除后补建、幂等、停用与历史快照隔离。目标离线套件 130 项、前端展示规则 8 项、build 和 smoke 通过。Hallmark 静态 0 FAIL、0 WARN，一条已有间距备注；浏览器进程启动失败。较广的 HTTP 回归受本机连接权限限制。无新增后台任务或定时任务。

#### 风险与回滚

补建以实际采集的新消息为前提，全局监听关闭且未绑定窗口时不会从微信采集新消息。此次没有操作运行实例，加载需手动重启 Butler 和刷新管理台。回滚源码和前端构建即可停止补建，已写入的记录可在联系人管理中调整或删除。详见 [impacts/2026-11-05-contact-enrollment-and-tts-ui](identity-tools.md#doc-98f596dd5f8d22)。
<!-- end-migrated-part: doc-f267229129f9a4 -->

<a id="doc-ef8af1106d1713"></a>

### 修复联系人策略保存锁等待与不可见旧技能

来源：`llm wiki/wxbot/raw/changes/2026-11-05-contact-policy-save.md:1`。

```yaml
type: change
title: 修复联系人策略保存锁等待与不可见旧技能
pages:
- apis/dashboard-contact-policy
- modules/identity
- modules/dashboard
- modules/web
- apis/index-tts
- apis/dashboard-voice-assets
- concepts/development-baseline
```
### 修复联系人策略保存锁等待与不可见旧技能

#### 目标与背景

修复“保存策略”长时间等待、关闭后重新打开未生效。根因是 ContactAdmin 写事务内的目录验证回调重新读取同一联系人库，经 ContactStore 构造函数申请第二把写锁，等待超时后回滚。另一个阻塞是已保存但未安装的技能被 UI 隐藏，服务器仍严格拒绝该值。详见 [impacts/2026-11-05-contact-policy-save](identity-tools.md#doc-62206a40735cb5)。

#### 文件与代码位置

- src/butler/identity/contact_admin.py:383：事务外只读快照确定校验路由并完成目录验证，事务内复查版本、目标和心跳约束；人物/会话共用。
- src/dashboard/http.py:181：未知技能错误包含具体名称和明确处理办法，仍严格拒绝。
- web/src/components/ContactDialog.vue:137、:546、:554：保留并显示未安装技能，使用者明确取消才移除；显示保存中状态。web/dist 已随源码重新构建。
- tests/dashboard/test_contact_admin.py:79、:107 与 web/scripts/smoke.mjs:695：同库读取、并发旧写、未安装技能、保存后重开回归。
- 图谱新建 [apis/dashboard-contact-policy](identity-tools.md#doc-fdc456753803cc) 并与相关模块/接口关联，更新移动的 ContactDialog 来源行号。开发基线页只复核 http 来源摘要，原基线事实不变。

#### 接口与字段

无新增 API/DTO。继续使用 POST /api/contacts 的 action/id/version/policy，policy 结构和服务端角色/工具验证规则不变。非法策略返回 400，版本冲突返回 409，成功返回完整快照。未安装技能不自动移除、不授予执行能力。

#### 数据库与迁移

无数据库迁移。仍写 unified_contacts.payload 的 person_policies 或 conversations[].policy，并增加 version；预校验与提交之间变化通过事务内版本检查拒绝。未写生产配置或权限数据。

#### 前端消费点

ContactDialog.submitPolicy → contactState.contactSave；Vue 3/Vite、现有布局、字段/事件/路由和主题令牌保持。原生复选框继承共享 focus-visible/disabled 样式，无新增动画；未安装项初始勾选，只有明确取消才改变请求。

#### 测试与异步任务

- TDD：3 个临时 SQLite 用例在修复前以 database is locked 失败；修复后联系人管理 16 项测试通过，含人物/会话保存重读、并发版本冲突及同源/原子性。
- npm --prefix web run build / smoke 通过；新增 UI 回归先以缺少显式取消入口失败，再验证未安装技能保留/取消、保存中和保存重开。
- compileall 与 git diff --check 通过（Git 提示已有文件的 LF/CRLF 转换）。
- 全量离线 pytest 有 4 项失败：test_portable_install.py::test_plugin_references_and_protocol_are_self_contained（技能数量预期 6、实际 7）；test_queue_admin.py::test_multipart_cli_sent_and_retry_preserve_other_parts；test_queue_store.py::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker；test_typing.py::test_typing_steps_keep_half_second_between_batches_and_one_final_enter。分别在安装、队列状态和输入节奏路径，不改这些业务。
- Hallmark component 静态检查单独扫描组件时因共享样式未纳入报 focus/active/disabled；连同实际共享样式、实际 /app/?tab=contacts 渲染后，检查产出 5 张图，报告共享主题/现有页面 116 FAIL、3 REFLEX、2 WARN。无新增 CSS；未扩大到旧主题清理，不声称 Hallmark 全通过。新弹窗逻辑由假数据 smoke 验证，渲染检查未操作生产弹窗。
- 无新增或更改异步任务。所有测试使用临时库/假 HTTP/假投递，不访问真实剪贴板，不发送微信。

#### 风险与回滚

预校验不持写锁；写入仍检查版本，避免并发覆盖。未放宽角色/工具目录边界，不绕过服务签发能力。保留工作树原有未提交修改。回滚本次源码和 dist 即可，无迁移。管理台进程需使用者自行重启、页面需刷新后加载；本次未重启服务，未移除生产权限记录，也未发送之前请求的语音。
<!-- end-migrated-part: doc-ef8af1106d1713 -->

<a id="doc-6f2fac571f1610"></a>

### 修改记录

来源：`llm wiki/wxbot/raw/changes/2026-11-05-enable-group-binding.md:1`。

```yaml
type: change
title: 为停用的群成员身份增加启用按钮
pages:
- apis/dashboard-contact-policy
- apis/index-tts
- modules/identity
- modules/web
```
### 修改记录

#### 目标与背景

为停用的单条群身份提供直接启用动作，避免编辑绑定同时确认身份或改变整个人物的开关。

#### 文件与代码位置

- `src/butler/identity/contact_admin.py:360,508` 注册 `binding_enable` 并和停用复用绑定归属校验。
- `web/src/views/ContactsView.vue:270,452,460` 增加启用处理、请求等待和按钮。`web/dist` 已重新构建。

#### 接口与字段

`POST /api/contacts` 新增 `action=binding_enable`，提交人物 `id`、`binding_id`、全局 `version`。沿用本机同源确认、旧版本 409 与完整快照响应。服务端拒绝不属于该人物的绑定及非群绑定。

#### 数据库与迁移

在现有业务库事务中写 `user_bindings.enabled=1`、推进绑定和联系人版本，并在 `user_audit` 记录 `enabled`。保留昵称、确认标记、识别证据与窗口开关。不涉及新增表、字段或迁移。

#### 前端消费点

群成员列表、个人群身份和折叠绑定列表均可启用停用的单条记录。显示启用中，阻止重复提交；成功采用服务端快照，失败沿用页面错误提示。

#### 测试与异步任务

临时库的 48 项联系人和身份回归以及前端 build、smoke 通过。测试覆盖保留未确认状态、拒绝错归属及旧版本、等待回执与启用后刷新投影。Hallmark 静态 0 FAIL、0 WARN，浏览器进程无法启动。不涉及新增后台任务。

#### 风险与回滚

启用会让此群绑定重新参与之后的识别，仍受原有确认与权限规则约束。回滚源码和 dist 即移除入口与新动作，不需要回滚数据库。详见 [impacts/2026-11-05-enable-group-binding](identity-tools.md#doc-b934820de6d35e)。
<!-- end-migrated-part: doc-6f2fac571f1610 -->
