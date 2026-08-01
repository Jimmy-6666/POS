param(
    [string]$Version = "3.1.4",
    [string]$Ref = "HEAD",
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath($PSScriptRoot)
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $root "outputs\release-$Version"
}
$output = [IO.Path]::GetFullPath($OutputDirectory)
$archiveName = "Saengngam-POS-$Version.zip"
$archive = Join-Path $output $archiveName
$temporary = "$archive.part"

Push-Location $root
try {
    $commit = (& git rev-parse --verify "$Ref^{commit}" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $commit -notmatch "^[0-9a-f]{40}$") {
        throw "Release ref is not a valid commit: $Ref"
    }
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    & git archive --format=zip "--output=$temporary" $commit
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $temporary)) {
        throw "Git archive failed."
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $package = [IO.Compression.ZipFile]::OpenRead($temporary)
    try {
        $names = @($package.Entries | ForEach-Object { $_.FullName })
        $required = @(
            "app.py",
            "requirements.lock.txt",
            "install-production.ps1",
            "verify-production.ps1",
            "VERSION_3.1.4.md"
        )
        foreach ($name in $required) {
            if ($names -notcontains $name) {
                throw "Release archive is missing required file: $name"
            }
        }
        $forbidden = @(
            "(^|/)(runtime|uat_runtime|\.venv|backups|logs|browser-profile|print-browser-profile)(/|$)",
            "(^|/)(uploads)(/|$)",
            "(^|/)(production\.json|\.secret_key|\.env(?:\.|$))",
            "\.(?:db|db-wal|db-shm|pem|key|pfx|p12)$"
        )
        foreach ($name in $names) {
            foreach ($pattern in $forbidden) {
                if ($name -match $pattern) {
                    throw "Release archive contains a forbidden runtime or secret path: $name"
                }
            }
        }
    } finally {
        $package.Dispose()
    }

    Move-Item -LiteralPath $temporary -Destination $archive -Force
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
    "$hash  $archiveName" | Set-Content -LiteralPath "$archive.sha256" -Encoding ascii
    $manifest = [ordered]@{
        product = "Saengngam Minimart POS"
        version = $Version
        source_ref = $Ref
        source_commit = $commit
        archive = $archiveName
        sha256 = $hash
        created_at_utc = [DateTime]::UtcNow.ToString("o")
        data_policy = "Committed source only; runtime data, uploads, credentials, and virtual environments excluded."
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output "release-manifest.json") -Encoding UTF8
    Write-Output ($manifest | ConvertTo-Json -Compress)
} finally {
    Pop-Location
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
}
