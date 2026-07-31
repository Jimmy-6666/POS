param(
    [string]$InstallRoot,
    [string]$RuntimeRoot,
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "production-common.ps1")
try {
    Assert-Windows
    $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
    Stop-ScheduledTask -TaskName $context.TaskName -ErrorAction SilentlyContinue
    Stop-ScheduledTask -TaskName $context.DesktopTaskName -ErrorAction SilentlyContinue
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match "(pos_app\.launcher|pos_desktop\.py)" -and
        $_.CommandLine -like "*$($context.InstallRoot)*"
    }
    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    $browserProfiles = @(
        (Join-Path $context.RuntimeRoot "browser-profile"),
        (Join-Path $context.RuntimeRoot "print-browser-profile"),
        (Join-Path $context.RuntimeRoot "pos-desktop\browser-profile"),
        (Join-Path $context.RuntimeRoot "pos-desktop\print-browser-profile")
    )
    $browserProcesses = Get-CimInstance Win32_Process | Where-Object {
        $commandLine = $_.CommandLine
        $_.Name -match "^(msedge|chrome)\.exe$" -and
        $commandLine -and
        ($browserProfiles | Where-Object { $commandLine -like "*$_*" })
    }
    foreach ($browserProcess in $browserProcesses) {
        Stop-Process -Id $browserProcess.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Output "Production POS stopped."
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
