param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
Push-Location -LiteralPath $resolvedRoot
try {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv sync --locked --extra dev
    } else {
        if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
            & py -3.14 -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Python 3.14 is required. Install it or use uv.' }
        }
        & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
        if ($LASTEXITCODE -eq 0) { & .\.venv\Scripts\python.exe -m pip install -e . --no-deps }
    }
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & .\.venv\Scripts\python.exe -m butler setup
    if ($LASTEXITCODE -ne 0) { throw 'Initialization failed.' }
    Write-Output '使用上面安装向导提供的登录、诊断和启动命令。已有安装可运行 python -m butler migrate 升级用户目录。'
} finally { Pop-Location }
