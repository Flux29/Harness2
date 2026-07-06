# Registers a Task Scheduler task (PLAN Phase 3): starts agent-web at logon,
# auto-restarts up to 3x on failure. Re-run any time to update. Remove with:
#   Unregister-ScheduledTask -TaskName "agent-web" -Confirm:$false
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
# Task Scheduler does not resolve commands via your shell PATH reliably -
# bake in the absolute path to uv.exe at registration time.
$uv = (Get-Command uv -ErrorAction Stop).Source
# --host 127.0.0.1 is the STATED bind invariant (plan step 5.3): the always-on
# service listens on loopback only — declared, not left to uvicorn's default.
$action   = New-ScheduledTaskAction -Execute $uv -Argument "run uvicorn agent_web.main:app --host 127.0.0.1 --port 8801" -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 0)
Register-ScheduledTask -TaskName "agent-web" -Action $action -Trigger $trigger -Settings $settings -Force
Write-Host "Task 'agent-web' registered - starts at every logon, self-restarts on failure." -ForegroundColor Green
Write-Host "Start it now with:  Start-ScheduledTask -TaskName agent-web"
