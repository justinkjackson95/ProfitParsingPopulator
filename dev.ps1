# dev.ps1 - Start backend + frontend dev servers in separate PowerShell windows.
# Run from repo root:   .\dev.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$venvPython = Join-Path $root "backend\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Backend venv not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

$envFile = Join-Path $root "backend\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "backend\.env not found. Copy backend\.env.example to backend\.env and add your key." -ForegroundColor Red
    exit 1
}

# Backend: uvicorn with --env-file loads ANTHROPIC_API_KEY from backend\.env
$backendCmd = "cd '$root\backend'; & '$venvPython' -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload --env-file .env"
$frontendCmd = "cd '$root\frontend'; npm run dev"

Write-Host "Starting backend on http://localhost:8000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-Command",$backendCmd

Start-Sleep -Seconds 2

Write-Host "Starting frontend on http://localhost:5173 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-Command",$frontendCmd

Write-Host "`nBoth servers launching in new windows."
Write-Host "Open http://localhost:5173 in your browser."
Write-Host "Close the spawned windows (or Ctrl-C in them) to stop."
