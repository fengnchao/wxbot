' 微信管家日志服务（8788）—— 开机自启 / 登录计划任务 的启动器（隐藏窗口）
' 真正逻辑在 D:\bot\log\wechat_inbox_startup.bat（内含单实例护栏）。
Set sh = CreateObject("WScript.Shell")
Q = Chr(34)
sh.CurrentDirectory = "D:\bot\log"
sh.Environment("PROCESS")("HERMES_HOME") = "D:\ai\hermes"
sh.Run Q & "D:\bot\log\wechat_inbox_startup.bat" & Q, 0, False
