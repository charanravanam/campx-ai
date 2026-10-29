# Starts the React dev server on http://localhost:5173 (proxies /api to the backend)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "frontend")
if (-not (Test-Path "node_modules")) { Write-Host "Run scripts\setup.ps1 first." -ForegroundColor Red; exit 1 }
npm run dev
