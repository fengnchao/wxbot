---
type: concept
module: wxbot
summary: 采集前恢复越屏微信窗口，监视器联合区域外的像素不能证明发送方
coverage: core
last_verified: '2026-11-05'
sources:
- path: src/wxbot/wechat/viewport.py
  line: 15
  anchor: 'def rect_is_visible(bounds, areas):'
- path: src/wxbot/wechat/viewport.py
  line: 38
  anchor: 'def fit_window_rect(bounds, areas):'
- path: src/wxbot/wechat/viewport.py
  line: 86
  anchor: 'def ensure_window_visible(window):'
- path: src/wxbot/wechat/chat_window.py
  line: 346
  anchor: def read_from_window(self, root,
- path: src/wxbot/wechat/main_window.py
  line: 287
  anchor: 'if not ensure_window_visible(win):'
changes:
- raw/changes/2026-11-05-group-auto-voice
depends_on:
- modules/wxbot
---
# 截图采集与可见窗口

## 原因与边界

ImageGrab 在真实监视器范围以外可能得到纯黑补边。左右 gutter 背景不一致时，ChatWindow.side_scores 必须拒绝方向证据，不能把黑补边当头像或文字。历史出现此错误而窗口入屏后恢复，原因是越屏几何，不应提高色差阈值。详见 [[concepts/unread-capture-retry]]、[[concepts/message-pipeline]]。

## 监视器联合区域

viewport.rect_is_visible 逐区域扣除覆盖部分，支持负坐标、重叠监视器、跨屏窗口和屏间空隙，不能只用最大矩形冒充显示范围。fit_window_rect 对已经完整可见的窗口原样返回；否则选择重叠最大或最近的工作区，能放下时只平移，窗口大于工作区时才缩小。monitor_work_areas 使用明确 HANDLE 类型的 Win32 MonitorFromRect/GetMonitorInfoW，读取工作区而非固定主屏尺寸。

## 恢复入口及失败语义

MainWindow.select 在已选中会话的早退分支之前恢复主窗口，并处理独立窗口。ChatWindow.read_from_window 在重新定位消息列表之前恢复现有 root，覆盖当前聊天无未读角标的采集路径；不切换会话或调用 SetActive。普通会话枚举、被动窗口 getter 仍不主动移动。

ensure_window_visible 通过控件 MoveWindow 后等待实际边界进入工作区，失败或不可确认则拒绝采集。side_scores 还在截图前验证头像高度带被真实监视器联合区域覆盖；越屏记 row_offscreen，不再用同文已发送缓存推断 self。原 gutter 一致性及裁剪拒绝规则保留，未知发送方仍不推进快照。

## 测试与风险

本地 tests/unit/wxbot/test_viewport.py 覆盖联合几何、窗口放置、已可见不移动、恢复失败、无未读当前面板及越屏缓存拒绝；合成像素和 fake root 不访问真实消息。clipped-history 测试提供固定监视器和有效可见 fake root，意外移动直接失败，仍执行真实几何与采集逻辑。

窗口最小尺寸大于可用区域、系统拒绝移动或监视器信息不可用时仍会 ReadDeferred；不猜发送方。无 API/DTO/数据库迁移、无权限变更。加载代码需自行重启 wxbot。来源 [[raw/changes/2026-11-05-group-auto-voice]]。
