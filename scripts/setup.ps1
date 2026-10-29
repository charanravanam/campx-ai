# One-time setup for Windows PowerShell.  Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Need($cmd, $hint) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Write-Host "MISSING: $cmd. $hint" -ForegroundColor Red; exit 1 }
}
Need "python" "Install Python 3.11+ from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')."
Need "node"   "Install Node.js LTS from https://nodejs.org/."
Need "npm"    "npm ships with Node.js."

Write-Host "==> Python version:" (python --version)
Write-Host "==> Creating virtual environment backend\.venv"
python -m venv backend\.venv
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
Write-Host "==> Installing backend dependencies"
& $py -m pip install -r backend\requirements.txt

if (-not (Test-Path ".env")) {
  Write-Host "==> Creating .env from .env.example with a random APP_SECRET_KEY"
  $secret = (& $py scripts\generate_secret.py).Trim()
  $lines = Get-Content ".env.example" | ForEach-Object { if ($_ -match '^APP_SECRET_KEY=') { "APP_SECRET_KEY=$secret" } else { $_ } }
  [System.IO.File]::WriteAllLines((Join-Path $root ".env"), $lines, (New-Object System.Text.UTF8Encoding $false))
} else {
  Write-Host "==> .env already exists - leaving it untouched"
}

Write-Host "==> Installing frontend dependencies"
Push-Location frontend
npm install
Pop-Location

Write-Host ""
Write-Host "Setup finished." -ForegroundColor Green
Write-Host "NEXT: open .env and set CAMPX_CLIENT_HEADER_VALUE (see README 'Finding X-Campx-Client'). Then run scripts\start-all.ps1"
