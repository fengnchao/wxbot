@echo off
REM Thin wrapper: stop the WeChat bot stack (wxbot 8765 + wechat-inbox 8788).
REM Real logic lives in wechat_stack_ctl.py. Pure ASCII on purpose:
REM cmd parses .bat as GBK, UTF-8 CJK comments can swallow following lines.
chcp 65001 >nul
setlocal
set "ROOT=%~dp0.."
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
if exist "%ROOT%\.venv\Scripts\python.exe" (set "PY=%ROOT%\.venv\Scripts\python.exe") else (set "PY=python")
title Hermes WeChat Bot - STOP
cls
echo ==========================================
echo   Hermes WeChat bot stack  --  STOPPING
echo ==========================================
echo.
"%PY%" "%~dp0wechat_stack_ctl.py" stop
echo.
echo (this window can be closed)
pause >nul
endlocal
