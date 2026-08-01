param(
    [string]$InstallRoot,
    [string]$RuntimeRoot,
    [int]$Port = 8000,
    [switch]$Worker,
    [string]$ResultPath
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "production-common.ps1")

if ($Worker) {
    try {
        $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
        Set-ProductionEnvironment $context
        Push-Location $context.InstallRoot
        try {
            $previousPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $output = @(& $context.Python -m pos_app.backup_cli test-connection 2>&1)
            $exitCode = $LASTEXITCODE
            $ErrorActionPreference = $previousPreference
        } finally {
            Pop-Location
        }
        [pscustomobject]@{
            status = if ($exitCode -eq 0) { "complete" } else { "failed" }
            exit_code = $exitCode
            output = @($output | ForEach-Object { $_.ToString() })
        } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
        exit $exitCode
    } catch {
        [pscustomobject]@{ status = "failed"; error = $_.Exception.Message } |
            ConvertTo-Json -Compress | Set-Content -LiteralPath $ResultPath -Encoding UTF8
        exit 1
    }
}

try {
    Assert-Windows
    Assert-Administrator
    $context = Get-ProductionContext $InstallRoot $RuntimeRoot $Port
    $secretStatus = Test-ProductionVpsBackupSecrets $context
    if (-not $secretStatus.configured) { throw "Production VPS backup is not configured." }
    if (-not $secretStatus.ok) { throw "Production VPS backup secret validation failed: $($secretStatus.issues -join '; ')" }

    $taskName = "SaengngamPOS-BackupConnectionTest-$([Guid]::NewGuid().ToString('N'))"
    $resultFile = if ($ResultPath) {
        [IO.Path]::GetFullPath($ResultPath)
    } else {
        Join-Path $context.ReportDirectory ("backup-connection-test-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resultFile) | Out-Null
    $scriptPath = Join-Path $context.InstallRoot "test-production-backup-connection.ps1"
    $argument = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -InstallRoot "{1}" -RuntimeRoot "{2}" -Port {3} -Worker -ResultPath "{4}"' -f $scriptPath, $context.InstallRoot, $context.RuntimeRoot, $context.Port, $resultFile
    $action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument $argument -WorkingDirectory $context.InstallRoot
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    try {
        Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal | Out-Null
        Start-ScheduledTask -TaskName $taskName
        $deadline = (Get-Date).AddSeconds(60)
        do {
            Start-Sleep -Milliseconds 500
            $task = Get-ScheduledTask -TaskName $taskName
            $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
        } while ($task.State -eq "Running" -and (Get-Date) -lt $deadline)
        if ($task.State -eq "Running") { throw "Production backup connection test timed out." }
        if (-not (Test-Path -LiteralPath $resultFile -PathType Leaf)) {
            throw "Production backup connection test produced no result; task result $($taskInfo.LastTaskResult)."
        }
    } finally {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    $result = Get-Content -Raw -LiteralPath $resultFile | ConvertFrom-Json
    if ($result.status -ne "complete") {
        $detail = @($result.output) -join " "
        if (-not $detail) { $detail = $result.error }
        throw "Production backup connection test failed: $detail"
    }
    Get-Content -Raw -LiteralPath $resultFile
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
