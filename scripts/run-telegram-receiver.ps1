$ErrorActionPreference = 'Stop'

$python = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
$receiver = Join-Path $PSScriptRoot 'telegram-receiver.py'
$log = Join-Path $env:LOCALAPPDATA 'SpykeSpace\logs\telegram-receiver.log'
$backup = "$log.1"
$utf8 = [System.Text.UTF8Encoding]::new($false)

function Write-ReceiverLog($message) {
    $line = '[{0}] {1}{2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message, [Environment]::NewLine
    [System.IO.File]::AppendAllText($log, $line, $utf8)
}

try {
    if ((Test-Path $log) -and (Get-Item $log).Length -ge 5MB) {
        if (Test-Path $backup) {
            Remove-Item $backup -Force
        }
        Move-Item $log $backup
    }

    Write-ReceiverLog '=== Receiver launcher starting ==='

    & $python $receiver 2>&1 | ForEach-Object {
        Write-ReceiverLog $_.ToString()
    }

    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 1 }

    Write-ReceiverLog "Receiver exited with code $exitCode"
    exit $exitCode
}
catch {
    Write-ReceiverLog "Launcher failure: $($_.Exception.Message)"
    exit 1
}