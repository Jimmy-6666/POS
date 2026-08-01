# Saengngam Minimart POS — Version 3.1.5

Status: released to Production and UAT 2026-08-02

Migration: none

## Backup connection repair

- The Production scheduler runs under `SYSTEM`. Windows OpenSSH rejects a
  private key owned by another account even when its ACL grants only SYSTEM
  and Administrators. Release 3.1.5 repairs the configured private key and
  `known_hosts` owner/ACL for the actual scheduler security context.
- `repair-production.ps1` attempts the repair when VPS backup is configured,
  but an optional remote-backup configuration problem does not block local POS
  startup or sales. `verify-production.ps1` reports a precise failure until
  the local secret files are safe for SYSTEM.
- `repair-production-backup-key.ps1` provides a repeatable focused repair.
  `test-production-backup-connection.ps1` runs the application SFTP `pwd`
  probe through a temporary SYSTEM task, writes no remote file, and always
  unregisters the temporary task.

## Actionable failure evidence

- SFTP retry failures retain the final bounded error detail instead of
  replacing it with only `Remote operation failed after retries`.
- The new `backup_cli test-connection` command exercises the same pinned key,
  known-hosts, port, and strict host-key settings as backup upload without
  creating a local archive or writing remote data.
- Error detail is collapsed to one line and limited to 300 characters. No key
  content, password, token, or database content is logged.

## Data and compatibility

- No schema migration, database rewrite, product change, or sales change.
- Local SQLite online backup and existing remote archive/image layout are
  unchanged.
- POS behavior and frontend asset `v=38` are unchanged.

## Current verification evidence

- The failed 2026-08-01 02:00 scheduled run created and verified its local
  archive successfully; only remote SFTP failed.
- DNS and TCP port 22 were healthy. An elevated user SFTP `pwd` passed, while
  the first SYSTEM probe exposed `UNPROTECTED PRIVATE KEY FILE` and
  `Permission denied (publickey)`.
- Production key owner changed from the local Admin account to SYSTEM while
  SHA-256 remained unchanged and ACL access remained limited to SYSTEM and
  Administrators. A second SYSTEM SFTP `pwd` passed with exit code 0.
- After explicit owner approval, a real `backup-and-sync` ran under
  `NT AUTHORITY\SYSTEM`. It uploaded and download-verified
  `backup-20260801T181553Z.zip` at SHA-256
  `c160e2f6a9732f47d005d67a5c8fda22723be6300db8127419e9f27da14487ed`.
  Product-image sync scanned and uploaded 16 files with zero errors.
- Candidate verification passed 34/34 focused tests, 201/201 full tests,
  Python compile, PowerShell parse, `pip check`, a dummy key/known-hosts ACL
  repair with unchanged hashes, and the candidate `backup_cli
  test-connection` command under SYSTEM.
- Post-deploy regression passed 23/23 affected focused tests and 201/201 full
  tests; `pip check` reported no broken requirements. Production SQLite
  `quick_check` returned `ok`, foreign keys returned zero issues, Migration 30
  remained latest, and measured row counts stayed at 818 products (817 active),
  211 sales, 774 sale items, and 781 stock movements.
- The exact 26-file source promotion completed without a migration or business
  data rewrite. Elevated Production lifecycle/runtime verification and
  `pip check` passed; both Production port 8000 and isolated UAT port 8001
  finished `ok`/`ready` on Release 3.1.5.
- The pre-release 26-file 3.1.4 rollback archive remains immutable. A verified
  two-entry addendum covers the later `stop-production.ps1` lifecycle change:
  `rollback-source-v3.1.4-stop-production-addendum-before-v3.1.5-20260802T013032.zip`,
  SHA-256 `2158bc42eeb2eb5ecfd1fcd994cefb750839a0f004ea6726017f70e2e0e1f6f4`.
- `stop-production.ps1` now stops only the requested port and the exact
  Production desktop launcher, so a staged UAT launcher below the install root
  is not selected by a broad command-line match.
