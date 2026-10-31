---
type: impact
status: done
date: '2026-10-31'
---
# 群成员身份改用昵称优先，头像退为证据

目标：启动时不再自动冒出新「待命名-」档案，同一个人不因头像像素抖动被拆成多条。

## 查询与覆盖

已查询关键词“群成员身份/头像/昵称/member_key/观测”，图谱未命中；[[modules/butler]] 只覆盖联系人档案的对外行为，`wxbot` 侧的观测采集与重放无词条。本次按源码补报告，并新建词条。

## 现象与证据

真实库 `data/business.sqlite3` 实测：5 条 `待命名-*` 全部 `channel_type=group`、`identity_confirmed=0`，创建时间集中在同一秒；`user_audit` 显示 20:41 手动删除 4 条后，20:43 用**完全相同的 member_key** 又建回来。

`data/cache/wxbot_queue.sqlite3` 的 `inbox` 表里，只有 `0000000000000000` 是空白截图：解码后 1 种颜色，正是 `normalize_avatar` 的兜底填充色 `#1F1F1F`。另外 4 条都是**真实头像**——18~19 色的那三条是纯色块图形头像（亮度标准差 49.7/59.0/56.6，与正常头像 34.9~78.4 完全重叠，不是坏图）。

主因不是坏图，是**昵称没传到**：`178c1373d18dadec` 在 wxbot 侧已映射到「挽风」，butler 却建了 `待命名-178c1373d18d`；`a6a65012cd323637` 对应「我干嘛」同样没有传过去；剩下的 `2425da15c8313767`、`2425da3489763652` 群目录里确实没有名字。

同一个人不同次截图的 dhash 距离实测 10~35，不同人之间 23~32，**没有区分度**；现有 `_avatar_score` 要求距离 ≤ 4，等价于「只认同一张截图」。

## 根因

1. `src/wxbot/inbox.py:99` 启动时 `sync_users()` 把 `inbox` 表里每个 `(会话, member_key)` 的最新一条带头像记录重新上送 butler（`queue_store.py:192-199`，只增不减）。删除档案后证据仍在，下次启动必然重建。
2. `inbox` 里存的是入库那一刻的昵称快照，之后 `DirectoryStore` 学到映射也不回填；`sync_users()` 直接读快照，于是上送昵称为空 → `named=False` → 新建 `待命名-<hash>`。
3. `src/wxbot/wechat/chat_window.py:236` 只用 `1 < bit_count < 63` 挡纯黑纯白，挡不住遮挡时截到的纯色块，坏图因此进入 `inbox` 并永久重放。
4. `src/butler/identity/user_registry.py:355` 只把头像 hash 当身份标识；hash 一变即新建，名字撞车再拼 `（uuid前12位）`。
5. `src/butler/identity/contact_admin.py:296` 取头像只认 `identity_confirmed=1`，待命名档案永远拿不到头像。
6. 重放没有语义过滤：没有昵称、也没有既有档案的观测也会被建成新身份，所以删掉之后下次启动必然再冒出一条。
7. 快照重放读的是截图原始行，截图读不出真名时写的是 `成员-<ID前8位>` 占位名。它是非空字符串，能绕过“无名不重放”的守卫，butler 端的 `normalize_name` 又会把它判成无名——结果照样新建 `待命名-`。这一条是清完旧数据后仍会冒新条目的最后一个缺口。

## 文件、调用与边界

- `src/common/avatar_identity.py:57`：新增 `avatar_is_informative`，只拒绝颜色数不超过 `BLANK_AVATAR_COLORS`（=2）的纯色块。第一版用颜色数 ≥64 作判据，测试实测发现会误杀 3 色的图形头像，已纠正；亮度标准差与比特位数实测同样无区分度，不能改用。
- `src/wxbot/wechat/chat_window.py:236` `_runtime_avatar`：源头拒绝空白块。
- `src/wxbot/queue_store.py:192` `identity_observations`：只取有头像的证据，不再用 base64 长度做启发式判据，图片质量只由 `avatar_is_informative` 一处决定。
- `src/wxbot/inbox.py:109` `sync_users`：丢弃空白头像；昵称取群目录当前映射而不是入库快照；没有昵称的群成员观测不重放。
- `src/wxbot/inbox.py:23` 新增 `member_nickname`：把 `成员-<ID前8位>` 占位名等同于无名。`_capture` 与启动重放共用这一处判断，避免两边口径不一。
- `src/butler/identity/user_registry.py:355` `observe`：空白头像置空；已存在档案学到群昵称时补名字；新 key 命中同群同名且唯一时并回原档案。新增 `_learn_nickname`，不覆盖管理员确认过的昵称。
- 不改 `_avatar_score` 的严格阈值，也不让头像相似度参与身份合并。

## 验证

`tests/butler/identity` + `tests/unit/wxbot` 共 298 项全过，含新增用例：空白块拒绝、3 色图形头像保留、归一化后空白块仍为空、启动重放跳过无名观测、启动重放不把截图占位名当昵称。全套 `tests` 剩 3 条与本改动无关的旧失败（队列状态机 `_recompute_batch` 与输入时序）。

真实数据仿真：把 `business.sqlite3` 与 `wxbot_queue.sqlite3` 复制到临时目录，用真实 `MainInbox.sync_users` + `UserRegistry.observe` 跑完整重放，`user_profiles` 23→23、`user_bindings` 13→13，零新建。第一版仿真拿 `user_bindings.nickname` 当昵称来源，不是真实链路（真实来源是 `unified_contacts.aliases`），因此误报了两个新建，记录在此避免重犯。

## 接口与数据

`POST /api/users/observe` 字段不变（`member_key`/`member_name`/`avatar`），只是 `avatar` 可能为空、`member_name` 更完整。`GET /api/contacts` 的 `avatar` 字段语义不变，昵称补全后头像自然出现。

业务表结构不变；只新增 `user_audit` 动作 `nickname_learned` 与 `avatar_alias`。

## 风险与回滚

- 同群同名的两个人会被并成一条：接受。头像 dhash 实测无法区分同一个人和不同人，用相似度防误并只会让真实重复继续增长。同名冲突已有 `ambiguous` 语义保护。
- 管理员手工确认过的昵称不被群昵称覆盖。
- 回滚：撤销上述 6 处改动即可；数据库只多出审计行，无结构变更。
- 已授权清理完成：`user_profiles` 28→23，删掉 5 条无名字的 `待命名-*`；`inbox` 里那条空白证据（`0000000000000000`，正文保留）只清空 `avatar` 字段。保留 2 条 `display_name` 仍为 `待命名-` 开头的档案，它们分别对应「我」与「老登看剑」，`identity_confirmed=1` 且界面已按昵称展示，属于有效档案而非脏数据。
- 清理前的备份在 `data/backups/identity-cleanup-20261031T130450Z/`。
