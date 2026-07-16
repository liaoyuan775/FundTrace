$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root'; python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload" -WindowStyle Hidden -PassThru
try { Set-Location "$Root\frontend"; npm run dev } finally { Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue }

