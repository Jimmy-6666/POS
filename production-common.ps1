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
    [pscustomobject]@{
        InstallRoot = $resolvedInstallRoot
        RuntimeRoot = $resolvedRuntimeRoot
        Port = $Port
        Python = Join-Path $resolvedInstallRoot ".venv\Scripts\python.exe"
        LockFile = Join-Path $resolvedInstallRoot "requirements.lock.txt"
        StartScript = Join-Path $resolvedInstallRoot "start-production.ps1"
        TaskName = "SaengngamPOS-Production"
        FirewallName = "Saengngam POS Production TCP $Port"
        ReportDirectory = Join-Path $resolvedRuntimeRoot "support"
    }
}

function Set-ProductionEnvironment {
    param($Context)
    $env:POS_RUNTIME_ROOT = $Context.RuntimeRoot
    $env:POS_PORT = [string]$Context.Port
    $env:POS_BIND_HOST = "0.0.0.0"
    $env:POS_PRODUCTION = "1"
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

function Initialize-ProductionApplication {
    param($Context)
    Set-ProductionEnvironment $Context
    Invoke-Checked $Context.Python @("-c", "from pos_app import create_app; create_app()") "Database initialization or startup validation failed."
}

function Register-ProductionStartup {
    param($Context)
    $argument = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -InstallRoot "{1}" -RuntimeRoot "{2}" -Port {3}' -f $Context.StartScript, $Context.InstallRoot, $Context.RuntimeRoot, $Context.Port
    $action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument $argument -WorkingDirectory $Context.InstallRoot
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $Context.TaskName -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
}

function Remove-ProductionStartup {
    param($Context)
    Unregister-ScheduledTask -TaskName $Context.TaskName -Confirm:$false -ErrorAction SilentlyContinue
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
        task_name = $Context.TaskName
        firewall_rule = $Context.FirewallName
    }
    $file = Join-Path $Context.ReportDirectory ("installation-report-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")
    $report | ConvertTo-Json | Set-Content -LiteralPath $file -Encoding UTF8
    Write-Output "Installation report: $file"
}
