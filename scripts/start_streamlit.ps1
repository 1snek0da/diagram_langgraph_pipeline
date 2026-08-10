$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not $env:DLP_API_BASE_URL) { $env:DLP_API_BASE_URL = 'http://127.0.0.1:8000' }
& .\.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
