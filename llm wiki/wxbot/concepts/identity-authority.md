---
type: concept
module: identity
summary: 窗口/头像/昵称是证据，服务签发上下文才是工具授权边界
coverage: core
last_verified: '2026-10-31'
sources:
- path: src/butler/agent/tools.py
  line: 47
  anchor: def issue(
- path: src/butler/agent/tools.py
  line: 56
  anchor: def verify(
- path: src/butler/agent/tools.py
  line: 92
  anchor: def call(
- path: src/wxbot/queue_store.py
  line: 345
  anchor: member_name = str(mention_name or '').strip()
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
---
# 观察证据与身份权限

## 业务规则

[[modules/identity]] 解析人物、绑定和记忆归属；ToolService 的 issue / verify / call 对服务签发身份、时效与权限进行校验。模型提示、运行时 Skill 分类、联系人同名和头像相似均不授予工具权限。

头像只是证据，不是权限：遮挡窗口截到的纯色块（颜色数不超过 `BLANK_AVATAR_COLORS`）会被丢弃，不进入档案；群成员靠 member_key 与昵称认人，见 [[concepts/group-identity-evidence]]。

## 输入到输出

[[apis/butler-handle]] 的 member_key/member_name/avatar 是来自 [[modules/wxbot]] 的观察；[[symbols/butler-handle]] 解析后才提供身份相关 meta。[[symbols/queue-finish]] 仅使用服务给出的 mention_name 给第一分句设置 @；不能用模型文本/本地猜测替换收件身份。

## 开发与运行边界

[[modules/plugin]] 的角色/工具 Markdown 是运行资产，[[modules/wiki]] 是开发知识，不作为运行时权限来源。不能因图谱写着“允许”就绕过业务校验。详细身份表与管理端合并契约仍在 [[coverage]] 待建档清单。

## 代码依据

- `src/butler/agent/tools.py:47` — `def issue(`
- `src/butler/agent/tools.py:56` — `def verify(`
- `src/butler/agent/tools.py:92` — `def call(`
- `src/wxbot/queue_store.py:345` — `member_name = str(mention_name or '').strip()`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
