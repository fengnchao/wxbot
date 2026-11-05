---
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
---
# 观察证据与身份权限

## 业务规则

[[modules/identity]] 解析人物、绑定和记忆归属；ToolService 的 issue / verify / call 对服务签发身份、时效与权限进行校验。模型提示、运行时 Skill 分类、联系人同名和头像相似均不授予工具权限。

头像只是证据，不是权限：遮挡窗口截到的纯色块（颜色数不超过 `BLANK_AVATAR_COLORS`）会被丢弃，不进入档案；群成员靠 member_key 与昵称认人，见 [[concepts/group-identity-evidence]]。

## 输入到输出

[[apis/butler-handle]] 的 member_key/member_name/avatar 是来自 [[modules/wxbot]] 的观察；[[symbols/butler-handle]] 解析后才提供身份相关 meta。[[symbols/queue-finish]] 仅使用服务给出的 mention_name 给第一分句设置 @；不能用模型文本/本地猜测替换收件身份。2026-11-02 复核：`queue_store.py` 只扩展了投递事件细节白名单，`member_name` 只取服务给出的 mention_name 这一条未变。

## 开发与运行边界

[[apis/index-tts]] 使用同一能力边界；生成参数不含身份、目标、URL 或路径。只读能力仅列预设，耗时生成后再次 verify（含动态策略撤销）。operations 按 owner/request/call_id 绑定指纹，并登记同内容别名；最终状态同步更新别名，投递未知不重复发送。

[[modules/plugin]] 的角色/工具 Markdown 是运行资产，[[modules/wiki]] 是开发知识，不作为运行时权限来源。不能因图谱写着“允许”就绕过业务校验。详细身份表与管理端合并契约仍在 [[coverage]] 待建档清单。

## 代码依据

- `src/butler/agent/tools.py:47` — `def issue(`
- `src/butler/agent/tools.py:55` — `def verify(`
- `src/butler/agent/tools.py:89` — `def call(`
- `src/wxbot/queue_store.py:361` — `member_name = str(mention_name or '').strip()`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]

[[raw/changes/2026-11-01-mention-fallback-unread-retry]]

[[raw/changes/2026-11-02-ui-snapshot-ref-contract]]

[[raw/changes/2026-11-02-details-whitelist-reverify]]

[[raw/changes/2026-11-02-mention-residue-reverify]]


## 本次核对

[[raw/changes/2026-11-04-index-tts-skill]]：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [[apis/index-tts]]，其余已述契约未改。


## 联系人语音配置核对

[[raw/changes/2026-11-04-webui-preset-binding]]：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [[apis/index-tts]]。


图谱契约说明来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]。
