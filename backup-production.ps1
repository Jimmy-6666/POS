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
    if (-not (Test-Path -LiteralPath $context.Python)) {
        throw "Production virtual environment was not found."
    }
    Set-ProductionEnvironment $context
    Push-Location $context.InstallRoot
    try {
        & $context.Python -m pos_app.backup_cli backup-and-sync
        if ($LASTEXITCODE -ne 0) { throw "Scheduled backup or VPS sync failed." }
    } finally {
        Pop-Location
    }
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
