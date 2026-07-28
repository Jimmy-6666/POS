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

## Verification

- Focused Release 3 transaction, sales, and online-order suites: 30 passed.
- Seven deterministic regressions cover concurrent checkout, concurrent void,
  decimal void, concurrent idempotency, expiry lock order, expiry versus staff
  transition, and the fresh schema.
- Full suite: 129 passed in 55.385 seconds.

## Remaining release gates

- Sprint 3: maintenance, authentication, privacy, and dependency hardening.
- Sprint 4: installer, production verification, packaging, and backup state.
- Sprint 5: version 3.0.0 identity and clean-machine Windows acceptance.
- Sprint 6: final audit, merge, tag, checksums, and customer delivery artifact.
