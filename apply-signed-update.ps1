param(
    [Parameter(Mandatory = $true)][string]$UpdateScript,
    [Parameter(Mandatory = $true)][string]$ExpectedThumbprint,
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][string]$RuntimeRoot,
    [Parameter(Mandatory = $true)][int]$Port
)
$ErrorActionPreference = "Stop"
try {
    $resolvedScript = [IO.Path]::GetFullPath($UpdateScript)
    $resolvedStaging = [IO.Path]::GetFullPath((Join-Path $RuntimeRoot "staging"))
    if (-not $resolvedScript.StartsWith($resolvedStaging, [StringComparison]::OrdinalIgnoreCase)) { throw "The update script must stay inside the runtime staging directory." }
    $signature = Get-AuthenticodeSignature -LiteralPath $resolvedScript
    if ($signature.Status -ne "Valid") { throw "The update script signature is not valid." }
    $actualThumbprint = ($signature.SignerCertificate.Thumbprint -replace "\s", "").ToUpperInvariant()
    if ($actualThumbprint -ne ($ExpectedThumbprint -replace "\s", "").ToUpperInvariant()) { throw "The update signer does not match the approved publisher." }
    $logDirectory = Join-Path $RuntimeRoot "logs"; New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    $log = Join-Path $logDirectory ("signed-update-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
    & $resolvedScript -InstallRoot $InstallRoot -RuntimeRoot $RuntimeRoot -Port $Port *>&1 | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "The signed update script returned exit code $LASTEXITCODE." }
    exit 0
} catch { Write-Error $_.Exception.Message; exit 1 }
