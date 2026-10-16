$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'The local UI environment is missing. Create .venv and install requirements.txt first.' }
& $python -m streamlit run app.py --server.headless true
