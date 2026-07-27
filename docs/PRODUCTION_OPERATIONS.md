# Production Operations

## Daily checks

    .\verify-production.ps1
    Get-ScheduledTask -TaskName SaengngamPOS-Backup
    Get-ChildItem .\runtime\backups\backup-*.zip

The POS service and backup task are independent. A failed VPS upload must not
interrupt sales; inspect the scheduled-task result and local backup directory.

## Manual commands

    .\backup-production.ps1
    .\sync-production.ps1
    .\.venv\Scripts\python.exe -m pos_app.backup_cli verify .\runtime\backups\backup-YYYYMMDDT020000Z.zip

The admin backup page remains available to users with `backup.manage`. It
creates the same verified local archive and records an audit event.

## File policy

Back up: SQLite snapshots, product images, and required uploads. Sync by
default: `uploads/products`. Configure additional approved runtime roots only
after reviewing their privacy and recovery need.

Never sync: databases, WAL/SHM files, secrets, private keys, logs, browser
profiles, virtual environments, caches, incomplete uploads, UAT data, source
imports, or generated development artifacts.

## Recovery drill

    .\scripts\recover-production.ps1 -Archive $archive `
      -TargetRuntimeRoot 'C:\Temp\SaengngamPOS-Recovery-Drill'
    .\scripts\verify-recovery.ps1 -RuntimeRoot 'C:\Temp\SaengngamPOS-Recovery-Drill'

Keep a recovery drill result with the installation report. Do not point the
drill at the active runtime.
