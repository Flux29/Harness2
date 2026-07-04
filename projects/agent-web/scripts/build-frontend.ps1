# Rebuild the web UI into frontend\dist (served by FastAPI - PLAN Phase 1/4).
# Run after any frontend change: powershell -File scripts\build-frontend.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\frontend")
npm install --no-audit --no-fund
npm run build
Write-Host "Built. FastAPI serves it on next request (no restart needed)." -ForegroundColor Green
