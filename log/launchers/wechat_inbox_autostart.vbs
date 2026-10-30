' WeChat inbox log service (8788) - hidden launcher for Startup folder / logon task.
' Real logic lives in ..\log\wechat_inbox_startup.bat (single-instance guard included).
Option Explicit
Dim sh, Q, base
Set sh = CreateObject("WScript.Shell")
Q = Chr(34)
base = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)
base = Left(base, InStrRev(base, "\") - 1)
sh.CurrentDirectory = base
sh.Run Q & base & "\wechat_inbox_startup.bat" & Q, 0, False
