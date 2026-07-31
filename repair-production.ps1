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
