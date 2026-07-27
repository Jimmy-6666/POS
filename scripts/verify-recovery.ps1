param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [string]$InstallRoot
)
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $PSScriptRoot) "production-common.ps1")
try {
    Assert-Windows
    $root = if ($InstallRoot) { [IO.Path]::GetFullPath($InstallRoot) } else { Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
    $database = Join-Path ([IO.Path]::GetFullPath($RuntimeRoot)) "data\pos.db"
    if (-not (Test-Path -LiteralPath $database)) { throw "Recovered database was not found: $database" }
    Push-Location $root
    try {
        & $python -c "import sqlite3,sys; p=sys.argv[1]; c=sqlite3.connect(p); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert not c.execute('PRAGMA foreign_key_check').fetchall(); print('Recovery SQLite checks passed')" $database
        if ($LASTEXITCODE -ne 0) { throw "Recovered SQLite checks failed." }
    } finally {
        Pop-Location
    }
    Write-Output "Recovery verification passed: $RuntimeRoot"
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
