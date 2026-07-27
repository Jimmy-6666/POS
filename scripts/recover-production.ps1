param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [Parameter(Mandatory=$true)][string]$TargetRuntimeRoot,
    [string]$InstallRoot
)
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $PSScriptRoot) "production-common.ps1")
try {
    Assert-Windows
    Assert-Administrator
    $resolvedArchive = [IO.Path]::GetFullPath($Archive)
    $target = [IO.Path]::GetFullPath($TargetRuntimeRoot)
    if (-not (Test-Path -LiteralPath $resolvedArchive)) { throw "Backup archive was not found." }
    if (Test-Path -LiteralPath $target) {
        $children = Get-ChildItem -LiteralPath $target -Force
        if ($children) { throw "Recovery target must be empty: $target" }
    }
    $root = if ($InstallRoot) { [IO.Path]::GetFullPath($InstallRoot) } else { Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
    Push-Location $root
    try {
        & $python -m pos_app.backup_cli restore-drill $resolvedArchive $target
        if ($LASTEXITCODE -ne 0) { throw "Recovery verification failed." }
    } finally {
        Pop-Location
    }
    Write-Output "Recovery drill completed in: $target"
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
