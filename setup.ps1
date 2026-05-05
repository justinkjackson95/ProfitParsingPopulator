# setup.ps1 - One-time install of backend (Python venv) and frontend (npm) deps.
# Run from repo root:   .\setup.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "==> Checking prerequisites" -ForegroundColor Cyan
function Require-Cmd($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: '$name' not found on PATH. Install it and re-run." -ForegroundColor Red
        exit 1
    }
}
Require-Cmd python
Require-Cmd node
Require-Cmd npm
Write-Host "    python: $(python --version)"
Write-Host "    node:   $(node --version)"
Write-Host "    npm:    $(npm --version)"

Write-Host "`n==> Setting up backend venv" -ForegroundColor Cyan
$venv = Join-Path $root "backend\venv"
if (-not (Test-Path $venv)) {
    python -m venv $venv
    Write-Host "    created $venv"
} else {
    Write-Host "    venv already exists, reusing"
}

$venvPip = Join-Path $venv "Scripts\pip.exe"
& $venvPip install --upgrade pip
& $venvPip install -r (Join-Path $root "backend\requirements.txt")

Write-Host "`n==> Installing frontend dependencies" -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend")
try {
    npm install
} finally {
    Pop-Location
}

Write-Host "`n==> Done." -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  1. Open backend\.env and paste your ANTHROPIC_API_KEY"
Write-Host "  2. Run .\dev.ps1 to start both servers"
