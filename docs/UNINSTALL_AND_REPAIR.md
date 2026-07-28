# Uninstall and Repair

## Repair

Run from an elevated PowerShell window:

    .\repair-production.ps1
    .\verify-production.ps1

Repair recreates missing non-data directories, repairs the virtual
environment and locked dependencies, reruns safe startup migrations, restores
the POS Task Scheduler registration, removes any legacy daily-backup task, and
restores the private-LAN firewall rule. Daily backup time is set in the Backup
page.
It never replaces the production database or secret key.

## Uninstall

    .\uninstall-production.ps1

Uninstall removes the production and any legacy backup Task Scheduler tasks, the
dedicated production firewall rule, and the application virtual environment.
It preserves:

- database and SQLite sidecar files;
- secret key;
- product images and payment evidence;
- backups, logs, support files, and runtime configuration.

Use -KeepEnvironment to retain .venv as well:

    .\uninstall-production.ps1 -KeepEnvironment

Sprint 1 does not implement a destructive data-removal option. Remove
production data only through a separately approved, manually verified
procedure.
