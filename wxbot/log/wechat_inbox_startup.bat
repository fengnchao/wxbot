@echo off
REM 微信收件日志服务（8788）—— 供看门狗/开机自启隐藏拉起
REM 用 pythonw：无控制台窗口。日志由服务自己写 logs\wechat-inbox\。
REM single-instance guard: if the port is already LISTENING, another instance is up -> skip.
REM (Startup item + logon task + watchdog all hit this; without it you get duplicate instances.)
netstat -ano | findstr /C:":8788" | findstr /I "LISTENING" >nul 2>&1 && (echo [%DATE% %TIME%] wechat_inbox_startup.bat: port 8788 already listening, skip >> "D:\ai\hermes\logs\wechat-inbox\autostart.log" 2>nul & exit /b 0)
set HERMES_HOME=D:\ai\hermes
cd /d D:\bot\log

REM pythonw 没有控制台，崩溃输出原先直接消失（2026-10-11 排查时正因此看不出死因）
REM 所以把 stdout/stderr 落到 service.log：崩了就有 traceback 可查。
set LOG=D:\ai\hermes\logs\wechat-inbox\service.log
"D:\ai\hermes\hermes-agent\venv\Scripts\pythonw.exe" server.py --host 127.0.0.1 --port 8788 >> "%LOG%" 2>&1
