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
