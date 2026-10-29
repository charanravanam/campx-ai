# Opens two PowerShell windows: backend and frontend.
$here = $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-File","`"$here\start-backend.ps1`""
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-File","`"$here\start-frontend.ps1`""
Write-Host "Backend:  http://127.0.0.1:8000/health  (API docs: http://127.0.0.1:8000/docs)"
Write-Host "Frontend: http://localhost:5173"
