---
type: module
module: common
summary: 仓库根、事件追踪、流和 wire schema 的跨包纯基础层
coverage: overview
last_verified: '2026-10-31'
sources:
- path: src/common/paths.py
  line: 29
  anchor: REPO_ROOT = _root()
- path: src/common/flow_trace.py
  line: 74
  anchor: def record(
- path: src/common/media_bundle.py
  line: 9
  anchor: 'def '
- path: src/common/avatar_identity.py
  line: 57
  anchor: def avatar_is_informative(
changes:
- raw/changes/2026-10-31-knowledge-graph-bootstrap
- raw/changes/2026-10-31-group-identity-nickname
---
# 共享基础能力

## 职责与边界

`src/common/` 不依赖 Butler 业务，不操作微信 UI。`common.paths.REPO_ROOT` 是项目路径唯一共享入口，支持 WXBOT_ROOT；新模块不按目录深度猜项目根。

## 使用方

[[modules/butler]]、[[modules/wxbot]]、[[modules/dashboard]] 和 [[modules/wiki]] 都可使用其路径/纯 schema 能力。flow_trace 用请求 ID 记录流转，消息正文不能写进结构追踪证据。媒体 wire schema 由两服务共享，详细字段另行建档。

## 头像证据

`avatar_identity.normalize_avatar` 统一输出 36×36 PNG + dhash-v1，透明区域用 `#1F1F1F` 兜底。`avatar_is_informative` 只拒绝颜色数不超过 `BLANK_AVATAR_COLORS` 的纯色块：窗口被遮挡、最小化或元素滚出视口时抓到的就是这种图，dhash 仍有值，不能当身份证据。不能改用颜色丰富度、亮度标准差或比特位数做判据，实测这些都和真实头像重叠（见 [[concepts/group-identity-evidence]]）。

## 代码依据

- `src/common/paths.py:29` — `REPO_ROOT = _root()`
- `src/common/flow_trace.py:74` — `def record(`
- `src/common/media_bundle.py:9` — `def `
- `src/common/avatar_identity.py:57` — `def avatar_is_informative(`

## 入库来源

[[raw/changes/2026-10-31-knowledge-graph-bootstrap]]
