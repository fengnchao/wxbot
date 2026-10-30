@echo off
REM Dashboard (Vue at /app/). Config defaults come from config.log.toml;
REM environment variables and command-line flags can override them.
REM Run from the repository root so relative data paths resolve.
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"
if exist "%ROOT%\.venv\Scripts\python.exe" (set "PY=%ROOT%\.venv\Scripts\python.exe") else (set "PY=python")
"%PY%" -m dashboard.server --open
endlocal
