param(
    [string]$InstallRoot,
    [string]$RuntimeRoot,
    [int]$Port = 8002,
    [string]$InterfaceAlias,
    [int]$PrefixLength = 24,
    [string]$DefaultGateway = "192.168.0.1",
    [string[]]$DnsServers = @("8.8.8.8", "8.8.4.4")
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "production-common.ps1")
try {
    Assert-Windows
    Assert-Administrator
    $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
    Ensure-RuntimeDirectories $context
    Write-ProductionRuntimeConfig $context
    Set-ProductionFirewall $context
    $network = Set-ProductionServerNetwork $context $InterfaceAlias $PrefixLength $DefaultGateway $DnsServers
    Write-InstallationReport $context "ok" "Static server IP and private-LAN POS access configured."
    Write-Output "Network adapter: $($network.interface_alias)"
    Write-Output "Static POS address: $($network.server_ip)/$($network.prefix_length)"
    Write-Output "Private-LAN POS URL: http://$($context.ServerIp):$($context.Port)"
    exit 0
} catch {
    if ($context) {
        Write-InstallationReport $context "failed" $_.Exception.Message
    }
    Write-Error ($_.Exception.Message + [Environment]::NewLine + $_.ScriptStackTrace)
    exit 1
}
