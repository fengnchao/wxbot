' wxbot —— 开机自启 / 登录计划任务 的启动器（隐藏窗口，不弹黑框）
' 真正逻辑在 D:\bot\scripts\wxbot_startup.bat（内含单实例护栏）。
'
' 前提（否则起来也没用）：1) 微信客户端已登录并保持运行 2) 目标聊天已打开为独立窗口、未最小化
'                          3) 电脑未锁屏（锁屏后 UI 自动化点不到控件）
' 日志：D:\ai\hermes\cache\wxbot.log    状态：python D:\bot\scripts\wxbot_run.py --status

Set sh = CreateObject("WScript.Shell")
Q = Chr(34)
sh.Environment("PROCESS")("HERMES_HOME") = "D:\ai\hermes"
sh.CurrentDirectory = "D:\ai\wxbot"
sh.Run "cmd /c " & Q & "D:\bot\scripts\wxbot_startup.bat" & Q, 0, False
