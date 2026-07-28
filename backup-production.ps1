param(
    [string]$InstallRoot,
    [string]$RuntimeRoot,
    [int]$Port = 8000,
    [switch]$LocalOnly,
    [switch]$FullRecoveryBundle
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "production-common.ps1")
try {
    Assert-Windows
    if ($LocalOnly -and $FullRecoveryBundle) {
        throw "Choose either -LocalOnly or -FullRecoveryBundle, not both."
    }
    $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
    if (-not (Test-Path -LiteralPath $context.Python)) {
        throw "Production virtual environment was not found."
    }
    Set-ProductionEnvironment $context
    Push-Location $context.InstallRoot
    try {
        $command = if ($FullRecoveryBundle) {
            "recovery-bundle"
        } elseif ($LocalOnly) {
            "backup"
        } else {
            "backup-and-sync"
        }
        & $context.Python -m pos_app.backup_cli $command
        $backupExitCode = $LASTEXITCODE
        if ((-not $FullRecoveryBundle) -and (-not $LocalOnly) -and ($backupExitCode -eq 2)) {
            Write-Warning "The verified local backup completed, but the VPS transfer or file sync failed."
            exit 2
        }
        if ($backupExitCode -ne 0) { throw "Scheduled local backup failed." }
    } finally {
        Pop-Location
    }
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
