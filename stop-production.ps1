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
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match "pos_app\.launcher" -and
        $_.CommandLine -like "*$($context.InstallRoot)*"
    }
    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Stop-ScheduledTask -TaskName $context.TaskName -ErrorAction SilentlyContinue
    Write-Output "Production POS stopped."
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
