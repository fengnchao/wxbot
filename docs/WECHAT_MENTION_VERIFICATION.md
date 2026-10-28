# 群聊提及兼容修复验证（2026-10-28）

现场微信在点击唯一成员候选后，输入框的 ValuePattern 和 TextPattern 都只返回单个 U+FFFC，TextPattern.GetChildren 返回空列表。原代码要求一个嵌入子控件，导致 mention_verify 阻断，正文输入零字。

修复增加与本次候选点击、成员昵称和输入控件运行标识绑定的选择凭据；重新枚举确认选择器关闭。Qt 可能保留已离树却仍报告 Exists=True、IsOffscreen=False 的旧控件，不能用缓存控件判断候选框是否关闭。多个新候选框或列表抛出歧义错误，不授予凭据。

正文分批输入前后及回车前仍检查聊天目标、焦点、完整草稿前缀、单个对象和控件身份。原来能够读取嵌入对象的客户端继续使用对象身份校验。普通 @昵称文本不视为对象。

这版微信的编辑范围不含分隔符，但发送气泡包含 U+2005。仅在选择凭据路径且初始范围恰为单个 U+FFFC 时，为送达核验补齐该分隔符。

用户授权的真实测试使用指定群聊及失败记录中的同一成员，发送两条明确标注的功能测试文本。最终复测使用生产 MainChatWindow、TypingSession 和 reply_is_visible：6 批全部输入、mention_verified=True、enter_attempted=True、bubble_verified=True。未自动重启服务，未改动真实队列记录；运行中的 wxbot 仍需手动重启加载修改。

自动回归覆盖无子控件、旧选择器控件残留、多个候选框、控件替换、额外草稿/对象、完整分批正文和 Unicode 气泡分隔符。

最终完整回归：922 通过、3 失败，共 925 项，54.04 秒；提及测试文件 37 项全部通过。完整回归仍包含此前已确认的三个基线失败：

- tests/test_queue_admin.py::test_multipart_cli_sent_and_retry_preserve_other_parts
- tests/test_queue_store.py::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker
- tests/test_typing.py::test_typing_steps_keep_half_second_between_batches_and_one_final_enter
