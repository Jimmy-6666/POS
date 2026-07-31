# Production Installation

Release 3.0.9 formalizes the isolated standard local `POS` account and the
separate `SYSTEM` server/interactive launcher lifecycle. See
`VERSION_3.0.9.md` for its accepted behavior, recovery contract, and
verification evidence.

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

The automatic server task is `SaengngamPOS-Production`; it runs as `SYSTEM` at
Windows startup without opening a desktop window. Configure the cashier
desktop separately from an elevated PowerShell window:

    .\configure-production-kiosk-user.ps1 -AccountName POS

This creates a passwordless standard local `POS` account,
`SaengngamPOS-Desktop` (attach-only launcher at that user's logon), a local
print-agent token, restricted launcher ACLs, a read-only standard-library
Python runtime at `desktop-python\`, and
`C:\Users\Public\Desktop\Saengngam POS.lnk`. Sign in to Windows as `POS` to
start the launcher; closing it does not stop the background server, and the
shortcut opens it again. The shared runtime prevents the launcher from
depending on the Admin user's private `AppData` Python installation; the
launcher loads its standalone path helper without starting Flask, while the
server continues to use the locked `.venv`. A desktop bootstrap failure is
shown visibly and written under `runtime\pos-desktop`. The shared mutable
display state is also stored at
`runtime\pos-desktop\display_state.json`; keeping it under this writable
parent preserves POS access when the server recreates the file after reboot.

The Backup page defaults
to a daily 02:00 Asia/Bangkok send time and may be changed by a user with
`backup.manage`; the POS process starts it while running during that minute. The send does not
stop the POS and sales continue if a VPS is offline.

For a manual local backup:

    .\backup-production.ps1 -LocalOnly

For a manual backup plus VPS upload and incremental file sync:

    .\backup-production.ps1

For a verified database-and-product-image bundle before handoff or a recovery
drill:

    .\backup-production.ps1 -FullRecoveryBundle

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

## Approved public host isolation

Sprint 1 adds application-side host separation but does not publish anything.
Keep both settings unset until the later Cloudflare and release-gate sprints:

    [Environment]::SetEnvironmentVariable('POS_PUBLIC_ORDER_HOST', 'online.raisanngam.com', 'Machine')
    [Environment]::SetEnvironmentVariable('POS_ADMIN_HOST', 'admin.raisanngam.com', 'Machine')

When configured, `online.raisanngam.com` serves only customer `/order` and
LINE-authentication routes. `admin.raisanngam.com` serves staff features only
to Admin accounts; Manager and Cashier accounts are rejected even if they know
the address and PIN. Customer ordering, LINE authentication, health, and the
print agent are not available on the Admin hostname. Manager and Cashier login
and authenticated staff sessions are accepted only from localhost. A remote
Admin must pass both Cloudflare Access and the application's second factor.

When the later Cloudflare sprint is approved, configure the host allow-list as
well. Include both public hostnames and each genuine LAN hostname or IP address
used to reach the POS; do not add wildcard entries:

    [Environment]::SetEnvironmentVariable('POS_TRUSTED_HOSTS', 'online.raisanngam.com,admin.raisanngam.com,LAN_HOST_OR_IP', 'Machine')

At that same time, set `POS_TRUST_PROXY=1` only if the Cloudflare connector is
the local process forwarding to Waitress, and keep `POS_TRUSTED_PROXY` at its
default `127.0.0.1` (or set it to the connector's verified local IP). Waitress
then accepts `X-Forwarded-*` data only from that connector. The application
will refuse to start with public hosts configured if their names are missing
from `POS_TRUSTED_HOSTS`.

Do not set either value or add a public tunnel route until Cloudflare Access,
Admin enrollment, and the customer release-validation gate are complete.

Before the Admin hostname is enabled, each Admin must sign in through the LAN,
open **ความปลอดภัยบัญชี**, set up an authenticator app, save the recovery
codes offline, then sign in again and confirm the code works. The public Admin
hostname rejects an Admin who has not completed this step. Manager and Cashier
accounts must not be enrolled for remote access and remain LAN-only.

For customer ordering through LINE LIFF, follow `docs/LINE_LIFF_SETUP.md`
before enabling the public Rich Menu link. It records the required Machine
environment values, HTTPS/Cloudflare trust condition, and live acceptance test.
Complete and retain `docs/CUSTOMER_ACCEPTANCE_3.0.md` before store go-live.

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
