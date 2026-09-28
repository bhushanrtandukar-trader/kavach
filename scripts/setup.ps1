# One-time setup. Everything installs INSIDE this project (.venv and frontend\node_modules),
# so nothing touches your global Python or your other projects.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path '.venv')) {
    Write-Host '==> Creating the Python virtual environment (.venv)'
    python -m venv .venv
}
Write-Host '==> Installing Python dependencies into .venv'
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements-dev.txt

Write-Host '==> Installing and building the web interface (frontend\node_modules)'
Push-Location frontend
try {
    npm ci --no-audit --no-fund
    npm run build
} finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Done.  Start Guptakosh with:  .\scripts\start.ps1'
