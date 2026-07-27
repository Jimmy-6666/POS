# Production Installation

Sprint 1 provides a Windows production lifecycle around the existing Flask,
Waitress, and SQLite application. It does not provide VPS backup, update
rollback, or remote support; those remain deferred.

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

The automatic startup task is SaengngamPOS-Production. It runs the production
launcher at Windows startup as SYSTEM and requests up to three restarts after
failure. It never uses the UAT launcher.

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

