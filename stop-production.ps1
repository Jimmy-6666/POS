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

    # Stop only a remaining listener on the requested Production port. A UAT
    # checkout may live below InstallRoot and must not be matched by a broad
    # pos_app.launcher command-line search.
    $listenerPids = @(Get-NetTCPConnection -LocalPort $context.Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($listenerPid in $listenerPids) {
        Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
    }

    # The Production desktop launcher is tied to its exact root script. This
    # avoids closing an isolated UAT launcher under staging/.
    $desktopScript = Join-Path $context.InstallRoot "pos_desktop.py"
    $desktopProcesses = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match "pos_desktop\.py" -and
        $_.CommandLine -like "*$desktopScript*"
    }
    foreach ($desktopProcess in $desktopProcesses) {
        Stop-Process -Id $desktopProcess.ProcessId -Force -ErrorAction SilentlyContinue
    }

    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 500
        $remainingListeners = @(Get-NetTCPConnection -LocalPort $context.Port -State Listen -ErrorAction SilentlyContinue)
    } while ($remainingListeners.Count -gt 0 -and (Get-Date) -lt $deadline)
    if ($remainingListeners.Count -gt 0) {
        throw "Production port $($context.Port) did not stop cleanly."
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
