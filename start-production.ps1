param(
    [string]$InstallRoot,
    [string]$RuntimeRoot,
    [int]$Port = 8000,
    [switch]$Desktop,
    [switch]$AttachOnly
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "production-common.ps1")
try {
    Assert-Windows
    $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
    if (-not $Desktop) {
        # SYSTEM can execute the locked production venv.  A standard-user
        # fallback task may be unable to launch that venv because of its ACL;
        # use the shared read-only runtime with the same site-packages so a
        # reboot still brings the POS back up and keeps the printer usable.
        $pythonRunnable = $false
        if (Test-Path -LiteralPath $context.Python) {
            try {
                $null = & $context.Python -B -c "import sys" 2>$null
                $pythonRunnable = ($LASTEXITCODE -eq 0)
            } catch {
                $pythonRunnable = $false
            }
        }
        if (-not $pythonRunnable) {
            if (-not (Test-Path -LiteralPath $context.DesktopPython)) {
                throw "Production Python runtime was not found or cannot be launched. Run install-production.ps1 or repair-production.ps1."
            }
            $context.Python = $context.DesktopPython
            $env:PYTHONPATH = Join-Path $context.InstallRoot ".venv\Lib\site-packages"
        }
    }
    if ($Desktop -and $AttachOnly) {
        if (-not (Test-Path -LiteralPath $context.PrintAgentTokenFile)) {
            throw "Production print-agent token was not found. Run configure-production-kiosk-user.ps1 as Administrator."
        }
    } else {
        Ensure-RuntimeDirectories $context
        $null = Ensure-ProductionPrintAgentToken $context
    }
    if ($Desktop -and $AttachOnly) {
        Set-ProductionEnvironment $context -DesktopAttachOnly
    } else {
        Set-ProductionEnvironment $context
    }
    # Receipt delivery uses the verified Windows printer-driver path instead
    # of the browser kiosk worker. Keep this setting in the startup script so
    # an ordinary Windows restart cannot fall back to Edge printing.
    $env:POS_DIRECT_WINDOWS_PRINTING = "1"
    $env:POS_RECEIPT_PRINTER = "POSPrinter POS-80"
    if ($Desktop) {
        if (-not (Test-Path -LiteralPath $context.DesktopPython)) {
            throw "Shared desktop Python environment was not found. Run configure-production-kiosk-user.ps1 as Administrator."
        }
        $desktopScript = Join-Path $context.InstallRoot "pos_desktop.py"
        if (-not (Test-Path -LiteralPath $desktopScript)) {
            throw "Production desktop launcher was not found: $desktopScript"
        }
        $env:POS_DESKTOP_ATTACH_ONLY = if ($AttachOnly) { "1" } else { "0" }
        if ($AttachOnly) {
            $env:PYTHONDONTWRITEBYTECODE = "1"
            $env:POS_DESKTOP_PROFILE_ROOT = Join-Path $context.RuntimeRoot "pos-desktop"
            # Wilai has a dedicated Startup print agent. Keep the normal POS
            # account on the launcher-managed agent, but never open two agents
            # in Wilai's session after a Windows restart.
            if ($env:USERNAME -eq "Wilai") {
                $env:POS_EXTERNAL_PRINT_AGENT = "1"
            }
        }
        $env:POS_LAUNCHER_TITLE = "Saengngam POS $($context.AppVersion) Production"
        $env:POS_LAUNCHER_MUTEX = "SaengngamPOSProductionDesktopLauncher"
        Push-Location $context.InstallRoot
        try {
            $desktopOutput = @(& $context.DesktopPython -B $desktopScript 2>&1)
            $desktopExitCode = $LASTEXITCODE
            if ($desktopOutput.Count -gt 0) {
                $desktopLog = Join-Path $context.RuntimeRoot "pos-desktop\desktop-startup.log"
                Add-Content -LiteralPath $desktopLog -Value (
                    "[{0}]`r`n{1}`r`n" -f (Get-Date -Format "s"), ($desktopOutput -join [Environment]::NewLine)
                ) -Encoding UTF8
            }
            if ($desktopExitCode -ne 0) {
                throw "POS Desktop Launcher exited with code $desktopExitCode."
            }
            exit 0
        } finally {
            Pop-Location
        }
    }
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
    if ($Desktop) {
        try {
            $desktopErrorDirectory = if ($context) {
                Join-Path $context.RuntimeRoot "pos-desktop"
            } elseif ($RuntimeRoot) {
                Join-Path ([IO.Path]::GetFullPath($RuntimeRoot)) "pos-desktop"
            } else {
                Join-Path $PSScriptRoot "runtime\pos-desktop"
            }
            New-Item -ItemType Directory -Force -Path $desktopErrorDirectory | Out-Null
            $desktopErrorPath = Join-Path $desktopErrorDirectory "desktop-startup-error.log"
            ($_ | Format-List * -Force | Out-String) |
                Set-Content -LiteralPath $desktopErrorPath -Encoding UTF8
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show(
                "Cannot open POS Launcher.`r`n`r`nDetails: $desktopErrorPath",
                "Saengngam POS",
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Error
            ) | Out-Null
        } catch {
            # The original launcher error remains authoritative.
        }
    }
    Write-Error $_.Exception.Message
    exit 1
}
