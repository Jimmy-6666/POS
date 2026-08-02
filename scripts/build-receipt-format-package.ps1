param(
    [string]$OutputRoot
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$packageName = "receipt-format-80mm-20260802"
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $root "output\deploy"
}
$output = [IO.Path]::GetFullPath($OutputRoot)
$staging = Join-Path $output $packageName
$archive = Join-Path $output "$packageName.zip"
$archiveHash = "$archive.sha256"

function Assert-ChildPath([string]$Parent, [string]$Child) {
    $parentPath = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    $childPath = [IO.Path]::GetFullPath($Child)
    if (-not $childPath.StartsWith($parentPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe generated path outside output root: $childPath"
    }
}

function Copy-PackageFile([string]$SourceRelative, [string]$DestinationRelative) {
    $source = Join-Path $root $SourceRelative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required package source was not found: $SourceRelative"
    }
    $destination = Join-Path $staging $DestinationRelative
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

New-Item -ItemType Directory -Path $output -Force | Out-Null
Assert-ChildPath $output $staging
Assert-ChildPath $output $archive
if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
foreach ($generatedFile in @($archive, $archiveHash)) {
    if (Test-Path -LiteralPath $generatedFile) {
        Remove-Item -LiteralPath $generatedFile -Force
    }
}
New-Item -ItemType Directory -Path $staging -Force | Out-Null

Copy-PackageFile "deploy/receipt-format/apply-receipt-format.ps1" "apply-receipt-format.ps1"
Copy-PackageFile "deploy/receipt-format/preconditions/sale_receipt_payload.py.txt" "preconditions/sale_receipt_payload.py.txt"
Copy-PackageFile "deploy/receipt-format/preconditions/windows_gdi_command.py.txt" "preconditions/windows_gdi_command.py.txt"
Copy-PackageFile "pos_app/services/print_jobs.py" "payload/pos_app/services/print_jobs.py"
Copy-PackageFile "pos_app/templates/receipt.html" "payload/pos_app/templates/receipt.html"
Copy-PackageFile "pos_app/static/css/receipt.css" "payload/pos_app/static/css/receipt.css"
Copy-PackageFile "pos_app/static/img/receipt-logo.png" "payload/pos_app/static/img/receipt-logo.png"
Copy-PackageFile "tests/test_receipt_format.py" "verification/tests/test_receipt_format.py"
Copy-PackageFile "docs/RECEIPT_FORMAT_DEPLOYMENT_TH.md" "DEPLOY_INSTRUCTIONS_TH.md"
Copy-PackageFile "CODEX_RECEIPT_FORMAT_DEPLOY_PROMPT_TH.md" "CODEX_DEPLOY_PROMPT_TH.md"
Copy-PackageFile "output/pdf/receipt-sample-80mm-auto.pdf" "reference/approved-google-doc-sample.pdf"
Copy-PackageFile "output/receipt-code-sample.pdf" "reference/rendered-from-code-sample.pdf"

$entries = @(
    Get-ChildItem -LiteralPath $staging -Recurse -File |
        Sort-Object FullName |
        ForEach-Object {
            [ordered]@{
                path = $_.FullName.Substring($staging.Length + 1).Replace('\', '/')
                size = $_.Length
                sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
            }
        }
)
$manifest = [ordered]@{
    package = $packageName
    product = "Saengngam Minimart POS"
    purpose = "Receipt format only; 80 x 297 mm paper with 72 mm content width"
    created_at_utc = [DateTime]::UtcNow.ToString("o")
    database_migration_required = $false
    server_restart_required = $true
    cash_drawer_source_sha256 = "e48cff050317e5c8476b83a338f1e3bdd5deaf004c2f8550fb562793a5dd8e49"
    approved_google_doc = "https://docs.google.com/document/d/1zyf1tXiM0bMRbkZDkhk62IwFHzgYPKzEaRv31w1Da9k"
    production_payload = @(
        "pos_app/services/print_jobs.py (two receipt-format functions only via installer)",
        "pos_app/templates/receipt.html",
        "pos_app/static/css/receipt.css",
        "pos_app/static/img/receipt-logo.png"
    )
    excluded_scope = "No database/runtime/config/routes/desktop launcher/receipt popup/LINE Bot changes"
    entries = $entries
}
$manifestPath = Join-Path $staging "manifest.json"
[IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false)
)

$sumLines = @(
    Get-ChildItem -LiteralPath $staging -Recurse -File |
        Sort-Object FullName |
        ForEach-Object {
            $relative = $_.FullName.Substring($staging.Length + 1).Replace('\', '/')
            $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
            "$hash  $relative"
        }
)
[IO.File]::WriteAllLines((Join-Path $staging "SHA256SUMS.txt"), $sumLines, [Text.Encoding]::ASCII)

$forbiddenPatterns = @(
    "(^|/)(runtime|uat_runtime|\.venv|uploads|backups|browser-profile|print-browser-profile)(/|$)",
    "(^|/)(production\.json|\.secret_key|\.env)(/|$)",
    "\.(db|db-wal|db-shm|pem|key|pfx|p12)$"
)
foreach ($file in Get-ChildItem -LiteralPath $staging -Recurse -File) {
    $relative = $file.FullName.Substring($staging.Length + 1).Replace('\', '/')
    foreach ($pattern in $forbiddenPatterns) {
        if ($relative -match $pattern) {
            throw "Package contains forbidden runtime or secret path: $relative"
        }
    }
}

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $archive -CompressionLevel Optimal
$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($archiveHash, "$zipHash  $packageName.zip`r`n", [Text.Encoding]::ASCII)

[ordered]@{
    ok = $true
    package_directory = $staging
    archive = $archive
    archive_sha256 = $zipHash
    entries = (Get-ChildItem -LiteralPath $staging -Recurse -File).Count
} | ConvertTo-Json
