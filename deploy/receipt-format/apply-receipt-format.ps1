param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$BackupRoot,
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$expectedDrawerSourceHash = "e48cff050317e5c8476b83a338f1e3bdd5deaf004c2f8550fb562793a5dd8e49"
$expectedOldTextHashes = @{
    "pos_app/templates/receipt.html" = "71823464d451eb1383ab8f18476d2893cca3b615279d341a2757dd445bf5ad38"
    "pos_app/static/css/receipt.css" = "1cf244223a4719b0c9a923eeceb33cb8ecb967eba63cab5acb409a0e3e6a8ffb"
}
$salePattern = "(?ms)^def _sale_receipt_payload\(sale_id, printer_name\):.*?(?=^def _checked_order_payload)"
$gdiPattern = "(?ms)^def _windows_gdi_command\(payload\):.*?(?=^def _direct_windows_print_worker)"

function Normalize-Text([string]$Value) {
    return ($Value -replace "`r`n", "`n" -replace "`r", "`n")
}

function Get-TextHash([string]$Value) {
    $bytes = [Text.Encoding]::UTF8.GetBytes((Normalize-Text $Value))
    $digest = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    return ([BitConverter]::ToString($digest) -replace "-", "").ToLowerInvariant()
}

function Read-NormalizedText([string]$Path) {
    return Normalize-Text ([IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8))
}

function Get-OnlyMatch([string]$Text, [string]$Pattern, [string]$Label) {
    $matches = [regex]::Matches($Text, $Pattern)
    if ($matches.Count -ne 1) {
        throw "$Label must occur exactly once; found $($matches.Count)."
    }
    return $matches[0].Value.TrimEnd([char[]]"`n")
}

function Assert-SafeRoot([string]$Path, [string]$Label) {
    $resolved = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($resolved)
    if ($resolved.TrimEnd('\') -eq $root.TrimEnd('\')) {
        throw "$Label cannot be a filesystem root: $resolved"
    }
    return $resolved
}

function Assert-DrawerInvariant([string]$Text, [string]$Label) {
    $drawerBlock = @'
try {{
    # Keep the original single drawer pulse before the receipt job.
    $drawer = [byte[]](0x1B,0x40,0x1B,0x70,0,25,250)
    [SaengngamReceiptPrinter]::SendRaw([string]$payload.printer_name, $drawer)
}} catch {{
    # Optional RAW drawer support must never suppress the receipt.
}}
'@
    $normalized = Normalize-Text $Text
    $drawerHash = Get-TextHash $drawerBlock
    if ($drawerHash -ne $expectedDrawerSourceHash) {
        throw "Packaged drawer invariant hash is invalid."
    }
    if ([regex]::Matches($normalized, [regex]::Escape($drawerBlock)).Count -ne 1) {
        throw "$Label does not contain the exact single cash-drawer block."
    }
    $drawerLine = '$drawer = [byte[]](0x1B,0x40,0x1B,0x70,0,25,250)'
    $logoLine = '$logo = [byte[]](0x1B,0x40,0x1B,0x74,20,0x1C,0x70,1,0,0x0A)'
    if ([regex]::Matches($normalized, [regex]::Escape($drawerLine)).Count -ne 1) {
        throw "$Label must contain exactly one drawer pulse."
    }
    if ([regex]::Matches($normalized, [regex]::Escape($logoLine)).Count -ne 1) {
        throw "$Label must contain exactly one printer-stored logo command."
    }
    if ($normalized.IndexOf($drawerLine) -gt $normalized.IndexOf($logoLine)) {
        throw "$Label changed the established drawer-before-logo order."
    }
}

$install = Assert-SafeRoot $InstallRoot "InstallRoot"
$backup = Assert-SafeRoot $BackupRoot "BackupRoot"
$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$payloadRoot = Join-Path $packageRoot "payload"
$preconditionRoot = Join-Path $packageRoot "preconditions"
if (-not (Test-Path -LiteralPath $install -PathType Container)) {
    throw "InstallRoot was not found: $install"
}
if (-not (Test-Path -LiteralPath $payloadRoot -PathType Container)) {
    throw "Package payload was not found: $payloadRoot"
}

$relativePaths = @(
    "pos_app/services/print_jobs.py",
    "pos_app/templates/receipt.html",
    "pos_app/static/css/receipt.css",
    "pos_app/static/img/receipt-logo.png"
)
foreach ($relativePath in $relativePaths) {
    $payloadPath = Join-Path $payloadRoot $relativePath
    if (-not (Test-Path -LiteralPath $payloadPath -PathType Leaf)) {
        throw "Package payload is missing: $relativePath"
    }
}

$targetPrintPath = Join-Path $install "pos_app/services/print_jobs.py"
$payloadPrintPath = Join-Path $payloadRoot "pos_app/services/print_jobs.py"
if (-not (Test-Path -LiteralPath $targetPrintPath -PathType Leaf)) {
    throw "Production print service was not found: $targetPrintPath"
}
$targetPrintRaw = [IO.File]::ReadAllText($targetPrintPath, [Text.Encoding]::UTF8)
$targetPrint = Normalize-Text $targetPrintRaw
$payloadPrint = Read-NormalizedText $payloadPrintPath
$oldSale = (Read-NormalizedText (Join-Path $preconditionRoot "sale_receipt_payload.py.txt")).TrimEnd([char[]]"`n")
$oldGdi = (Read-NormalizedText (Join-Path $preconditionRoot "windows_gdi_command.py.txt")).TrimEnd([char[]]"`n")
$newSale = Get-OnlyMatch $payloadPrint $salePattern "Payload sale receipt function"
$newGdi = Get-OnlyMatch $payloadPrint $gdiPattern "Payload Windows GDI function"
$targetSale = Get-OnlyMatch $targetPrint $salePattern "Target sale receipt function"
$targetGdi = Get-OnlyMatch $targetPrint $gdiPattern "Target Windows GDI function"

if ($targetSale -ne $oldSale -and $targetSale -ne $newSale) {
    throw "Target sale receipt function differs from both the approved baseline and package. Review manually; no file was changed."
}
if ($targetGdi -ne $oldGdi -and $targetGdi -ne $newGdi) {
    throw "Target Windows GDI function differs from both the approved baseline and package. Review manually; no file was changed."
}
$targetOutside = [regex]::Replace([regex]::Replace($targetPrint, $salePattern, "<SALE_RECEIPT_FORMAT>`n`n"), $gdiPattern, "<WINDOWS_GDI_FORMAT>`n`n")
$payloadOutside = [regex]::Replace([regex]::Replace($payloadPrint, $salePattern, "<SALE_RECEIPT_FORMAT>`n`n"), $gdiPattern, "<WINDOWS_GDI_FORMAT>`n`n")
if ((Get-TextHash $targetOutside) -ne (Get-TextHash $payloadOutside)) {
    throw "Target print_jobs.py has changes outside the two receipt-format functions. Review manually; no file was changed."
}
Assert-DrawerInvariant $targetGdi "Target Windows GDI function"
Assert-DrawerInvariant $newGdi "Payload Windows GDI function"

foreach ($relativePath in @("pos_app/templates/receipt.html", "pos_app/static/css/receipt.css")) {
    $targetPath = Join-Path $install $relativePath
    $payloadPath = Join-Path $payloadRoot $relativePath
    if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) {
        throw "Target file was not found: $relativePath"
    }
    $targetHash = Get-TextHash ([IO.File]::ReadAllText($targetPath, [Text.Encoding]::UTF8))
    $payloadHash = Get-TextHash ([IO.File]::ReadAllText($payloadPath, [Text.Encoding]::UTF8))
    if ($targetHash -ne $expectedOldTextHashes[$relativePath] -and $targetHash -ne $payloadHash) {
        throw "Target receipt file has unreviewed changes: $relativePath"
    }
}

$targetLogo = Join-Path $install "pos_app/static/img/receipt-logo.png"
$payloadLogo = Join-Path $payloadRoot "pos_app/static/img/receipt-logo.png"
if ((Test-Path -LiteralPath $targetLogo) -and
    (Get-FileHash -Algorithm SHA256 -LiteralPath $targetLogo).Hash -ne
    (Get-FileHash -Algorithm SHA256 -LiteralPath $payloadLogo).Hash) {
    throw "Target receipt logo differs from the approved package. Review it manually; no file was changed."
}

$preflight = [ordered]@{
    ok = $true
    install_root = $install
    receipt_format_already_applied = ($targetSale -eq $newSale -and $targetGdi -eq $newGdi)
    cash_drawer_source_sha256 = $expectedDrawerSourceHash
    files = $relativePaths
}
if ($PreflightOnly) {
    $preflight | ConvertTo-Json -Depth 5
    exit 0
}

$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$backupSession = Join-Path $backup "receipt-format-before-$timestamp"
New-Item -ItemType Directory -Path $backupSession -Force | Out-Null
$beforeEntries = New-Object System.Collections.Generic.List[object]
foreach ($relativePath in $relativePaths) {
    $targetPath = Join-Path $install $relativePath
    if (Test-Path -LiteralPath $targetPath -PathType Leaf) {
        $backupPath = Join-Path $backupSession $relativePath
        New-Item -ItemType Directory -Path (Split-Path -Parent $backupPath) -Force | Out-Null
        Copy-Item -LiteralPath $targetPath -Destination $backupPath -Force
        $beforeEntries.Add([ordered]@{
            path = $relativePath
            existed = $true
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $backupPath).Hash.ToLowerInvariant()
        })
    } else {
        $beforeEntries.Add([ordered]@{ path = $relativePath; existed = $false; sha256 = $null })
    }
}
$beforeManifest = [ordered]@{
    created_at_utc = [DateTime]::UtcNow.ToString("o")
    install_root = $install
    cash_drawer_source_sha256 = $expectedDrawerSourceHash
    entries = @($beforeEntries | ForEach-Object { $_ })
}
[IO.File]::WriteAllText(
    (Join-Path $backupSession "rollback-manifest.json"),
    ($beforeManifest | ConvertTo-Json -Depth 6),
    [Text.UTF8Encoding]::new($false)
)

$updatedPrint = $targetPrint.Replace($targetSale, $newSale).Replace($targetGdi, $newGdi)
$printOutput = if ($targetPrintRaw.Contains("`r`n")) { $updatedPrint -replace "`n", "`r`n" } else { $updatedPrint }
[IO.File]::WriteAllText($targetPrintPath, $printOutput, [Text.UTF8Encoding]::new($false))
foreach ($relativePath in @("pos_app/templates/receipt.html", "pos_app/static/css/receipt.css")) {
    $targetPath = Join-Path $install $relativePath
    $payloadPath = Join-Path $payloadRoot $relativePath
    [IO.File]::WriteAllText(
        $targetPath,
        [IO.File]::ReadAllText($payloadPath, [Text.Encoding]::UTF8),
        [Text.UTF8Encoding]::new($false)
    )
}
New-Item -ItemType Directory -Path (Split-Path -Parent $targetLogo) -Force | Out-Null
[IO.File]::WriteAllBytes($targetLogo, [IO.File]::ReadAllBytes($payloadLogo))

$afterEntries = New-Object System.Collections.Generic.List[object]
foreach ($relativePath in $relativePaths) {
    $targetPath = Join-Path $install $relativePath
    $afterEntries.Add([ordered]@{
        path = $relativePath
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetPath).Hash.ToLowerInvariant()
    })
}
$appliedPrint = Read-NormalizedText $targetPrintPath
if ((Get-OnlyMatch $appliedPrint $salePattern "Applied sale receipt function") -ne $newSale -or
    (Get-OnlyMatch $appliedPrint $gdiPattern "Applied Windows GDI function") -ne $newGdi) {
    throw "Receipt functions did not match the package after write. Restore from $backupSession"
}
Assert-DrawerInvariant (Get-OnlyMatch $appliedPrint $gdiPattern "Applied Windows GDI function") "Applied Windows GDI function"

$result = [ordered]@{
    ok = $true
    install_root = $install
    backup_directory = $backupSession
    server_restart_required = $true
    database_migration_required = $false
    cash_drawer_source_sha256 = $expectedDrawerSourceHash
    entries = @($afterEntries | ForEach-Object { $_ })
}
$result | ConvertTo-Json -Depth 6
