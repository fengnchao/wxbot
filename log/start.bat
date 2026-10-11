@echo off
REM 微信收件日志 — 只读，按发送人分组。不改动任何现有数据。
setlocal
set HERMES_HOME=D:\ai\hermes
set PORT=8788
echo [wechat-inbox] 启动中... http://127.0.0.1:%PORT%/
start "" http://127.0.0.1:%PORT%/
python "%~dp0server.py" --host 127.0.0.1 --port %PORT%
endlocal
