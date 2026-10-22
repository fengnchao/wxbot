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
    }
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & .\.venv\Scripts\python.exe -m butler init
    if ($LASTEXITCODE -ne 0) { throw 'Initialization failed.' }
    Write-Output 'Next: .\.venv\Scripts\python.exe -m butler login'
    Write-Output 'Then: .\.venv\Scripts\python.exe -m butler doctor'
} finally { Pop-Location }
