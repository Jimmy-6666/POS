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
    $null = Get-SupportedPython
    if (-not (Test-Path -LiteralPath $context.Python)) { throw "Virtual environment is missing." }
    if (-not (Test-Path -LiteralPath $context.LockFile)) { throw "requirements.lock.txt is missing." }
    Set-ProductionEnvironment $context
    $json = & $context.Python -m pos_app.runtime_check --json
    if ($LASTEXITCODE -ne 0) { throw "Runtime validation failed: $json" }
    $report = $json | ConvertFrom-Json
    if (-not $report.ok) { throw "Runtime validation failed." }
    $task = Get-ScheduledTask -TaskName $context.TaskName -ErrorAction SilentlyContinue
    if (-not $task) { throw "Automatic startup task is missing." }
    $backupTask = Get-ScheduledTask -TaskName $context.BackupTaskName -ErrorAction SilentlyContinue
    if (-not $backupTask) { throw "Automatic backup task is missing." }
    if (-not (Test-ProductionFirewall $context)) { throw "Private-LAN firewall rule is missing or unsafe." }
    if (-not (Test-ProductionHealth $context -Attempts 3)) { throw "Health endpoint is not ready." }
    Write-Output "Production verification passed."
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
