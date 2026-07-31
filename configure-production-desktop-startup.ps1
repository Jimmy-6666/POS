param(
    [string]$InstallRoot,
    [string]$RuntimeRoot,
    [int]$Port = 8000,
    [string]$DesktopUser,
    [switch]$StartNow
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "production-common.ps1")
try {
    Assert-Windows
    Assert-Administrator
    $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
    Ensure-ProductionDesktopPython $context
    $desktopScript = Join-Path $context.InstallRoot "pos_desktop.py"
    if (-not (Test-Path -LiteralPath $desktopScript)) {
        throw "Production desktop launcher is missing: $desktopScript"
    }
    $null = Ensure-ProductionPrintAgentToken $context
    Register-ProductionStartup $context
    Register-ProductionDesktopStartup $context $DesktopUser
    $task = Get-ScheduledTask -TaskName $context.DesktopTaskName -ErrorAction Stop
    Write-Output "Production background startup task registered for SYSTEM."
    Write-Output "Production desktop startup task registered for $($task.Principal.UserId)."
    Write-Output "The launcher will start at that user's Windows logon."
    if ($StartNow) {
        Start-ScheduledTask -TaskName $context.TaskName
        Write-Output "Production background startup task started."
    }
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
