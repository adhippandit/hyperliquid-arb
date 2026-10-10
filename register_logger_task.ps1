# Run this once, elevated (right-click -> "Run with PowerShell as Administrator",
# or from an admin PowerShell: .\register_logger_task.ps1).
# Registers a Task Scheduler task that relaunches data_logger.py at boot
# (regardless of logon) and re-checks every 15 min if it's not running.
# logger_startup.ps1 already no-ops if the logger is already running, so the
# 15-min recheck is safe to fire even while a previous run is still alive.

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\milin\OneDrive\hyperliquid-arb\logger_startup.ps1"'

$trigger1 = New-ScheduledTaskTrigger -AtStartup
$trigger1.Delay = 'PT1M'

$trigger2 = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited

Register-ScheduledTask -TaskName "HyperliquidGapLogger" -Action $action -Trigger @($trigger1, $trigger2) `
    -Settings $settings -Principal $principal -Force `
    -Description "Auto-restarts data_logger.py at boot (1 min delay) and re-checks every 15 min if not running; logger_startup.ps1 no-ops if already running"

Write-Host "Task registered. Verifying..."
Get-ScheduledTask -TaskName "HyperliquidGapLogger" | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName "HyperliquidGapLogger" | Select-Object LastRunTime, LastTaskResult, NextRunTime
