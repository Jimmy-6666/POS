# Production Operations

## Daily checks

    .\verify-production.ps1
    Get-ChildItem .\runtime\backups\backup-*.zip

The Backup page contains the daily schedule and last server-upload status. The
POS must be running during the selected Bangkok minute. A failed VPS upload must not
interrupt sales; inspect the local backup directory and Backup page status.

## Manual commands

    .\backup-production.ps1 -LocalOnly
    .\sync-production.ps1
    .\.venv\Scripts\python.exe -m pos_app.backup_cli verify .\runtime\backups\backup-YYYYMMDDT020000Z.zip

The admin backup page remains available to users with `backup.manage`. It can
create a local database archive, send a database archive plus image delta now,
and set the daily send time; all actions record audit events.

## File policy

Back up: SQLite snapshots in the database ZIP. Sync separately by default:
`uploads/products`. Only new/changed product images are sent. The VPS moves a
previous or locally deleted image snapshot into `file-backups/` before removing
it from the active snapshot. Configure additional approved runtime roots only
after reviewing their privacy and recovery need.

Never sync: databases, WAL/SHM files, secrets, private keys, logs, browser
profiles, virtual environments, caches, incomplete uploads, UAT data, source
imports, or generated development artifacts.

## Full recovery bundle

Before customer handoff, upgrade, or an offline recovery drill, create a
verified bundle containing the SQLite snapshot and current product images:

    .\backup-production.ps1 -FullRecoveryBundle

Copy the resulting `recovery-*.zip` and its recorded SHA-256 to
owner-controlled off-machine storage. This command is intentionally separate
from the smaller daily database backup and incremental VPS image sync.

## Recovery drill

    .\scripts\recover-production.ps1 -Archive $archive `
      -TargetRuntimeRoot 'C:\Temp\SaengngamPOS-Recovery-Drill'
    .\scripts\verify-recovery.ps1 -RuntimeRoot 'C:\Temp\SaengngamPOS-Recovery-Drill'

Keep a recovery drill result with the installation report. Do not point the
drill at the active runtime.
