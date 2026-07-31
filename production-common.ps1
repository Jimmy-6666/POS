$ErrorActionPreference = "Stop"

function Assert-Windows {
    if ($env:OS -ne "Windows_NT") {
        throw "This production command must run on supported Windows."
    }
    if ([Environment]::OSVersion.Version.Major -lt 10) {
        throw "Windows 10 or newer is required."
    }
}

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this command from an elevated PowerShell window."
    }
}

function Get-ProductionContext {
    param(
        [string]$InstallRoot,
        [string]$RuntimeRoot,
        [int]$Port = 8000
    )
    $resolvedInstallRoot = if ($InstallRoot) {
        [IO.Path]::GetFullPath($InstallRoot)
    } else {
        [IO.Path]::GetFullPath((Split-Path -Parent $PSCommandPath))
    }
    if (-not $RuntimeRoot) {
        $legacyDatabase = Join-Path $resolvedInstallRoot "data\pos.db"
        $releaseDatabase = Join-Path $resolvedInstallRoot "runtime\data\pos.db"
        $RuntimeRoot = if ((Test-Path -LiteralPath $legacyDatabase) -and -not (Test-Path -LiteralPath $releaseDatabase)) {
            $resolvedInstallRoot
        } else {
            Join-Path $resolvedInstallRoot "runtime"
        }
    }
    $resolvedRuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
    $desktopPythonRoot = Join-Path $resolvedInstallRoot "desktop-python"
    [pscustomobject]@{
        InstallRoot = $resolvedInstallRoot
        RuntimeRoot = $resolvedRuntimeRoot
        Port = $Port
        AppVersion = "3.0.9"
        ServerIp = "192.168.0.200"
        LanNetworks = "192.168.0.0/24"
        DefaultGateway = "192.168.0.1"
        DnsServers = @("8.8.8.8", "8.8.4.4")
        Python = Join-Path $resolvedInstallRoot ".venv\Scripts\python.exe"
        Pythonw = Join-Path $resolvedInstallRoot ".venv\Scripts\pythonw.exe"
        DesktopPythonRoot = $desktopPythonRoot
        DesktopPython = Join-Path $desktopPythonRoot "python.exe"
        DesktopPythonw = Join-Path $desktopPythonRoot "pythonw.exe"
        LockFile = Join-Path $resolvedInstallRoot "requirements.lock.txt"
        StartScript = Join-Path $resolvedInstallRoot "start-production.ps1"
        BackupScript = Join-Path $resolvedInstallRoot "backup-production.ps1"
        TaskName = "SaengngamPOS-Production"
        DesktopTaskName = "SaengngamPOS-Desktop"
        BackupTaskName = "SaengngamPOS-Backup"
        BackupTime = if ($env:POS_BACKUP_TIME) { $env:POS_BACKUP_TIME } else { "02:00" }
        FirewallName = "Saengngam POS Production TCP $Port"
        ReportDirectory = Join-Path $resolvedRuntimeRoot "support"
        PrintAgentTokenFile = Join-Path $resolvedRuntimeRoot "config\print-agent-token"
        DisplayStateFile = Join-Path $resolvedRuntimeRoot "pos-desktop\display_state.json"
    }
}

function Set-ProductionEnvironment {
    param($Context)
    $env:POS_RUNTIME_ROOT = $Context.RuntimeRoot
    $env:POS_PORT = [string]$Context.Port
    $env:POS_BIND_HOST = "0.0.0.0"
    $env:POS_PRODUCTION = "1"
    $env:POS_APP_VERSION = $Context.AppVersion
    $env:POS_SERVER_IP = $Context.ServerIp
    $env:POS_LAN_ACCESS_ENABLED = "1"
    $env:POS_LAN_NETWORKS = $Context.LanNetworks
    $env:POS_DISPLAY_STATE_FILE = $Context.DisplayStateFile
    if (Test-Path -LiteralPath $Context.PrintAgentTokenFile) {
        $token = (Get-Content -Raw -LiteralPath $Context.PrintAgentTokenFile).Trim()
        if ($token) {
            $env:POS_PRINT_AGENT_TOKEN = $token
        }
    }
    $trustedHosts = @(
        @($env:POS_TRUSTED_HOSTS -split ",") |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    )
    $env:POS_TRUSTED_HOSTS = (@($trustedHosts + $Context.ServerIp + "localhost" + "127.0.0.1") |
        Select-Object -Unique) -join ","
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$FailureMessage
    )
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Get-SupportedPython {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Python 3.11 or newer was not found."
    }
    $versionText = (& $command.Source --version 2>&1 | Out-String)
    if ($versionText -notmatch "Python\s+(\d+)\.(\d+)") {
        throw "Unable to read the Python version."
    }
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if (($major -lt 3) -or (($major -eq 3) -and ($minor -lt 11))) {
        throw "Python 3.11 or newer is required."
    }
    return $command.Source
}

function Ensure-RuntimeDirectories {
    param($Context)
    $directories = @(
        "data", "uploads", "uploads\products", "uploads\payments",
        "uploads\online-payments", "backups", "logs", "support",
        "staging", "releases", "browser-profile", "print-browser-profile", "config"
    )
    foreach ($relative in $directories) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Context.RuntimeRoot $relative) | Out-Null
    }
}

function Write-ProductionRuntimeConfig {
    param($Context)
    $configPath = Join-Path $Context.RuntimeRoot "config\production.json"
    $config = [ordered]@{}
    if (Test-Path -LiteralPath $configPath) {
        $existing = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
        foreach ($property in $existing.PSObject.Properties) {
            $config[$property.Name] = $property.Value
        }
    }
    $config["runtime_root"] = $Context.RuntimeRoot
    $config["bind_host"] = "0.0.0.0"
    $config["port"] = $Context.Port
    $config["app_version"] = $Context.AppVersion
    $config["production"] = $true
    $config["server_ip"] = $Context.ServerIp
    $config["lan_access_enabled"] = $true
    $config["lan_networks"] = $Context.LanNetworks
    $config["default_gateway"] = $Context.DefaultGateway
    $config["dns_servers"] = $Context.DnsServers
    $temporary = "$configPath.tmp"
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($temporary, ($config | ConvertTo-Json -Depth 10), $encoding)
    Move-Item -LiteralPath $temporary -Destination $configPath -Force
}

function Ensure-VirtualEnvironment {
    param($Context, [string]$SystemPython)
    if (-not (Test-Path -LiteralPath $Context.Python)) {
        Invoke-Checked $SystemPython @("-m", "venv", (Join-Path $Context.InstallRoot ".venv")) "Virtual environment creation failed."
    }
    if (-not (Test-Path -LiteralPath $Context.LockFile)) {
        throw "requirements.lock.txt was not found."
    }
    Invoke-Checked $Context.Python @("-m", "pip", "install", "--disable-pip-version-check", "-r", $Context.LockFile) "Locked dependency installation failed."
    Invoke-Checked $Context.Python @("-m", "pip", "check") "Installed dependency verification failed."
}

function Get-VirtualEnvironmentPythonHome {
    param($Context)
    $configuration = Join-Path $Context.InstallRoot ".venv\pyvenv.cfg"
    if (-not (Test-Path -LiteralPath $configuration)) {
        throw "Virtual environment configuration is missing: $configuration"
    }
    foreach ($line in Get-Content -LiteralPath $configuration) {
        $match = [regex]::Match($line, "^\s*home\s*=\s*(.+?)\s*$")
        if ($match.Success) {
            $pythonHome = [IO.Path]::GetFullPath($match.Groups[1].Value.Trim())
            if (-not (Test-Path -LiteralPath (Join-Path $pythonHome "pythonw.exe"))) {
                throw "Virtual environment Python home is incomplete: $pythonHome"
            }
            return $pythonHome
        }
    }
    throw "Virtual environment Python home was not found in $configuration."
}

function Test-ProductionDesktopPython {
    param($Context)
    if (-not (Test-Path -LiteralPath $Context.DesktopPython) -or -not (Test-Path -LiteralPath $Context.DesktopPythonw)) {
        return $false
    }

    $previousSmokeRoot = $env:POS_DESKTOP_SMOKE_ROOT
    $valid = $false
    try {
        $env:POS_DESKTOP_SMOKE_ROOT = $Context.InstallRoot
        $smokeOutput = @(& $Context.DesktopPython -I -B -c "import os, sys; sys.path.insert(0, os.environ['POS_DESKTOP_SMOKE_ROOT']); import pos_desktop; print('desktop-python-ok')" 2>&1)
        $valid = $LASTEXITCODE -eq 0 -and ($smokeOutput -join "`n") -match "desktop-python-ok"
    } catch {
        $valid = $false
    } finally {
        if ($null -eq $previousSmokeRoot) {
            Remove-Item Env:POS_DESKTOP_SMOKE_ROOT -ErrorAction SilentlyContinue
        } else {
            $env:POS_DESKTOP_SMOKE_ROOT = $previousSmokeRoot
        }
    }
    return $valid
}

function Ensure-ProductionDesktopPython {
    param($Context)
    if (Test-ProductionDesktopPython $Context) {
        return
    }

    $sourceRoot = Get-VirtualEnvironmentPythonHome $Context
    New-Item -ItemType Directory -Force -Path $Context.DesktopPythonRoot | Out-Null

    foreach ($directoryName in @("DLLs", "Lib", "tcl")) {
        $sourceDirectory = Join-Path $sourceRoot $directoryName
        if (-not (Test-Path -LiteralPath $sourceDirectory)) {
            throw "Desktop Python source directory is missing: $sourceDirectory"
        }
        $targetDirectory = Join-Path $Context.DesktopPythonRoot $directoryName
        New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null
        & robocopy.exe $sourceDirectory $targetDirectory /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) {
            throw "Unable to copy the shared desktop Python directory: $directoryName"
        }
    }

    $runtimeFiles = Get-ChildItem -LiteralPath $sourceRoot -File |
        Where-Object {
            $_.Name -match "^(python(?:w)?\.exe|python.*\.dll|vcruntime.*\.dll|LICENSE\.txt)$"
        }
    foreach ($runtimeFile in $runtimeFiles) {
        Copy-Item -LiteralPath $runtimeFile.FullName -Destination $Context.DesktopPythonRoot -Force
    }
    if (-not (Test-ProductionDesktopPython $Context)) {
        throw "Shared desktop Python validation failed after installation."
    }
}

function Initialize-ProductionApplication {
    param($Context)
    Set-ProductionEnvironment $Context
    Push-Location $Context.InstallRoot
    try {
        Invoke-Checked $Context.Python @("-c", "from pos_app import create_app; create_app()") "Database initialization or startup validation failed."
    } finally {
        Pop-Location
    }
}

function Ensure-ProductionPrintAgentToken {
    param($Context)
    $parent = Split-Path -Parent $Context.PrintAgentTokenFile
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if (-not (Test-Path -LiteralPath $Context.PrintAgentTokenFile)) {
        $bytes = New-Object byte[] 32
        $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $generator.GetBytes($bytes)
        } finally {
            $generator.Dispose()
        }
        $token = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
        [IO.File]::WriteAllText($Context.PrintAgentTokenFile, $token, (New-Object Text.ASCIIEncoding))
    }
    $existing = (Get-Content -Raw -LiteralPath $Context.PrintAgentTokenFile).Trim()
    if ($existing.Length -lt 32) {
        throw "Production print-agent token is missing or too short."
    }
    return $existing
}

function Get-ProductionDesktopUser {
    param([string]$DesktopUser)
    if ($DesktopUser) {
        return $DesktopUser
    }
    $consoleUser = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).UserName
    if ($consoleUser) {
        return $consoleUser
    }
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    if ($currentUser -and $currentUser -notmatch "\\SYSTEM$") {
        return $currentUser
    }
    throw "No interactive Windows user was found. Re-run with -DesktopUser DOMAIN\User while that user is signed in."
}

function Register-ProductionStartup {
    param($Context)
    $argument = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -InstallRoot "{1}" -RuntimeRoot "{2}" -Port {3}' -f $Context.StartScript, $Context.InstallRoot, $Context.RuntimeRoot, $Context.Port
    $action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument $argument -WorkingDirectory $Context.InstallRoot
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $Context.TaskName -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
}

function Register-ProductionDesktopStartup {
    param($Context, [string]$DesktopUser)
    $resolvedDesktopUser = Get-ProductionDesktopUser $DesktopUser
    $argument = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -InstallRoot "{1}" -RuntimeRoot "{2}" -Port {3} -Desktop -AttachOnly' -f $Context.StartScript, $Context.InstallRoot, $Context.RuntimeRoot, $Context.Port
    $action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument $argument -WorkingDirectory $Context.InstallRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $resolvedDesktopUser
    $principal = New-ScheduledTaskPrincipal -UserId $resolvedDesktopUser -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    $task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings
    Register-ScheduledTask -TaskName $Context.DesktopTaskName -InputObject $task -Force | Out-Null
}

function Remove-ProductionStartup {
    param($Context)
    Unregister-ScheduledTask -TaskName $Context.TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $Context.DesktopTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

function Register-ProductionBackupTask {
    param($Context)
    if (-not (Test-Path -LiteralPath $Context.BackupScript)) {
        throw "Backup runner was not found: $($Context.BackupScript)"
    }
    $runAt = [DateTime]::ParseExact($Context.BackupTime, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
    $argument = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -InstallRoot "{1}" -RuntimeRoot "{2}" -Port {3}' -f $Context.BackupScript, $Context.InstallRoot, $Context.RuntimeRoot, $Context.Port
    $action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument $argument -WorkingDirectory $Context.InstallRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $runAt
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15) -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::FromHours(2))
    Register-ScheduledTask -TaskName $Context.BackupTaskName -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
}

function Remove-ProductionBackupTask {
    param($Context)
    Unregister-ScheduledTask -TaskName $Context.BackupTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

function Set-ProductionFirewall {
    param($Context)
    Get-NetFirewallRule -DisplayName $Context.FirewallName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $Context.FirewallName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Context.Port -Profile Private -RemoteAddress LocalSubnet | Out-Null
}

function Remove-ProductionFirewall {
    param($Context)
    Get-NetFirewallRule -DisplayName $Context.FirewallName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}

function Test-ProductionFirewall {
    param($Context)
    $rule = Get-NetFirewallRule -DisplayName $Context.FirewallName -ErrorAction SilentlyContinue
    if (-not $rule) { return $false }
    $port = $rule | Get-NetFirewallPortFilter
    $address = $rule | Get-NetFirewallAddressFilter
    return (
        ($rule.Enabled -eq "True") -and
        ($rule.Direction -eq "Inbound") -and
        ($rule.Action -eq "Allow") -and
        ($rule.Profile -match "Private") -and
        ($port.Protocol -eq "TCP") -and
        ($port.LocalPort -eq [string]$Context.Port) -and
        ($address.RemoteAddress -contains "LocalSubnet")
    )
}

function Get-ProductionNetworkAdapter {
    param([string]$InterfaceAlias)
    if ($InterfaceAlias) {
        $adapter = Get-NetAdapter -Name $InterfaceAlias -ErrorAction Stop
        if ($adapter.Status -ne "Up") {
            throw "Selected network adapter is not connected: $InterfaceAlias"
        }
        return $adapter
    }
    $candidates = @(
        Get-NetIPConfiguration |
            Where-Object {
                $_.NetAdapter.Status -eq "Up" -and
                $_.IPv4Address -and
                $_.IPv4DefaultGateway
            }
    )
    if ($candidates.Count -ne 1) {
        throw "Unable to select one active LAN adapter. Re-run with -InterfaceAlias."
    }
    return $candidates[0].NetAdapter
}

function Set-ProductionServerNetwork {
    param(
        $Context,
        [string]$InterfaceAlias,
        [int]$PrefixLength = 24,
        [string]$DefaultGateway = "192.168.0.1",
        [string[]]$DnsServers = @("8.8.8.8", "8.8.4.4")
    )
    $adapter = Get-ProductionNetworkAdapter $InterfaceAlias
    $addresses = @(Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction Stop)
    $target = @($addresses | Where-Object { $_.IPAddress -eq $Context.ServerIp })
    if (-not $target) {
        $responds = Test-Connection -ComputerName $Context.ServerIp -Count 1 -Quiet -ErrorAction SilentlyContinue
        $neighbor = Get-NetNeighbor -InterfaceIndex $adapter.ifIndex -IPAddress $Context.ServerIp -ErrorAction SilentlyContinue
        $neighborInUse = $neighbor -and $neighbor.State -notin @("Unreachable", "Incomplete")
        if ($responds -or $neighborInUse) {
            throw "The fixed POS address $($Context.ServerIp) appears to be in use by another device."
        }
    }

    Set-NetIPInterface -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -Dhcp Disabled
    foreach ($address in $addresses) {
        if ($address.IPAddress -ne $Context.ServerIp -and $address.PrefixOrigin -ne "WellKnown") {
            Remove-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress $address.IPAddress -Confirm:$false
        }
    }
    if (-not $target -or $target[0].PrefixLength -ne $PrefixLength) {
        foreach ($address in $target) {
            Remove-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress $address.IPAddress -Confirm:$false
        }
        Get-NetRoute -InterfaceIndex $adapter.ifIndex -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
            Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
        New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress $Context.ServerIp -PrefixLength $PrefixLength -DefaultGateway $DefaultGateway | Out-Null
    } else {
        $defaultRoutes = @(Get-NetRoute -InterfaceIndex $adapter.ifIndex -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue)
        $defaultRoutes | Where-Object { $_.NextHop -ne $DefaultGateway } |
            Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
        if (-not ($defaultRoutes | Where-Object { $_.NextHop -eq $DefaultGateway })) {
            New-NetRoute -InterfaceIndex $adapter.ifIndex -DestinationPrefix "0.0.0.0/0" -NextHop $DefaultGateway | Out-Null
        }
    }
    Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses $DnsServers
    $profile = Get-NetConnectionProfile -InterfaceIndex $adapter.ifIndex -ErrorAction SilentlyContinue
    if ($profile -and $profile.NetworkCategory -ne "DomainAuthenticated") {
        $profile | Set-NetConnectionProfile -NetworkCategory Private
    }
    $verification = Get-ProductionServerNetworkStatus $Context $adapter.Name $PrefixLength $DefaultGateway $DnsServers
    if (-not $verification.ok) {
        throw "Static POS network verification failed: $($verification | ConvertTo-Json -Compress)"
    }
    return [pscustomobject]@{
        interface_alias = $adapter.Name
        server_ip = $Context.ServerIp
        prefix_length = $PrefixLength
        default_gateway = $DefaultGateway
        dns_servers = $DnsServers
    }
}

function Test-ProductionServerNetwork {
    param(
        $Context,
        [string]$InterfaceAlias,
        [int]$PrefixLength = 24,
        [string]$DefaultGateway = "192.168.0.1",
        [string[]]$DnsServers = @("8.8.8.8", "8.8.4.4")
    )
    return (Get-ProductionServerNetworkStatus $Context $InterfaceAlias $PrefixLength $DefaultGateway $DnsServers).ok
}

function Get-ProductionServerNetworkStatus {
    param(
        $Context,
        [string]$InterfaceAlias,
        [int]$PrefixLength = 24,
        [string]$DefaultGateway = "192.168.0.1",
        [string[]]$DnsServers = @("8.8.8.8", "8.8.4.4")
    )
    try {
        $adapter = Get-ProductionNetworkAdapter $InterfaceAlias
        $address = @(Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -IPAddress $Context.ServerIp -ErrorAction Stop) |
            Select-Object -First 1
        $route = @(Get-NetRoute -InterfaceIndex $adapter.ifIndex -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop |
            Where-Object { $_.NextHop -eq $DefaultGateway })
        $dns = @((Get-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction Stop).ServerAddresses)
        $missingDns = @($DnsServers | Where-Object { $_ -notin $dns })
        $profile = Get-NetConnectionProfile -InterfaceIndex $adapter.ifIndex -ErrorAction Stop
        $profileIsPrivate = $profile.NetworkCategory -in @("Private", "DomainAuthenticated")
        return [pscustomobject]@{
            ok = (
                [bool]$address -and
                ($address.PrefixLength -eq $PrefixLength) -and
                ($route.Count -gt 0) -and
                ($missingDns.Count -eq 0) -and
                $profileIsPrivate
            )
            interface_alias = $adapter.Name
            server_ip = if ($address) { $address.IPAddress } else { $null }
            prefix_length = if ($address) { $address.PrefixLength } else { $null }
            default_gateway = @($route | ForEach-Object { $_.NextHop })
            dns_servers = $dns
            missing_dns_servers = $missingDns
            network_category = $profile.NetworkCategory
        }
    } catch {
        return [pscustomobject]@{
            ok = $false
            error = $_.Exception.Message
        }
    }
}

function Test-ProductionHealth {
    param($Context, [int]$Attempts = 20)
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$($Context.Port)/health" -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $body = $response.Content | ConvertFrom-Json
                if ($body.status -eq "ok" -and $body.database -eq "ready") {
                    return $true
                }
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

function Write-InstallationReport {
    param($Context, [string]$Status, [string]$Detail = "")
    New-Item -ItemType Directory -Force -Path $Context.ReportDirectory | Out-Null
    $report = [ordered]@{
        status = $Status
        detail = $Detail
        created_at_utc = [DateTime]::UtcNow.ToString("o")
        install_root = $Context.InstallRoot
        runtime_root = $Context.RuntimeRoot
        port = $Context.Port
        server_ip = $Context.ServerIp
        lan_networks = $Context.LanNetworks
        lan_url = "http://$($Context.ServerIp):$($Context.Port)"
        task_name = $Context.TaskName
        desktop_task_name = $Context.DesktopTaskName
        firewall_rule = $Context.FirewallName
    }
    $file = Join-Path $Context.ReportDirectory ("installation-report-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")
    $report | ConvertTo-Json | Set-Content -LiteralPath $file -Encoding UTF8
    Write-Output "Installation report: $file"
}
