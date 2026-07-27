# Disaster Recovery

## Replacement Windows computer

1. Install supported Windows and Python 3.11 or newer.
2. Extract the application to a stable directory and run the production
   installer. Do not run from a ZIP.
3. Configure the same store ID and the new machine's SFTP private key and
   known-hosts file. Never reuse a copied Flask secret as a VPS credential.
4. List or download a verified archive from the VPS SFTP account. The archive
   must have a matching `.complete` status marker.
5. Run the recovery script into a new runtime directory:

       .\scripts\recover-production.ps1 `
         -Archive 'C:\Recovery\backup-20260727T020000Z.zip' `
         -TargetRuntimeRoot 'C:\ProgramData\SaengngamPOS-Recovery'

6. Verify the recovered database and foreign keys:

       .\scripts\verify-recovery.ps1 `
         -RuntimeRoot 'C:\ProgramData\SaengngamPOS-Recovery'

7. Point a clean production installation at the recovered runtime only after
   reviewing the manifest, store ID, schema version, product image count, and
   a health/smoke test. Keep the original failed disk untouched until the
   replacement is accepted.
8. Create a new local backup after the replacement starts successfully.

The recovery archive excludes the local Flask secret by design. The clean
installation generates a new local secret; staff PIN hashes and business data
remain in the restored SQLite database.

## Non-destructive recovery drill

Use a temporary target, never the active runtime:

    .\scripts\recover-production.ps1 -Archive .\runtime\backups\backup-*.zip `
      -TargetRuntimeRoot 'C:\Temp\SaengngamPOS-Recovery-Drill'
    .\scripts\verify-recovery.ps1 -RuntimeRoot 'C:\Temp\SaengngamPOS-Recovery-Drill'

The target must be empty. The drill verifies archive checksums, SQLite
integrity, foreign keys, and restoration of uploads without modifying current
production data.

## What is deliberately not automated

There is no HTTP restore endpoint and no script option that overwrites an
active runtime. A live restore requires the operator to stop the POS, create a
safety backup, verify the selected archive, confirm schema compatibility, and
record the action locally. Those controls will be surfaced in Sprint 3's
administrator maintenance area.
