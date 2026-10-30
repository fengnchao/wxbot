@echo off
REM Dashboard (Vue at /app/). Config defaults come from config.log.toml;
REM environment variables and command-line flags can override them.
setlocal
set "ROOT=%~dp0.."
if exist "%ROOT%\.venv\Scripts\python.exe" (set "PY=%ROOT%\.venv\Scripts\python.exe") else (set "PY=python")
"%PY%" "%~dp0server.py" --open
endlocal
