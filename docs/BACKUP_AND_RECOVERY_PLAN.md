# Backup and Recovery Plan

## Scope

Sprint 2 protects the existing offline-first SQLite POS without replacing the
database or requiring cloud availability for sales. The local POS is the
source of truth. VPS transfer is an outbound, best-effort copy.

## Local backup format

`backup-production.ps1` runs `python -m pos_app.backup_cli backup-and-sync`.
The service creates a temporary snapshot under `runtime/staging`, using
SQLite's online backup API so the active WAL database is not copied as loose
files. The published archive is named `backup-<UTC timestamp>.zip` and is
visible only after all checks pass.

Each complete archive contains:

    database/pos.db
    data/pos.db                 # legacy compatibility member
    config/recovery-config.json # sanitized, no secrets
    manifest.json
    checksums.sha256

The manifest records application/schema versions, store ID, UTC and Bangkok
timestamps, file sizes, and SHA-256 checksums. The database is checked with
`PRAGMA integrity_check` and `PRAGMA foreign_key_check`. Secrets, private keys,
tokens, the Flask secret, virtual environments, logs, caches, WAL/SHM sidecars,
product images, and development/UAT artifacts are not in the ZIP.

The default local retention is seven verified archives. Set
`POS_BACKUP_RETENTION` to change it. Invalid or incomplete archives are never
counted as restorable and are not silently deleted.

## Full recovery bundle

`backup-production.ps1 -FullRecoveryBundle` creates a separately named
`recovery-<UTC timestamp>.zip`. It uses the same verified SQLite snapshot and
manifest/checksum validation, and additionally includes regular files from
`uploads/products`. Filesystem links are rejected. The bundle is for handoff,
upgrade protection, and recovery drills; it does not change the daily
database-only schedule or its retention behavior.

Copy the bundle to owner-controlled off-machine storage. A bundle left only on
the POS disk does not protect against disk loss.

## VPS transfer

When `POS_VPS_HOST` and the required key/known-host files are configured, the
same scheduled run uploads the local archive over SFTP. It uploads to a
temporary `.part` name, renames atomically, downloads the remote archive for
checksum verification by default, then publishes a completion marker. Product
images sync separately from `uploads/products`: only new or changed files are
uploaded to `file-snapshots/uploads/products`. Before a product image is
replaced or removed locally, the VPS snapshot is moved to a timestamped
`file-backups/` path. This keeps the database ZIP small while retaining an
auditable image history. The file-sync manifest is associated with the backup
ID.

If the VPS is offline, the local archive still completes. The scheduled task
may report failure for monitoring, but it does not stop or alter POS sales.

## Restore safety

`verify` validates an archive without changing runtime data. Recovery scripts
require an empty target directory and never overwrite the active runtime. A
production restore must be performed on a replacement or stopped machine,
with a safety backup and explicit operator approval; Sprint 2 intentionally has
no web route capable of overwriting the active database.

## Retention and monitoring

The local task leaves at least one verified archive. Remote retention only
removes archives with completion markers and always keeps the newest archive.
The Backup page shows the last completed/failed server upload, database archive,
and image delta result. It also stores a daily Bangkok-time schedule in the
local settings table. The POS must be running during the scheduled minute; its
in-process scheduler starts the database backup and image sync without stopping
sales.
