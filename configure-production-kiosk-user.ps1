param(
    [string]$InstallRoot,
    [string]$RuntimeRoot,
    [int]$Port = 8000,
    [string]$AccountName = "POS",
    [switch]$StartServer
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "production-common.ps1")

function Set-KioskRootWriteDeny {
    param([string]$Path, [string]$UserName)
    & icacls.exe $Path /remove:d $UserName | Out-Null
    & icacls.exe $Path /deny "${UserName}:(OI)(CI)(WD,AD,WEA,WA,DC,DE,WDAC,WO)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to protect the installation root from POS writes: $Path."
    }
}

function Set-KioskPathAccess {
    param(
        [string]$Path,
        [string]$UserName,
        [ValidateSet("M", "RX")][string]$Rights,
        [switch]$Children
    )
    & icacls.exe $Path /inheritance:d | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to disable inherited ACLs on $Path."
    }
    & icacls.exe $Path /remove:g $UserName | Out-Null
    & icacls.exe $Path /remove:d $UserName | Out-Null
    $grant = if ($Children) { "(OI)(CI)$Rights" } else { $Rights }
    & icacls.exe $Path /grant:r "${UserName}:$grant" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to grant $Rights access to $UserName on $Path."
    }
}

try {
    Assert-Windows
    Assert-Administrator
    $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
    $account = Get-LocalUser -Name $AccountName -ErrorAction SilentlyContinue
    if (-not $account) {
        $account = New-LocalUser `
            -Name $AccountName `
            -NoPassword `
            -AccountNeverExpires `
            -UserMayNotChangePassword `
            -Description "Saengngam POS kiosk account"
    } else {
        Enable-LocalUser -Name $AccountName
        Set-LocalUser -Name $AccountName -PasswordNeverExpires $true
        if ($account.PasswordRequired) {
            throw "Local user $AccountName already exists with a password. Reset it explicitly before continuing."
        }
    }
    & net.exe user $AccountName /passwordchg:no /expires:never /active:yes | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to apply local POS account restrictions."
    }

    $usersGroup = Get-LocalGroup -SID "S-1-5-32-545"
    $administratorsGroup = Get-LocalGroup -SID "S-1-5-32-544"
    $account = Get-LocalUser -Name $AccountName -ErrorAction Stop
    $inUsers = Get-LocalGroupMember -Group $usersGroup -ErrorAction SilentlyContinue |
        Where-Object { $_.SID -eq $account.SID }
    if (-not $inUsers) {
        Add-LocalGroupMember -Group $usersGroup -Member $account
    }
    $inAdministrators = Get-LocalGroupMember -Group $administratorsGroup -ErrorAction SilentlyContinue |
        Where-Object { $_.SID -eq $account.SID }
    if ($inAdministrators) {
        Remove-LocalGroupMember -Group $administratorsGroup -Member $account
    }

    Ensure-RuntimeDirectories $context
    $null = Ensure-ProductionPrintAgentToken $context
    Ensure-ProductionDesktopPython $context
    $desktopRuntime = Join-Path $context.RuntimeRoot "pos-desktop"
    New-Item -ItemType Directory -Force -Path $desktopRuntime | Out-Null
    if (-not (Test-Path -LiteralPath $context.DisplayStateFile)) {
        [IO.File]::WriteAllText($context.DisplayStateFile, "{}", (New-Object Text.UTF8Encoding($false)))
    }

    $desktopUser = "$env:COMPUTERNAME\$AccountName"
    Set-KioskRootWriteDeny -Path $context.InstallRoot -UserName $desktopUser
    Set-KioskPathAccess -Path $desktopRuntime -UserName $desktopUser -Rights M -Children
    Set-KioskPathAccess -Path $context.PrintAgentTokenFile -UserName $desktopUser -Rights RX
    Set-KioskPathAccess -Path $context.DisplayStateFile -UserName $desktopUser -Rights M

    Register-ProductionStartup $context
    Register-ProductionDesktopStartup $context $desktopUser

    $publicDesktop = [Environment]::GetFolderPath("CommonDesktopDirectory")
    if (-not $publicDesktop) {
        $publicDesktop = Join-Path $env:PUBLIC "Desktop"
    }
    New-Item -ItemType Directory -Force -Path $publicDesktop | Out-Null
    $shortcutPath = Join-Path $publicDesktop "Saengngam POS.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "PowerShell.exe"
    $shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -InstallRoot "{1}" -RuntimeRoot "{2}" -Port {3} -Desktop -AttachOnly' -f $context.StartScript, $context.InstallRoot, $context.RuntimeRoot, $context.Port
    $shortcut.WorkingDirectory = $context.InstallRoot
    $shortcut.Description = "Open Saengngam POS launcher"
    $shortcut.IconLocation = "$($context.DesktopPythonw),0"
    $shortcut.Save()

    if ($StartServer) {
        Start-ScheduledTask -TaskName $context.TaskName
    }

    Write-Output "Local standard user created: $desktopUser"
    Write-Output "Production server task: $($context.TaskName) (SYSTEM, startup)"
    Write-Output "POS launcher task: $($context.DesktopTaskName) ($desktopUser, logon)"
    Write-Output "Desktop shortcut: $shortcutPath"
    exit 0
} catch {
    $errorDirectory = if ($context) { Join-Path $context.RuntimeRoot "logs" } else { Join-Path $PSScriptRoot "runtime\logs" }
    New-Item -ItemType Directory -Force -Path $errorDirectory -ErrorAction SilentlyContinue | Out-Null
    $errorPath = Join-Path $errorDirectory "kiosk-config-error.log"
    ($_ | Format-List * -Force | Out-String) | Set-Content -LiteralPath $errorPath -Encoding UTF8 -ErrorAction SilentlyContinue
    Write-Error $_.Exception.Message
    exit 1
}
