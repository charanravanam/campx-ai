# Runs the backend test suite and a frontend production build.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
Set-Location (Join-Path $root "backend")
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Set-Location (Join-Path $root "frontend")
npm run build
