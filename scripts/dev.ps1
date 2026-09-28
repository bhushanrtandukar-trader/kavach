# Development mode: the API with auto-reload-friendly dev settings on :8050 and the Next.js dev server on :3100
# (which proxies /api to the API). Open http://localhost:3100. Ctrl+C stops the web server; close the API window.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Run .\scripts\setup.ps1 first.' }

Write-Host '==> Starting the API on http://127.0.0.1:8050 (new window)'
Start-Process -FilePath "$root\.venv\Scripts\python.exe" -ArgumentList '-m', 'guptakosh.api', '--dev' -WorkingDirectory $root

Write-Host '==> Starting the web UI on http://localhost:3100'
Push-Location frontend
try { npm run dev } finally { Pop-Location }
