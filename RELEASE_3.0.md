# Release 3.0

Status: in development on `codex/release-3.0`.

Release 3.0 is the final customer-delivery hardening release. It preserves the
accepted offline-first Windows/LAN product contract and produces a clean
installer before customer-site VPS, LINE LIFF, and Cloudflare configuration.

## Sprint 0 — source-control baseline

- Published local Release 2.3–2.4.2 commits and tags.
- Preserved the prior public-host/security worktree at
  `codex/v3-prework-snapshot` commit `eab1876`.
- Created the clean `codex/release-3.0` branch from tag `v2.4.2`.

## Sprint 1 — sales and void transaction correctness

- Authoritative POS cart, price, cost, stock, reservation, and payment
  validation now occurs after `BEGIN IMMEDIATE`.
- Void processing locks before reading sale/item state and conditionally guards
  `voided_quantity`, preventing concurrent over-refund and over-restock.
- Partial and full weighted-product voids accept valid decimal quantities.
- `schema.sql` now declares the `voided_quantity` column that the existing
  compatibility initializer already adds to older databases. No new migration
  or customer-data rewrite is required.

## Sprint 2 — online-order atomicity

- Expiry selects candidates and conditionally transitions them under one write
  transaction before releasing reservations.
- Idempotency lookup and order creation share one write transaction. An
  unexpected unique-key conflict recovers the already-created order instead of
  returning a server error.

## Sprint 3 — authentication, privacy, and dependency hardening

- Integrated the disabled-by-default public-host isolation package. Customer
  and Admin hostnames have separate route allow-lists, trusted-host/proxy
  validation, secure public cookies, security headers, and no-store responses.
- Manager and Cashier login and authenticated staff sessions are restricted to
  loopback requests. The configured remote Admin hostname permits only Admins
  who complete application TOTP or a recovery code after Cloudflare Access.
- Added a signed pre-session CSRF token to the staff login form. Cloudflare
  protects the remote hostname but cannot protect a browser POST to localhost.
- Fixed signed-update PIN reauthentication to read the current active Admin
  hash from the database before verifying the staged manifest and signer.
- Extended support-bundle redaction to quoted JSON credentials, authorization
  values, cookies, sessions, tokens, phone numbers, and plain key/value logs.
- Upgraded Flask from 3.1.1 to 3.1.3 and regenerated the matching direct/frozen
  dependency records. `pip check` reports no broken requirements.
- Public host settings and provider configuration remain disabled and deferred
  until the customer Cloudflare/LINE gate is executed.

## Verification

- Focused Release 3 transaction, sales, and online-order suites: 30 passed.
- Focused Sprint 3 public-host, maintenance, Admin 2FA, and auth suites:
  30 passed.
- Seven deterministic regressions cover concurrent checkout, concurrent void,
  decimal void, concurrent idempotency, expiry lock order, expiry versus staff
  transition, and the fresh schema.
- Full suite: 148 passed in 60.401 seconds on Flask 3.1.3.

## Remaining release gates

- Sprint 4: installer, production verification, packaging, and backup state.
- Sprint 5: version 3.0.0 identity and clean-machine Windows acceptance.
- Sprint 6: final audit, merge, tag, checksums, and customer delivery artifact.
