# Saengngam Minimart POS — Version 3.1.6

Status: LINE Bot UAT promoted to Live Production 2026-08-02 (VPS-only release)

Migration: none

## Scope

- Promotes the accepted Vision Product Group UAT flow to Live Production on the
  existing public LINE Bot service. The same LINE channel, webhook, tunnel,
  allowlisted group, and signed POS boundary remain in use.
- Includes the deployed legacy Quote group-flow behavior: any member of an
  allowed group may Quote a retained image, progress, cancel, or confirm that
  group's one active legacy flow. The signed POS command records the actual
  confirmer.
- The deployed VPS release is legacy group-flow candidate.7.2 on the verified
  Vision candidate.6 base. Candidate.6 remains the rollback target.

## Explicit non-scope

- No `pos_app` file, POS frontend asset, Windows POS runtime, port-8000
  Production installation, or port-8001 UAT installation is changed.
- No schema migration, POS database rewrite, product/image write, or LINE
  webhook, tunnel, or Vision configuration change is made by this release.
- Versions 3.1.6 and 3.1.7 are VPS LINE Bot-only releases. POS application
  work may begin no earlier than Version 3.1.8; do not deploy either release
  to the Windows POS hosts.

## Verification and promotion evidence

- Owner UAT acceptance and explicit Live Production promotion were recorded on
  2026-08-02.
- The local focused LINE legacy/Vision suite passed 38/38. The full suite
  completed 247 tests: 246 passed and one filesystem-capability test skipped.
- The deployed VPS passed 24 hotfix/Vision regression tests, local and public
  health checks, config comparison, localhost-only port-8010 listener check,
  and a five-minute error-log monitor.
- Source, configuration, and SQLite rollback backups were verified before the
  atomic release switch. No credentials are recorded in this document.
