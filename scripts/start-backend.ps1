# Starts the FastAPI backend on http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "Run scripts\setup.ps1 first." -ForegroundColor Red; exit 1 }
if (-not (Test-Path (Join-Path $root ".env"))) { Write-Host "No .env found. Run scripts\setup.ps1 first." -ForegroundColor Red; exit 1 }
Set-Location (Join-Path $root "backend")
& $py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
