Set-Location "C:\Users\milin\OneDrive\hyperliquid-arb"

$logFile = "logger_output.log"
$staleMinutes = 12  # normal log cadence is ~5-6 min; anything older means the loop is stuck

# Add-Content (UTF8) and python's stdout redirection used to write to this file with
# different encodings/stream-wrapping (PowerShell's `*>>` boxes native stderr lines as
# ErrorRecord objects), which interleaved into garbled, unreadable log text. Both writers
# now use plain UTF8 appends so the file stays consistent.
function Write-Log($msg) {
    Add-Content -Path $logFile -Value "$(Get-Date) - $msg" -Encoding utf8
}

$already = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*data_logger.py*' }

if ($already) {
    $isStale = $false
    if (Test-Path $logFile) {
        $age = (Get-Date) - (Get-Item $logFile).LastWriteTime
        if ($age.TotalMinutes -gt $staleMinutes) { $isStale = $true }
    }

    if (-not $isStale) {
        # The running logger holds logger_output.log open via *>>, so this write
        # routinely collides with it (every 15-min recheck) — non-fatal, just skip logging it.
        try { Write-Log "data_logger.py already running (PID $($already.ProcessId)), skipping startup" } catch {}
        exit
    }

    # Process is alive but hasn't written a log line in $staleMinutes — treat as hung and
    # replace it. A stuck logger silently stops collecting data (real outage seen 2026-09-15/16:
    # a hung instance kept the scheduler's "IgnoreNew" policy from ever re-triggering).
    try { Write-Log "data_logger.py PID $($already.ProcessId) appears hung (no log activity in $([int]$age.TotalMinutes) min), killing and restarting" } catch {}
    foreach ($proc in $already) {
        try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop } catch {
            try { Write-Log "failed to kill PID $($proc.ProcessId): $_" } catch {}
        }
    }
    Start-Sleep -Seconds 2
}

Write-Log "starting data_logger.py"

# Run via cmd.exe rather than PowerShell's native `*>>` redirection: cmd passes stdout/stderr
# through as plain bytes, whereas PowerShell wraps a native process's stderr lines as
# ErrorRecord objects (rendered as multi-line "NativeCommandError" blocks) and writes with a
# different text encoding than Add-Content above — the combination was what corrupted the log.
$env:PYTHONIOENCODING = "utf-8"
$escapedLog = $logFile.Replace('"', '""')
# Launch detached (no -Wait) so this script exits immediately. If it waited on the logger,
# the task instance would stay "Running" for the logger's whole life and IgnoreNew would
# refuse every 15-min recheck (0x800710E0), so the hang check above could never fire.
Start-Process -FilePath "cmd.exe" -WindowStyle Hidden -WorkingDirectory (Get-Location).Path `
    -ArgumentList "/c `"`"C:\Python313\python.exe`" `"data_logger.py`" >> `"$escapedLog`" 2>&1`""
