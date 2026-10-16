$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$env:HF_HOME = Join-Path (Split-Path -Parent $here) 'rag\outputs\hf_cache'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:PYTHONPATH = $here
if (-not $env:BCMID_API_HOST) { $env:BCMID_API_HOST = '127.0.0.1' }
if (-not $env:BCMID_API_PORT) { $env:BCMID_API_PORT = '8000' }

$python = $env:BCMID_PYTHON
if (-not $python) {
    $candidate = Join-Path $env:TEMP 'bcmid-notebook-runner\Scripts\python.exe'
    if (Test-Path $candidate) { $python = $candidate }
}
if (-not $python) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $python -or -not (Test-Path $python)) {
    throw 'Python was not found. Set BCMID_PYTHON to an environment containing agentic_local/requirements.txt.'
}
$preflight = "import importlib.util,sys; sys.exit(any(importlib.util.find_spec(name) is None for name in ('fastapi','chromadb','sentence_transformers','uvicorn')))"
& $python -c $preflight 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Python at $python is missing API/index dependencies. Set BCMID_PYTHON to the prepared notebook runner or install agentic_local/requirements.txt into a project environment."
}
Write-Host "Starting the local API with $python"
& $python -m uvicorn api:app --host $env:BCMID_API_HOST --port $env:BCMID_API_PORT
