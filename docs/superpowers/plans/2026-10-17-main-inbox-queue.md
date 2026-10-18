# 微信主窗口收发队列 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the user-authorized inline implementation. Track completion below.

**Goal:** 持续采集全部会话，以 SQLite 保存消息和回复，按会话合并后由单个后台工作线程处理。

**Architecture:** UI 线程独占 UIA；QueueStore 管理事务与批次；ModelWorker 仅处理普通数据；TypingSession 将键入拆为可逐步执行的动作。

**Tech Stack:** Python 标准库 sqlite3/threading、既有 uiautomation/Pillow/pytest。

**Spec:** docs/superpowers/specs/2026-10-17-main-inbox-queue-design.md

## Global Constraints

- 全会话监听；群聊只有明确 @机器人 的消息进入模型队列。
- 安静合并 3 秒，最长等待 10 秒；模型线程 1 个，每会话最多 1 批执行中。
- 不自动重启 wxbot、Butler 或 Hermes；不向真实微信发送测试消息。
- 结果不确定的模型请求与发送不自动重放；本阶段不改 Butler 协议或业务代码。
- 直接修改当前工作区并保留已有改动；不自动提交。

## Review Focus

- 连续相同正文也要保留；消息和快照必须在同一事务中落库。
- 分组成员、命令和不同用户不能混合；等待发送时不得抢跑该用户下一批。
- 模型阻塞不阻塞收件，打字期间不切会话或滚动抢焦点。
- UIA/网络结果未知、进程中断不能触发盲目重发。
- 首次未读任务必须先持久化，再点击清除角标。

## Tasks

- [x] 1. 创建 queue_store.py：收件、快照、未读任务、合并批次、发件及恢复；写行为测试并跑红绿。
- [x] 2. 创建 queue_worker.py：后台单线程处理，异常保留 uncertain；验证模型等待时可继续采集。
- [x] 3. 创建 wechat/typing.py，重用 ChatWindow.start_send；验证 5 字一批、1 秒间隔及目标变动阻断。
- [x] 4. 重写 MainInbox 为纯采集与 tick 驱动发送，持久化后才确认快照，整合启动/停止；更新原主窗口测试。
- [x] 5. 增加 queue_admin.py、配置与说明，验证缓存忽略、恢复和完整测试。

## Execution notes

- Ruling: 使用本地 SQLite + 不确定任务显式恢复，本阶段不自动重试可能已执行工具的请求；不需要修改或重启 Butler。
- Ruling: 同会话在旧批次回复得到发送确认前不开始下一批模型调用，保证上下文与交付顺序。
- Review fixes: 不可读控件不提交空快照；有明确未读时保留相同正文新消息；同名会话与类型变化停止收发；不可读草稿停止发送；采集失败不能阻止发件超时确认。
- 验证仅使用离线数据、假 UI 控件和本地测试 HTTP 服务；不向真实微信发送消息，不重启任何服务，不提交 Git。
- 最终验证：`python -m pytest` → 112 passed in 16.93s；`git diff --check` 无错误；Python 语法、示例 TOML、CLI help、数据库及 WAL/SHM/锁文件忽略规则均通过检查。
- 独立只读代码审查已核对四项修复，未发现剩余 Critical/Important/Minor；实际微信收发尚未验证，等待用户自行重启 wxbot 后观察。
