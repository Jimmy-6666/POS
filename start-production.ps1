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
        throw "Production virtual environment was not found. Run install-production.ps1 or repair-production.ps1."
    }
    Ensure-RuntimeDirectories $context
    Set-ProductionEnvironment $context
    if (Test-ProductionHealth $context -Attempts 1) {
        Write-Output "Production POS is already running."
        exit 0
    }
    Push-Location $context.InstallRoot
    try {
        & $context.Python -m pos_app.launcher
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
