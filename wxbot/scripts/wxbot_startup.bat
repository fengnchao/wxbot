@echo off
REM wxbot 启动脚本（供开机自启 VBS 隐藏调用，也可手动双击）
REM 日志追加到 D:\ai\hermes\cache\wxbot.log
REM 前提：微信客户端已登录并保持打开；目标聊天为独立窗口、未最小化；电脑未锁屏。

REM single-instance guard: if the port is already LISTENING, another instance is up -> skip.
REM (Startup item + logon task + watchdog all hit this; without it you get duplicate instances.)
netstat -ano | findstr /C:":8765" | findstr /I "LISTENING" >nul 2>&1 && (echo [%DATE% %TIME%] wxbot_startup.bat: port 8765 already listening, skip >> "D:\ai\hermes\logs\wxbot\autostart.log" 2>nul & exit /b 0)
cd /d D:\ai\wxbot
set HERMES_HOME=D:\ai\hermes
set PYTHONDONTWRITEBYTECODE=1
REM 日志文件统一 UTF-8，否则 cmd 重定向会按 GBK 写、中文变乱码
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

"D:\ai\hermes\hermes-agent\venv\Scripts\python.exe" -m wxbot.main >> "D:\ai\hermes\cache\wxbot.log" 2>&1
