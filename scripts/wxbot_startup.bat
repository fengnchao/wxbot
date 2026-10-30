@echo off
REM wxbot launcher (called hidden by the logon task; can also be double-clicked).
REM Prerequisite: WeChat is logged in and open; target chat window visible, machine unlocked.
REM Keep this file ASCII-only: cmd parses .bat as GBK.
setlocal
set "ROOT=%~dp0.."

REM single-instance guard: if 8765 is already LISTENING, another instance is up -> skip.
netstat -ano | findstr /C:":8765" | findstr /I "LISTENING" >nul 2>&1 && exit /b 0

if "%HERMES_HOME%"=="" set "HERMES_HOME=%ROOT%\data"
set "LOGDIR=%HERMES_HOME%\cache"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1

set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
cd /d "%ROOT%"
if exist "%ROOT%\.venv\Scripts\python.exe" (set "PY=%ROOT%\.venv\Scripts\python.exe") else (set "PY=python")
"%PY%" -m wxbot.main >> "%LOGDIR%\wxbot.log" 2>&1
endlocal
