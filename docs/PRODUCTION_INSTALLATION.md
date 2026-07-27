# Production Installation

The Windows production lifecycle now includes the Sprint 2 backup runner. It
keeps the existing Flask, Waitress, and SQLite application offline-first while
adding verified local snapshots, optional outbound SFTP sync, and a daily
Task Scheduler job.

## Requirements

- Windows 10 or newer.
- Python 3.11 or newer available as python.
- An elevated PowerShell window for installation, Task Scheduler, and firewall
  configuration.
- The application folder extracted to a stable path, not run from a ZIP.

## Install

From the application folder:

    PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-production.ps1

Optional paths:

    .\install-production.ps1 -InstallRoot 'C:\SaengngamPOS' -RuntimeRoot 'C:\ProgramData\SaengngamPOS' -Port 8000

The installer creates or repairs .venv, installs requirements.lock.txt,
initializes additive database migrations, preserves the database, secret key,
and uploads, registers the startup task, configures the Private/LocalSubnet
firewall rule, starts the POS, and writes a machine-readable report under
runtime\support.

New installations default to install-root\runtime. If an existing legacy
install-root\data\pos.db exists without a Release 2.1 runtime database, the
installer uses the existing installation root and does not relocate it.

## Lifecycle

    .\verify-production.ps1
    .\repair-production.ps1
    .\start-production.ps1
    .\stop-production.ps1
    .\restart-production.ps1

The automatic startup task is SaengngamPOS-Production. The automatic backup
task is SaengngamPOS-Backup and defaults to 02:00 Asia/Bangkok (override the
`POS_BACKUP_TIME` environment variable before installation). Both tasks run as
SYSTEM; the backup task does not stop the POS and sales continue if a VPS is
offline.

For a manual local backup:

    .\backup-production.ps1

For a manual backup plus VPS upload and incremental file sync:

    .\backup-production.ps1

The backup task requires `POS_VPS_*` settings only when remote sync is wanted.
Without them, local backup remains available and the POS itself remains
operational offline.

## Network behavior

The application listens on the configured port. The installer creates only
one inbound TCP firewall rule for that port, limited to the Private profile
and LocalSubnet. Public profiles are not enabled. No port forwarding,
Cloudflare Tunnel, reverse proxy, or internet exposure is configured.

## Lock regeneration

Keep requirements.txt as the direct dependency list. In a clean supported
environment:

    python -m venv .venv-lock
    .\.venv-lock\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv-lock\Scripts\python.exe -m pip freeze | Set-Content requirements.lock.txt

Review the generated file and run python -m pip check before accepting it.
