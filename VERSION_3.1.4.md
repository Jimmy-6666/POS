# Saengngam Minimart POS — Version 3.1.4

Status: deployed to UAT 2026-08-01; deployed to Production 2026-08-02

Migration: none

Version 3.1.4 is the current Production release on port 8000 with `runtime/`.
The isolated UAT instance remains available on port 8001 with `uat_runtime/`.

## POS cashier continuity

- Every cart render moves the `รายการขาย` scroll container to its bottom, so
  the newest scanned line remains visible when the cart exceeds its viewport.
- Clicking a non-action area returns focus to the barcode/product lookup with
  scroll prevention, keeping the register ready for the next hardware scan.
- Buttons, links, form controls, labels, dialog content, content-editable
  elements, and explicit actions retain their normal interaction and are not
  intercepted.
- Open manual-price, payment, success, and held-bill dialogs continue to block
  scanner-focus recovery until their existing workflow resolves.

## XLSX product import

- For an existing product identified by `product_uuid`, `stock_quantity` is
  ignored completely during preview and confirmation. Negative, stale, or
  otherwise unrelated exported stock values cannot reject catalog changes and
  never update the database stock balance.
- Stock remains ledger-owned. Admins use receiving, stock adjustment, or
  stock count to change an existing balance and retain movement history.
- A new product with a blank UUID retains the accepted audited opening-stock
  workflow. Its opening quantity is still validated and creates an
  `opening_balance` movement when nonzero.

## Data and compatibility

- No schema migration, database rewrite, or permission change.
- Sale, payment, receipt, print diagnostics, manual-price, negative-stock,
  and online-order rules are unchanged.
- The POS JavaScript cache identity advances to `v=38`.

## Verification

- Focused automated regression: 21/21 passed before and after deployment.
- Pre-deploy UAT full suite: 197 tests completed; 196 passed with one existing
  filesystem-capability skip. Post-deploy elevated full suite: 197/197 passed.
- `pip check` reported no broken requirements.
- Live UAT runs Release 3.1.4 from the isolated source on port 8001 with
  `uat_runtime/`; health is `ok`/`ready` and the served POS asset exactly
  matches candidate `v=38`.
- Browser QA built a ten-line cart: `scrollHeight=1445`, `clientHeight=430`,
  `scrollTop=1015`, and `atBottom=true`. A non-action heading click returned
  focus from `holdButton` to `productLookup`; an open payment dialog retained
  `receivedInput` focus and did not return focus to the scanner. Reload
  cleared the unsaved cart, and there were zero console errors. The owner also
  manually confirmed both Cashier behaviors.
- A live UAT XLSX export/parse round-trip covered all 670 products, including
  four negative-stock products: 670 unchanged, zero rejected, and zero
  validation errors. It was preview-only and wrote no product or stock data.
- SQLite quick check is `ok`, foreign-key violations are zero, Migration 30
  remains latest, and the existing UAT snapshot remains 670 products/5 sales.
- Production was deployed after explicit owner approval. The live runtime
  reports Version 3.1.4 with health `ok`/`ready`, and its served POS asset
  matches the approved UAT/source SHA-256
  `349a9a3939d99b518731d2cdf1608ac4381a6ec736e610ec8c653d729cc377e1`.
- Production deployment created both a local database backup and a full
  recovery bundle plus an exact source rollback bundle before promotion.
  Existing Migration 30 remained latest; no schema migration was added.
- Final read-only Production verification retained 818 products (817 active),
  211 sales, 774 sale items, and 781 stock movements. SQLite quick check was
  `ok`, foreign-key violations were zero, both SYSTEM/POS startup tasks were
  restored, and port-8001 UAT finished healthy.

## Deployment lessons learned

The behavior release itself was already UAT-approved. Rollout time increased
because both startup tasks were missing, a protected port-8000 listener needed
UAC, the legacy stop script also stopped UAT, the staged UAT source lacked the
`.venv` expected by its batch launcher, Production repair restricted the
shared venv ACL, release documentation was promoted after the first focused
run, and an inline Python check hit PowerShell 5.1 quoting/error-capture issues.
The reusable root-cause notes, faster sequence, and tooling follow-ups are in
`docs/DEPLOYMENT_LESSONS.md`.
