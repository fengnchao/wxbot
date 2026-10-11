@echo off
REM Thin wrapper: start the WeChat bot stack (wxbot 8765 + wechat-inbox 8788).
REM Real logic lives in wechat_stack_ctl.py. This file is pure ASCII on purpose
REM (cmd parses .bat as GBK; UTF-8 CJK comments can swallow following lines).
chcp 65001 >nul
set HERMES_HOME=D:\ai\hermes
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title Hermes WeChat Bot - START
cls
echo ==========================================
echo   Hermes WeChat bot stack  --  STARTING
echo ==========================================
echo.
"D:\ai\hermes\hermes-agent\venv\Scripts\python.exe" "D:\bot\scripts\wechat_stack_ctl.py" start
echo.
echo (this window can be closed)
pause >nul
