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
    Ensure-VirtualEnvironment $context $systemPython
    Initialize-ProductionApplication $context
    Register-ProductionStartup $context
    Set-ProductionFirewall $context
    $startArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $context.StartScript, "-InstallRoot", $context.InstallRoot, "-RuntimeRoot", $context.RuntimeRoot, "-Port", $context.Port)
    Start-Process -FilePath "PowerShell.exe" -ArgumentList $startArgs -WorkingDirectory $context.InstallRoot
    if (-not (Test-ProductionHealth $context)) {
        throw "POS health check did not become ready."
    }
    Write-InstallationReport $context "ok" "Production installation completed."
    Write-Output "Production installation succeeded: http://127.0.0.1:$($context.Port)"
    exit 0
} catch {
    if ($context) {
        Write-InstallationReport $context "failed" $_.Exception.Message
    }
    Write-Error $_.Exception.Message
    exit 1
}
