@echo off
REM WeChat inbox log service (8788) - hidden startup for watchdog / logon task.
REM Uses pythonw: no console window. Keep this file ASCII-only: cmd parses .bat as GBK.
REM
REM single-instance guard: if the port is already LISTENING, another instance is up -> skip.
netstat -ano | findstr /C:":8788" | findstr /I "LISTENING" >nul 2>&1 && exit /b 0

setlocal
set "ROOT=%~dp0.."
if "%HERMES_HOME%"=="" set "HERMES_HOME=%ROOT%\data"
set "LOGDIR=%HERMES_HOME%\logs\wechat-inbox"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
set "LOG=%LOGDIR%\service.log"

cd /d "%ROOT%"
if exist "%ROOT%\.venv\Scripts\pythonw.exe" (set "PYW=%ROOT%\.venv\Scripts\pythonw.exe") else (set "PYW=pythonw")
"%PYW%" -m dashboard.server --host 127.0.0.1 --port 8788 >> "%LOG%" 2>&1
endlocal
