# 联系人策略保存超时影响分析与实施计划

## 目标与基线

修复保存策略长时间等待后未持久化，并让已有但未安装的技能可见、可明确取消。
当前目录 D:/work/code/wxbot，分支 codex/index-tts-skill，HEAD a1f40c38e120376f992d69628f0e8aec308f1d76；保留已有未提交修改。

## 已核对的调用与原因

- `web/src/components/ContactDialog.vue:369` submitPolicy → `web/src/contactState.js:143` contactSave → POST /api/contacts。
- `src/dashboard/api/contacts.py:32` save → `src/butler/identity/contact_admin.py:345` ContactAdmin.save。
- 原 save 在 BEGIN IMMEDIATE 内调用 _policy；dashboard/http.py:172 的验证回调调用 api/support.py:61 _load_butler_config。
- DirectoryStore.snapshot 经 ContactStore 构造函数再次 BEGIN IMMEDIATE（contact_store.py:38），同库另一连接等待 30 秒，保存回滚。
- ContactDialog.loadSkills 保留已有 allowed_skills，但只渲染安装目录中的技能，未安装的已有值不可见，服务端严格校验仍会拒绝。
- 图谱 modules/identity 和 modules/dashboard 尚未详细覆盖联系人策略写入；本次补充专门 API 词条并反向关联。

## 修改位置与契约

- ContactAdmin.save：事务外根据只读快照和目标预验证策略；写事务内重新检查版本、目标和心跳约束。验证器签名、角色/工具白名单规则不变。
- ContactDialog.vue：显示已有未安装技能，保持勾选；只有使用者明确取消才从请求移除；显示保存中状态。
- dashboard/http.py：校验错误指出具体未知技能，方便定位；仍拒绝新添加的未知技能。
- 请求仍为 action/id/version/policy，policy 仍为 role_skill/allowed_skills/heartbeat_enabled；成功仍返回完整联系人快照，冲突 409，非法策略 400。
- 数据落入 unified_contacts.payload 的 conversations[].policy 或 person_policies，version 用于并发控制；无表/字段变更、无迁移。

## 执行与验证

- [x] 临时 SQLite 回归：验证器读取同库目录时，人物/会话策略可保存并重新读取。
- [x] 临时 SQLite 回归：验证期间有并发修改时拒绝旧版本，不覆盖新值；非法技能不落盘。
- [x] 将验证移出写事务，保留事务内版本与目标校验。
- [x] 前端冒烟：未安装技能可见且不会静默删除，取消后保存并重开保持新策略；错误保留弹窗。
- [x] pytest 全离线、web build/smoke、Hallmark component 检查、源码编译和 diff 检查。
- [x] 追加 raw、更新 API/模块知识页、ingest、lint。

## 风险与边界

预验证与写入间配置可能变化，以事务内版本检查拒绝并发旧写；不放宽服务端能力权限。
无异步任务、消息投递或模型调用改动。测试不访问真实剪贴板或发送微信。
不修改生产策略，不删除任何已有权限；不重启已有进程。代码加载需使用者自行重启管理台，前端需刷新。
回滚本次源码和对应 web/dist 即可，无数据迁移。


## 验证结果与保留事项

联系人管理 16 项通过；web build/smoke、compileall、diff 检查通过。全量测试 4 项失败与 Hallmark 共享主题既有 findings 见 [[raw/changes/2026-11-05-contact-policy-save]]，不宣称全量通过。

图谱已登记 7 页；最终 lint 保留两个既有 pending-change（2026-11-03-feat-voice-002-indextts、2026-11-03-indextts-enqueue-media），以及 symbols/model-worker 的 page/source drift；本次受影响页无新增巡检问题。
