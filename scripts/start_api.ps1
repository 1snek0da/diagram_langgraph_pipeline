$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& .\.venv\Scripts\python.exe -m uvicorn diagram_langgraph_pipeline.api.app:create_app --factory --host 127.0.0.1 --port 8000
