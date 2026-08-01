param(
    [string]$InstallRoot = $PSScriptRoot,
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $InstallRoot 'runtime'
$tokenPath = Join-Path $runtimeRoot 'config\print-agent-token'
$profile = Join-Path $env:LOCALAPPDATA 'SaengngamPOS\wilai-production-print-agent-v2'

for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$Port/health"
        if ($response.StatusCode -eq 200) { break }
    } catch {
        if ($attempt -eq 59) { exit 0 }
    }
    Start-Sleep -Seconds 1
}

if (-not (Test-Path -LiteralPath $tokenPath)) { exit 0 }
$token = (Get-Content -Raw -LiteralPath $tokenPath).Trim()
if (-not $token) { exit 0 }

# Allow the production desktop launcher a short startup window. If it owns an
# agent in this session, leave it as the single worker. Otherwise this script
# remains the Wilai-only fallback worker.
Start-Sleep -Seconds 12
$printAgentMarker = "--app=http://127.0.0.1:$Port/print-agent"
$existing = Get-CimInstance Win32_Process -Filter "Name = 'msedge.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match [regex]::Escape($printAgentMarker) }
if ($existing) { exit 0 }

$edge = @(
    'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $edge) { exit 0 }

New-Item -ItemType Directory -Force -Path $profile | Out-Null
$url = "http://127.0.0.1:$Port/print-agent?token=$([uri]::EscapeDataString($token))&desktop_user=Wilai"
Start-Process -FilePath $edge -ArgumentList @(
    "--app=$url", '--new-window', '--window-size=320,240', '--window-position=-32000,-32000',
    "--user-data-dir=$profile", '--no-first-run', '--no-default-browser-check',
    '--disable-session-crashed-bubble', '--kiosk-printing', '--disable-save-password-bubble',
    '--disable-background-mode', '--disable-sync', '--disable-signin-promo'
) -WindowStyle Hidden
