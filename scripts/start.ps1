# Run Guptakosh (API + the built web UI) on http://127.0.0.1:8050
param([int]$Port = 8050)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Run .\scripts\setup.ps1 first.' }
if (-not (Test-Path 'frontend\out\index.html')) { Write-Warning 'The web interface is not built yet: run .\scripts\setup.ps1 (or "npm run build" in frontend).' }
$env:GUPTAKOSH_PORT = "$Port"
& .\.venv\Scripts\python.exe -m guptakosh
