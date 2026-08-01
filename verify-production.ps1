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
    if (-not (Test-Path -LiteralPath $context.Python)) { throw "Virtual environment is missing." }
    if (-not (Test-ProductionDesktopPython $context)) { throw "Shared desktop Python environment is missing or invalid." }
    if (-not (Test-Path -LiteralPath $context.LockFile)) { throw "requirements.lock.txt is missing." }
    Set-ProductionEnvironment $context
    Push-Location $context.InstallRoot
    try {
        $runtimeOutput = @(& $context.Python -m pos_app.runtime_check --json 2>&1)
        $runtimeExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    $json = $runtimeOutput -join [Environment]::NewLine
    if ($runtimeExitCode -ne 0) { throw "Runtime validation failed with exit code ${runtimeExitCode}: $json" }
    $report = $json | ConvertFrom-Json
    if (-not $report.ok) { throw "Runtime validation failed." }
    if ($report.app_version -ne $context.AppVersion) {
        throw "Runtime version mismatch: expected $($context.AppVersion), found $($report.app_version)."
    }
    $task = Get-ScheduledTask -TaskName $context.TaskName -ErrorAction SilentlyContinue
    if (-not $task) { throw "Automatic startup task is missing." }
    if ($task.Principal.UserId -notmatch "(^|\\)SYSTEM$" -or $task.Principal.LogonType -ne "ServiceAccount") {
        throw "Production server startup task must run in the SYSTEM service context."
    }
    if (-not ($task.Triggers | Where-Object { $_.CimClass.CimClassName -eq "MSFT_TaskBootTrigger" })) {
        throw "Production server startup task must use a Windows startup trigger."
    }
    if ($task.Actions | Where-Object { $_.Arguments -match "(^|\s)-Desktop(\s|$)" }) {
        throw "Production server task must not launch the desktop UI."
    }
    $desktopTask = Get-ScheduledTask -TaskName $context.DesktopTaskName -ErrorAction SilentlyContinue
    if (-not $desktopTask) { throw "POS desktop launcher task is missing." }
    if ($desktopTask.Principal.UserId -match "(^|\\)SYSTEM$" -or $desktopTask.Principal.LogonType -ne "Interactive") {
        throw "POS desktop launcher task must run as a signed-in standard user."
    }
    if (-not ($desktopTask.Triggers | Where-Object { $_.CimClass.CimClassName -eq "MSFT_TaskLogonTrigger" })) {
        throw "POS desktop launcher task must use an interactive logon trigger."
    }
    if (-not ($desktopTask.Actions | Where-Object { $_.Arguments -match "(^|\s)-Desktop(\s|$)" -and $_.Arguments -match "(^|\s)-AttachOnly(\s|$)" })) {
        throw "POS desktop launcher task must attach to the background server."
    }
    if (-not (Test-Path -LiteralPath $context.PrintAgentTokenFile)) {
        throw "Production print-agent token is missing."
    }
    $backupTask = Get-ScheduledTask -TaskName $context.BackupTaskName -ErrorAction SilentlyContinue
    if ($backupTask) { throw "Legacy backup task is still registered and may create duplicate backups." }
    if (-not $report.checks.backup_schedule.ok) { throw "In-process backup schedule is invalid." }
    $backupSecretStatus = Test-ProductionVpsBackupSecrets $context
    if (-not $backupSecretStatus.ok) {
        throw "Production VPS backup secret validation failed: $($backupSecretStatus.issues -join '; ')"
    }
    if (-not $report.lan_access_enabled) { throw "Private-LAN staff access is disabled." }
    if ($report.server_ip -ne $context.ServerIp) { throw "Runtime server IP does not match $($context.ServerIp)." }
    if (-not (Test-ProductionServerNetwork $context)) { throw "Static POS network configuration is missing or incorrect." }
    if (-not (Test-ProductionFirewall $context)) { throw "Private-LAN firewall rule is missing or unsafe." }
    if (-not (Test-ProductionHealth $context -Attempts 3)) { throw "Health endpoint is not ready." }
    Write-Output "Production verification passed."
    exit 0
} catch {
    $errorDirectory = if ($context) { Join-Path $context.RuntimeRoot "logs" } else { Join-Path $PSScriptRoot "runtime\logs" }
    New-Item -ItemType Directory -Force -Path $errorDirectory -ErrorAction SilentlyContinue | Out-Null
    $errorPath = Join-Path $errorDirectory "production-verify-error.log"
    ($_ | Format-List * -Force | Out-String) | Set-Content -LiteralPath $errorPath -Encoding UTF8 -ErrorAction SilentlyContinue
    Write-Error $_.Exception.Message
    exit 1
}
