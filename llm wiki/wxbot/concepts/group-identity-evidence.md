---
type: concept
module: identity
summary: 群成员先按同群 member_key 与昵称认人，头像 dhash 只作证据且不足以区分个体
coverage: core
last_verified: '2026-11-02'
sources:
- path: src/butler/identity/user_registry.py
  line: 350
  anchor: def observe(
- path: src/butler/identity/user_registry.py
  line: 239
  anchor: def _learn_nickname(
- path: src/wxbot/inbox.py
  line: 111
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
  line: 246
  anchor: def _runtime_avatar(
- path: src/wxbot/wechat/main_window.py
  line: 28
  anchor: 'def plausible_nickname(name: str) -> bool:'
changes:
- raw/changes/2026-10-31-group-identity-nickname
- raw/changes/2026-10-31-identity-placeholder-names
- raw/changes/2026-11-01-mention-fallback-unread-retry
- raw/changes/2026-11-01-citation-sweep
- raw/changes/2026-11-01-knowledge-vault-graph
- raw/changes/2026-11-02-ui-snapshot-ref-contract
- raw/changes/2026-11-02-mention-residue-reverify
---
# 群成员身份：昵称优先，头像退为证据

## 业务规则

群成员认人的顺序是「已登记的 `member_key` → 同群昵称 → 新建」。头像只用来补证据和展示，不参与判定是不是同一个人。档案已存在时，群目录后来学到的昵称会补上（`_learn_nickname`），不再让它永远停在 `待命名-`；管理员确认过的昵称不会被群昵称覆盖。

## 输入到输出

`POST /api/users/observe` 仍只收 `member_key` / `member_name` / `avatar`。空白的 `avatar` 会被丢弃，`member_name` 缺失只更新证据、不新建带名字的档案；同群出现同名且只有一条既有档案时，把新的 `member_key` 并到那条档案的别名里。

## 实测边界

同一人不同次截图的 dhash 距离 10~35，不同人之间 23~32，两者重叠，**dhash 无法区分同一个人和不同的人**；`_avatar_score` 的距离 ≤ 4 实际等价于「只认同一张截图」。亮度标准差和比特位数同样重叠（坏图 28~29 位、正常图 19~33 位）。因此颜色数是唯一可用判据：窗口被遮挡时截到的纯色块只有 1 种颜色，真实的纯色块图形头像有十几种颜色，按色彩丰富度过滤会误杀真实头像。

wxbot 启动时 `sync_users` 会重放 `inbox` 里的头像证据，这是「每次启动多几条待命名」的来源。重放只用于补证据，因此空白头像和没有昵称的群成员观测都不重放：它们建不出能核对的人，真正的资料等这个人下次发言再补。截图读不出真名时会写下 `成员-<ID前8位>` 占位名，它和空名字等价，不能当昵称上送。

## 已知取舍

同群两个人用完全相同的昵称会被并成一条，接受这个取舍：现有头像证据本来就没有区分度，靠相似度防误并只会让重复继续增长。

昵称来自消息预览时另受 `preview_sender` 的格式约束（`src/wxbot/wechat/main_window.py:45`）：长度超过 16（微信昵称上限）、含换行或句读、以 `[` 开头、以「你/我」开头且含空白的整句都不当昵称（`plausible_nickname`，`src/wxbot/wechat/main_window.py:28`）。这条约束是 2026-11-01 补的：此前「你收到一笔群分红 请在手机上查看」这类卡片文案被学成成员昵称，进而成为 `mention_name`，让 @ 永远选不中候选。人工在管理台确认的昵称不受此约束。

## 代码依据

- `src/butler/identity/user_registry.py:355` — `def observe(`
- `src/butler/identity/user_registry.py:244` — `def _learn_nickname(`
- `src/wxbot/inbox.py:111` — `def sync_users(`
- `src/wxbot/inbox.py:23` — `def member_nickname(`
- `src/wxbot/queue_store.py:192` — `def identity_observations(`
- `src/common/avatar_identity.py:57` — `def avatar_is_informative(`
- `src/wxbot/wechat/chat_window.py:246` — `def _runtime_avatar(`
- `src/wxbot/wechat/main_window.py:28` — `def plausible_nickname(name: str) -> bool:`
- `src/wxbot/wechat/main_window.py:45` — `def preview_sender(preview: str, text: str) -> str | None:`

## 入库来源

[[raw/changes/2026-10-31-group-identity-nickname]]

[[raw/changes/2026-11-01-mention-fallback-unread-retry]]

[[raw/changes/2026-11-01-citation-sweep]]

[[raw/changes/2026-11-02-ui-snapshot-ref-contract]]

[[raw/changes/2026-11-02-mention-residue-reverify]]
