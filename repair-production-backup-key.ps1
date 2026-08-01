param(
    [string]$InstallRoot,
    [string]$RuntimeRoot,
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "production-common.ps1")
try {
    Assert-Windows
    Assert-Administrator
    $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
    $result = Repair-ProductionVpsBackupSecrets $context
    if (-not $result.configured) {
        throw "Production VPS backup is not configured."
    }
    [pscustomobject]@{
        status = "complete"
        repaired = @($result.repaired | ForEach-Object { $_.label })
    } | ConvertTo-Json -Compress
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
