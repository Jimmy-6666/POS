# Production Installation

The Windows production lifecycle now includes the Sprint 2 backup runner. It
keeps the existing Flask, Waitress, and SQLite application offline-first while
adding verified local snapshots and optional outbound SFTP database/image sync.

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
install-root\data\pos.db exists without a Release 2.2 runtime database, the
installer uses the existing installation root and does not relocate it.

## Lifecycle

    .\verify-production.ps1
    .\repair-production.ps1
    .\start-production.ps1
    .\stop-production.ps1
    .\restart-production.ps1

The automatic startup task is SaengngamPOS-Production. The Backup page defaults
to a daily 02:00 Asia/Bangkok send time and may be changed by a user with
`backup.manage`; the POS process starts it while running during that minute. The send does not
stop the POS and sales continue if a VPS is offline.

For a manual local backup:

    .\backup-production.ps1

For a manual backup plus VPS upload and incremental file sync:

    .\backup-production.ps1

The remote backup command requires `POS_VPS_*` settings only when remote sync is wanted.
Without them, local backup remains available and the POS itself remains
operational offline. If the local archive verifies but VPS upload or file sync
fails, the command exits with code `2` and reports
`local_complete_remote_failed`; the local archive remains available for
recovery. Any other non-zero exit means the local backup itself failed.

## Network behavior

The application listens on the configured port. The installer creates only
one inbound TCP firewall rule for that port, limited to the Private profile
and LocalSubnet. Public profiles are not enabled. No port forwarding,
Cloudflare Tunnel, reverse proxy, or internet exposure is configured.

If a separately approved Cloudflare Tunnel/reverse proxy is added for customer
ordering, set `POS_TRUST_PROXY=1` only when Waitress receives traffic solely
from that trusted proxy. This makes externally forwarded HTTPS issue Secure
session cookies, while direct `http://localhost:<port>` continues to work with
its local cookie. Do not enable it on an internet-facing listener that accepts
untrusted `X-Forwarded-*` headers.

For customer ordering through LINE LIFF, follow `docs/LINE_LIFF_SETUP.md`
before enabling the public Rich Menu link. It records the required Machine
environment values, HTTPS/Cloudflare trust condition, and live acceptance test.

## Signed update and support

The administrator-only **ดูแลระบบ** page provides runtime status, support
bundle download, and the controlled signed-update hand-off. Follow
`docs/SIGNED_UPDATE_AND_SUPPORT.md` to configure the publisher certificate
thumbprint and package format. It does not enable remote control or automatic
internet downloads.

## Lock regeneration

Keep requirements.txt as the direct dependency list. In a clean supported
environment:

    python -m venv .venv-lock
    .\.venv-lock\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv-lock\Scripts\python.exe -m pip freeze | Set-Content requirements.lock.txt

Review the generated file and run python -m pip check before accepting it.
