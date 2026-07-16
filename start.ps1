$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
if (-not (Test-Path "frontend\node_modules")) { npm install --prefix frontend }
npm run build --prefix frontend
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

