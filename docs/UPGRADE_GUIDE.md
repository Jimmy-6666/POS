# Upgrade Guide

Sprint 1 provides migration-compatible installation and repair. A signed
update agent and automatic rollback are deferred to Sprint 3.

1. Confirm the current POS is healthy with .\verify-production.ps1.
2. Stop the production process with .\stop-production.ps1.
3. Preserve the complete runtime directory before replacing application
   files. Do not copy an active SQLite database.
4. Replace only application files; retain data, uploads, backups, logs,
   configuration, and the secret key.
5. Run .\repair-production.ps1.
6. Run .\verify-production.ps1.
7. Run the full test suite from the development checkout before deploying:
   .venv\Scripts\python.exe -m unittest discover -s tests -v.

The application retains its existing ad-hoc migration behavior and records a
compatibility row in schema_migrations. Future additive migrations are
recorded with version, name, checksum, application version, timestamp, and
success state. A failed migration prevents startup.

Sprint 1 has no automatic code rollback. If startup fails, stop the POS,
restore the previously preserved application files, and run verification.
Do not replace the database or secret key as a repair step.

