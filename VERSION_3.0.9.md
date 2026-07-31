# Saengngam Minimart POS — Version 3.0.9

Prepared 2026-07-31.

## Release purpose

Version 3.0.9 formalizes the accepted Windows Production account isolation and
launcher recovery behavior installed after Version 3.0.8. It does not change
POS sales, inventory, customer ordering, product data, or database schema.

## Windows operating model

- `SaengngamPOS-Production` runs the port-8000 Flask/Waitress server as
  `SYSTEM` from a Windows startup trigger. It has no interactive desktop
  window and continues running when the Cashier launcher closes.
- `SaengngamPOS-Desktop` runs only at interactive logon of the standard local
  `POS` account. It starts `pos_desktop.py` in attach-only mode and never owns,
  replaces, or stops the Production server.
- The passwordless `POS` account is a member of the built-in Users group and
  is removed from Administrators. Its password cannot be changed, the account
  does not expire, and it cannot write application source or server runtime
  data outside its explicitly granted desktop paths.
- `C:\Users\Public\Desktop\Saengngam POS.lnk` reopens a launcher that a user
  closed accidentally. The shortcut attaches to the existing background
  server; it does not launch another server.

## Isolated launcher runtime and state

- The server retains its locked `.venv`. The launcher uses the read-only
  standard-library runtime copied to `desktop-python/` during elevated setup,
  so the `POS` account does not need access to an Administrator's private
  `AppData` Python installation.
- `pos_desktop.py` loads the standalone `pos_app/runtime_paths.py` helper
  directly. It does not execute `pos_app/__init__.py` or require Flask inside
  the desktop-only runtime.
- Browser profiles, startup diagnostics, and mutable launcher state live under
  `runtime/pos-desktop/`. The shared state is
  `runtime/pos-desktop/display_state.json`; keeping it in that POS-writable
  parent ensures a replacement created by the `SYSTEM` server after reboot
  inherits the correct ACL.
- The receipt print-agent uses a generated local token. The `POS` account has
  read-only token access, while ordinary requests without the token remain
  rejected.
- Hidden startup failures are recorded under `runtime/pos-desktop/` and also
  show a visible Windows error message with the diagnostic path.

## Initial setup

Run this once from an elevated PowerShell window in the stable installation
directory:

```powershell
PowerShell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\configure-production-kiosk-user.ps1 `
  -AccountName POS `
  -StartServer
```

The command is safe to rerun for repair. It:

1. creates or re-enables the local `POS` account and enforces standard-user
   membership;
2. creates the print-agent token and POS-writable desktop runtime folder;
3. validates or installs the read-only shared Desktop Python runtime;
4. applies the install-root write deny and the narrow runtime/token/state ACLs;
5. registers the `SYSTEM` boot task and interactive `POS` logon task; and
6. creates or refreshes the Public Desktop recovery shortcut.

Install and repair initialization explicitly runs from the installation root,
so elevated UAC processes launched from `System32` still resolve `pos_app`
correctly.

If an existing account named `POS` requires a password, setup stops instead of
silently changing credentials. Reset that account intentionally before
rerunning the command.

After setup, sign out of Windows and sign in as `POS`. The launcher opens from
the logon task. If it was closed, double-click **Saengngam POS** on the
desktop.

## Repair and verification

Rerun the same elevated setup command after replacing application files,
repairing Python, or changing the local account. Then run:

```powershell
PowerShell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\verify-production.ps1
```

Verification requires:

- a valid server `.venv` and shared Desktop Python runtime;
- the `SYSTEM` boot task and interactive attach-only desktop logon task;
- the local print-agent token and valid in-process backup schedule;
- the accepted static server address and Private/LocalSubnet firewall rule;
  and
- a ready Production health endpoint.

Network verification remains subject to the accepted shop contract:
`192.168.0.200/24` on Private `192.168.0.0/24`. Localhost health may pass on a
different LAN, but that does not satisfy the site network gate.

## Compatibility and verification evidence

- A live `SaengngamPOS-Desktop` task run under the actual `POS` security
  context successfully updated `display_state.json` after the server restarted.
- The protected print-agent returned HTTP 200 with its configured token.
- Shared-runtime import, Tk initialization, PowerShell parsing, and 11 focused
  launcher/runtime regressions passed. The Release 3.0.9 focused set passed
  13/13; the full suite completed 180 tests with 179 passed and one existing
  filesystem-capability skip.
- Local Production repair and restart completed with runtime Version 3.0.9.
  Health/database readiness, SQLite quick check, foreign keys, POS state ACLs,
  and token-protected print-agent HTTP 200 passed. The read-only catalog check
  observed 669 active products and 0 sales.
- Full `verify-production.ps1` passed all checks preceding the static-network
  gate, then correctly stopped because the active adapter does not yet match
  `192.168.0.200/24` Private. No network setting was changed by this release.
- No database migration and no product, price, stock, sale, receipt, customer,
  audit, or configuration-secret rewrite is part of this release.
