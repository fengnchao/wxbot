' wxbot - hidden launcher for the Startup folder / logon task.
' Real logic lives in ..\wxbot_startup.bat (single-instance guard included).
' Prerequisite: WeChat is logged in; the target chat window is visible; machine unlocked.
Option Explicit
Dim sh, Q, base
Set sh = CreateObject("WScript.Shell")
Q = Chr(34)
base = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)
sh.CurrentDirectory = base
sh.Run "cmd /c " & Q & base & "\wxbot_startup.bat" & Q, 0, False
