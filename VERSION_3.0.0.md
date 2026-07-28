# Saengngam Minimart POS — Version 3.0.0

Released 2026-07-28.

## Customer-delivery release

- POS checkout, void/refund, online-order creation, expiry, and reservation
  changes now validate and mutate state under one SQLite write transaction.
- Manager and Cashier sign-in and staff sessions are localhost-only. A
  configured remote Admin hostname is Admin-only and requires both Cloudflare
  Access at the edge and application TOTP or a recovery code.
- Staff login has pre-session CSRF protection. Trusted public hosts, forwarded
  headers, secure cookies, response headers, and support-bundle redaction are
  hardened and remain disabled until provider acceptance.
- Flask is 3.1.3 and the frozen dependency set passes `pip check`.
- Production verification now matches the in-process backup scheduler and
  rejects the obsolete Windows backup task.
- Routine backups remain verified database archives with optional incremental
  VPS image sync. `backup-production.ps1 -FullRecoveryBundle` creates a
  separate verified database-and-product-image archive for offline recovery.
- `build-release.ps1` creates a committed-source ZIP, rejects runtime data and
  credential paths, and emits SHA-256 plus a JSON manifest.

## Install and verify

Extract the ZIP to a stable Windows folder and run elevated:

    .\install-production.ps1
    .\verify-production.ps1

Before customer handoff, create and copy a full recovery bundle to
owner-controlled storage:

    .\backup-production.ps1 -FullRecoveryBundle

Follow `docs/PRODUCTION_INSTALLATION.md`, `docs/PRODUCTION_OPERATIONS.md`, and
`docs/CUSTOMER_ACCEPTANCE_3.0.md`. Public LINE/Cloudflare traffic remains a
customer-site acceptance gate; it is not enabled by the release package.

## Compatibility

- No schema migration is added by Sprints 4–6.
- Existing database, uploads, secret key, and runtime configuration are
  preserved by install/repair.
- Windows 10 or newer and Python 3.11 or newer are required.
