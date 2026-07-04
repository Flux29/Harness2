# One-click launcher (PLAN Phase 2): ensures the server is up, opens the app.
# Safe to run any time; does nothing but open the browser if already running.
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path $PSScriptRoot -Parent
$url  = "http://localhost:8801"

function Test-Health { try { (Invoke-WebRequest "$url/healthz" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 } catch { $false } }

if (-not (Test-Health)) {
    Write-Host "Starting agent-web server..."
    Start-Process -FilePath "uv" -ArgumentList "run","uvicorn","agent_web.main:app","--port","8801" `
        -WorkingDirectory $root -WindowStyle Hidden
    $tries = 0
    while (-not (Test-Health) -and $tries -lt 90) { Start-Sleep -Seconds 1; $tries++ }  # cold start builds the agent + MCP handshakes
    if (-not (Test-Health)) { Write-Host "Not healthy after 90s. Diagnose with: uv run uvicorn agent_web.main:app --port 8801 (port-in-use error = a server IS already running)" -ForegroundColor Red; exit 1 }
}
Start-Process $url
