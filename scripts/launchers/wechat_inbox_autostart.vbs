' WeChat inbox dashboard (8788) - hidden launcher for Startup folder / logon task.
' Real logic lives in ..\dashboard_startup.bat (single-instance guard included).
Option Explicit
Dim sh, Q, base
Set sh = CreateObject("WScript.Shell")
Q = Chr(34)
base = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)
sh.CurrentDirectory = base
sh.Run Q & base & "\dashboard_startup.bat" & Q, 0, False
