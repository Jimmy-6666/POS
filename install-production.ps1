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
    # Daily backup timing is now controlled from the running POS Backup page.
    # Remove the legacy task so it cannot create a duplicate upload.
    Remove-ProductionBackupTask $context
    Set-ProductionFirewall $context
    Start-ScheduledTask -TaskName $context.TaskName
    if (-not (Test-ProductionHealth $context)) {
        throw "POS health check did not become ready."
    }
    Write-InstallationReport $context "ok" "Production installation completed."
    Write-Output "Production installation succeeded: http://127.0.0.1:$($context.Port)"
    Write-Output "Private-LAN POS URL: http://$($context.ServerIp):$($context.Port)"
    exit 0
} catch {
    if ($context) {
        Write-InstallationReport $context "failed" $_.Exception.Message
    }
    Write-Error $_.Exception.Message
    exit 1
}
