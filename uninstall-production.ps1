param(
    [string]$InstallRoot,
    [string]$RuntimeRoot,
    [int]$Port = 8000,
    [switch]$KeepEnvironment
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "production-common.ps1")
try {
    Assert-Windows
    Assert-Administrator
    $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
    Remove-ProductionStartup $context
    Remove-ProductionBackupTask $context
    Remove-ProductionFirewall $context
    if (-not $KeepEnvironment) {
        $venv = Join-Path $context.InstallRoot ".venv"
        if (Test-Path -LiteralPath $venv) {
            Remove-Item -LiteralPath $venv -Recurse -Force
        }
    }
    Write-Output "Production startup and firewall registration removed."
    Write-Output "Database, secret key, uploads, backups, logs, and runtime configuration were preserved."
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
