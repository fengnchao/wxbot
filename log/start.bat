@echo off
REM 配置默认值从 config.log.toml 读取；环境变量和命令行可覆盖。
setlocal
python "%~dp0server.py" --open
endlocal
