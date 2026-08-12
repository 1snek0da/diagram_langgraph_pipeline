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
& .\.venv\Scripts\python.exe -m uvicorn diagram_langgraph_pipeline.api.app:create_app `
    --factory --host 127.0.0.1 --port 8000
