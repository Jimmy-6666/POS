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
    $systemPython = Get-SupportedPython
    Ensure-RuntimeDirectories $context
    $null = Ensure-ProductionPrintAgentToken $context
    Write-ProductionRuntimeConfig $context
    try {
        $backupSecretRepair = Repair-ProductionVpsBackupSecrets $context
        if ($backupSecretRepair.configured) {
            Write-Output "Production VPS backup key ownership and ACL repaired for SYSTEM."
        }
    } catch {
        Write-Warning "Production VPS backup secret repair failed; local POS startup will continue: $($_.Exception.Message)"
    }
    Ensure-VirtualEnvironment $context $systemPython
    Initialize-ProductionApplication $context
    Register-ProductionStartup $context
    Remove-ProductionBackupTask $context
    Set-ProductionFirewall $context
    Write-Output "Production repair completed. Database and secret key were preserved."
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
