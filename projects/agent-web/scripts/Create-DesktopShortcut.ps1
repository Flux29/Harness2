# Creates a Desktop shortcut to Start-AgentWeb.ps1 (PLAN Phase 2).
# Optional: -IconPath C:\path\to\icon.ico   (shortcuts need .ico, not .bmp/.png)
param([string]$IconPath = "")
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $ws.SpecialFolders("Desktop") "Agent Web.lnk"))
$lnk.TargetPath = "powershell.exe"
$lnk.Arguments  = "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSScriptRoot\Start-AgentWeb.ps1`""
$lnk.WorkingDirectory = Split-Path $PSScriptRoot -Parent
if ($IconPath -and (Test-Path $IconPath)) { $lnk.IconLocation = $IconPath }
$lnk.Save()
Write-Host "Desktop shortcut 'Agent Web' created." -ForegroundColor Green
