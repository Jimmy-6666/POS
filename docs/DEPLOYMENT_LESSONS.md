# Deployment Lessons

This file records operational lessons that should shorten later Production
releases. It complements the accepted release procedure; it does not replace
the backup, rollback, verification, or approval gates.

## Release 3.1.4 Production rollout — 2026-08-02

The application changes had already passed UAT. Most of the deployment time
was spent resolving Windows process, privilege, and environment differences.

### Causes of delay

1. Both accepted startup tasks were missing before deployment. The running
   service masked this until the elevated preflight ran `verify-production.ps1`.
2. Port 8000 had launcher processes in two Windows security contexts. The
   protected process exposed no command line or owner to the normal session,
   so the existing stop script could not terminate its listener without UAC.
3. `stop-production.ps1` matches launchers below the install root too broadly.
   It stopped the isolated port-8001 UAT launcher as well as Production.
4. The isolated UAT candidate did not contain its own `.venv`, while
   `start-uat.bat` expects one. After Production repair, the shared Production
   `.venv` ACL also required elevation, so UAT needed an explicit elevated
   restart using the candidate working directory and `uat_runtime/`.
5. Privileged operations were split across several helpers, producing repeated
   UAC transitions and extra state checks.
6. The first post-deploy focused run occurred before `VERSION_3.1.4.md` was
   promoted. The behavior tests passed, but the release-identity test failed
   on the missing file and forced a full rerun after documentation promotion.
7. The final verification helper used inline `python -c` through Windows
   PowerShell 5.1. Native argument quoting removed the Python string quotes,
   while strict error handling initially hid the complete stderr. A small
   file-backed, read-only checker resolved both problems.
8. The first rollback addendum serialized the existing JSON array as a nested
   array under PowerShell 5.1. Its hash was valid but its manifest count was
   wrong. A newly generated bundle explicitly flattened and re-read all 23
   entries before it was accepted.

### Checklist for the next release

Before downtime:

- Run the elevated Production verifier first. Confirm both scheduled tasks,
  the port-8000 listener owner/security context, static LAN, firewall, health,
  runtime identity, and current database counts.
- Confirm the exact UAT restart method and Python runtime before stopping
  anything. Do not assume a staged source contains `.venv`.
- Create the local database backup, full recovery bundle, and exact per-file
  source rollback archive; record every SHA-256 and re-read the manifest to
  verify its expected entry/preserved/new-file counts.
- Freeze the complete candidate, including release note and release-identity
  tests, before the first post-promotion test run.

During downtime:

- Prefer one audited elevated deployment orchestrator for stop, task repair,
  start, and privileged verification instead of repeated UAC helpers.
- Stop Production by confirmed port-8000 ownership/runtime identity, not by a
  repository-wide `pos_app.launcher` command-line match.
- Assert that port 8000 has no listener before promotion. Check port 8001
  immediately and restore UAT from its isolated source/runtime if necessary.
- Promote only the explicit manifest and verify source/target hashes.

After start:

- Verify both health endpoints, runtime Version 3.1.4, raw HTTP/source asset
  hashes, startup tasks, network/firewall, read-only database integrity and
  row counts, focused tests, full suite, and `pip check`.
- Use file-backed Python verification scripts on Windows PowerShell 5.1 and
  always retain native stderr in the deployment log.
- Update release/status/decision documentation only from measured results.

### Tooling follow-ups

These are recorded follow-ups, not changes included in Release 3.1.4:

- Narrow `stop-production.ps1` to the requested port/runtime and protect UAT.
- Parameterize the supported UAT launcher with an explicit Python path or give
  UAT an isolated environment.
- Add one structured elevated deploy command that emits a machine-readable
  result and preserves a complete log.
- Separate code release-identity tests from mutable deployment-state wording.

## Release 3.1.5 backup connection incident — 2026-08-02

- A successful interactive Admin SFTP test did not represent the scheduler.
  The scheduler runs under SYSTEM, and Windows OpenSSH rejected a private key
  owned by the Admin account as unprotected despite its narrow ACL.
- For backup incidents, test in this order: confirm the local archive/hash,
  check DNS and TCP 22, inspect key owner/ACL without reading key content, then
  run the application `test-connection` command under SYSTEM. Do not trigger a
  real Production upload until that external write is explicitly approved.
- Private key and known-hosts files must be regular files, owned by SYSTEM,
  inheritance-disabled, and explicitly accessible only to SYSTEM and
  Administrators. Verify hashes before/after ACL repair.
- Retry wrappers must preserve a bounded form of the final transport error;
  a generic retries-exhausted message turns a short owner fix into a long
  network investigation.

### Release 3.1.5 deployment delays and corrections

1. Sandbox elevation and Windows Administrator/UAC are separate boundaries.
   The first orchestrator run correctly stopped at its Administrator preflight
   and made no change. Future runs should request the single UAC elevation
   before starting the measured downtime window.
2. The first port-scoped stop helper used terminating error handling when
   querying port 8000 after its scheduled task stopped. An empty listener set
   was the expected success state but was reported as failure. Listener probes
   now accept an empty result and explicitly fail only if the port remains
   open after the deadline.
3. Promotion, health, and `verify-production.ps1` had passed, but an auxiliary
   Python runtime check ran outside the install-root working directory and
   raised `ModuleNotFoundError`. All file-backed Python checks must set their
   working directory before module execution.
4. That false failure entered rollback. Windows PowerShell 5.1 retained the
   top-level rollback JSON array as a nested object, so count validation failed
   after Production had been stopped but before any source was restored. The
   parser now forces pipeline enumeration; validate rollback parsing and file
   count before downtime, not first during recovery.
5. The Codex-side 120-second wait expired while the approved SYSTEM backup was
   still syncing images. The SYSTEM task completed normally after 116 seconds.
   A client/tool timeout is not proof of backup failure: inspect the unique
   result file, temporary task, process list, and `remote-backup.jsonl` before
   ever starting a second upload.
6. Windows PowerShell 5.1 exposes Python `unittest` progress written to stderr
   as native error records. With `ErrorActionPreference=Stop`, the first normal
   test line falsely terminated the wrapper before its exit code was read.
   Capture native output with non-terminating preference and treat the process
   exit code as authoritative; this avoids an unnecessary extra UAC run.

The corrected run finished with Production/UAT healthy on 3.1.5. The approved
SYSTEM backup uploaded and download-verified the database archive and synced
16 product images without errors. Most elapsed deployment time came from the
two incorrect helper assumptions and repeated UAC transitions, not dependency
installation or application startup. Because the port-scoped stop fix was
accepted after the original 26-file rollback archive was frozen, its exact
3.1.4 predecessor is retained in a separate hash-verified rollback addendum;
never mutate an already recorded rollback artifact in place.
