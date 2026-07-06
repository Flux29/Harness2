# Registers the nightly improve run (feat-improve-loop) as a current-user
# Task Scheduler job — the deterministic trigger the agent-callable improve
# tool lacks. Report-only: review state\improve\last-report.txt and apply
# manually (or add --apply here once the proposals have earned trust).
#
# Run once from any PowerShell:  .\scripts\Register-ImproveTask.ps1
# Remove with:                   Unregister-ScheduledTask Harness2-ImproveRun

$proj = Join-Path (Split-Path $PSScriptRoot -Parent) "projects\agent-web"
$report = Join-Path $proj "state\improve\last-report.txt"

$cmd = "Set-Location '$proj'; uv run python -m agent_web.improve_run --days 7 *> '$report'"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -Command `"$cmd`""
$trigger = New-ScheduledTaskTrigger -Daily -At 3:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName "Harness2-ImproveRun" `
    -Action $action -Trigger $trigger -Settings $settings -Force `
    -Description "Nightly agent-web improve run (report-only): analyzes state/history sessions, proposes context-file updates. feat-improve-loop."

Write-Host "Registered 'Harness2-ImproveRun' (daily 03:00, report-only)."
Write-Host "Report lands in $report"
