# 群昵称自动映射验证（2026-10-24）

主窗口从会话摘要读取「昵称: 消息」，与最后一条收到的消息全文核对，并在读取消息后再次检查摘要未变化，才保存该群内的成员 ID 到昵称映射。映射保存在收发队列数据库，沿用原成员 ID，不改变会话或记忆归属。手动配置昵称优先；未知昵称不添加 `@成员-<ID>` 前缀。队列结构从版本 7 升到 8，由下一次正常启动自动增加映射表。

只读检查当前微信确认：会话摘要包含发言人昵称，右侧消息条目没有单独的昵称控件。此实现不保证每条消息都能学习昵称：摘要截断、引用等格式造成全文不匹配、摘要变化或会话不可读时跳过学习，使用已有映射或不加 @。独立窗口模式仍依赖手动配置。

## 验证结果

- 相关测试：`python -m pytest tests/test_group_nickname_mapping.py tests/test_group_member_identity.py tests/test_main_window.py tests/test_queue_migration.py`，72 项通过。
- 完整测试：`python -m pytest`，547 项通过，4 项失败（见下）。
- 修改文件的 `git diff --check` 通过。
- 复核发现并修复了旧摘要给不同成员的相同正文错误建立映射的问题，新增摘要变化、会话消失回归测试。
- 未重启服务、未发送真实微信消息，未访问真实剪贴板；行为验证使用临时数据库和假投递。

## 已有失败

在临时源码副本中移除本次队列存储和结构改动后，以下四项仍以同样原因失败；本次没有修改其涉及的前端、投递状态策略或输入间隔行为。

| 测试 | 失败原因 |
| --- | --- |
| `test_log_frontend.py::test_monitor_rendering_request_races_and_navigation` | 前端检查期望数量 5，实际 6。 |
| `test_queue_admin.py::test_multipart_cli_sent_and_retry_preserve_other_parts` | 期望批次为 `waiting_delivery`，实际为 `done`。 |
| `test_queue_store.py::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker` | 期望批次为 `uncertain`，实际为 `done`。 |
| `test_typing.py::test_typing_steps_keep_half_second_between_batches_and_one_final_enter` | 测试期望批间隔 0.5 秒，当前行为使用 0.25 秒。 |
