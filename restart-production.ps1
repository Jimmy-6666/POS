param(
    [string]$InstallRoot,
    [string]$RuntimeRoot,
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "production-common.ps1")
try {
    $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
    $stopArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "stop-production.ps1"), "-InstallRoot", $context.InstallRoot, "-RuntimeRoot", $context.RuntimeRoot, "-Port", $context.Port)
    $stopProcess = Start-Process -FilePath "PowerShell.exe" -ArgumentList $stopArgs -WorkingDirectory $context.InstallRoot -Wait -PassThru
    if ($stopProcess.ExitCode -ne 0) { throw "Production stop failed before restart." }
    $task = Get-ScheduledTask -TaskName $context.TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        throw "Production desktop startup task is missing. Run repair-production.ps1 as Administrator."
    }
    Start-ScheduledTask -TaskName $context.TaskName
    if (-not (Test-ProductionHealth $context)) {
        throw "Production POS did not become healthy after restart."
    }
    Write-Output "Production POS restarted."
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
