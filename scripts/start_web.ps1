$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

Push-Location frontend
try {
    $env:WRANGLER_LOG_PATH = '.wrangler/wrangler.log'
    & .\node_modules\.bin\vinext.cmd build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

$env:DLP_FRONTEND_DIST = Join-Path $projectRoot 'frontend\dist'
$repoRoot = Split-Path -Parent $projectRoot
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "找不到 Python 虚拟环境。已检查：$repoRoot\.venv 和 $projectRoot\.venv"
}
$env:PYTHONPATH = Join-Path $projectRoot 'src'
& $pythonExe -m uvicorn diagram_langgraph_pipeline.api.app:create_app `
    --factory --host 127.0.0.1 --port 8000
