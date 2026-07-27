# Feature Status

Status reflects implementation, not a promise that every path is defect-free.
The original acceptance contract remains `REQUIREMENTS_V1.0.md`.

| Capability | State | Main verification |
|---|---|---|
| Offline Flask/SQLite/Windows/LAN foundation | Implemented | phase 1 |
| PIN login, sessions, CSRF, roles/permissions | Implemented | phase 2 |
| Product/catalog/image/reference/price management | Implemented; edit-form pricing plus name/SKU/barcode price lookup and direct audited save | phase 3–5 and 6–10 |
| Touch POS, scan/search, held bills, cash/scan/transfer | Implemented | phase 3–5, version 2.1 |
| Billing customers, billed sales, partial/bulk payment | Implemented | billing |
| Atomic sales, receipts, stock reduction, void/refund | Implemented | phase 3–5 |
| Receiving, weighted-average cost, adjustment, ledger, suppliers | Implemented; receiving and adjustment support name/SKU/barcode lookup | inventory, phase 6–10 |
| Multi-user blind stock count and application | Implemented; manual sheets use print-only navigation-free tables with category headers | phase 6–10 |
| Daily closing/reconciliation and verification | Implemented and verified | phase 6–10 |
| Dashboard, daily/monthly reports, CSV | Implemented | phase 6–10 |
| Staff/settings/audit/backup | Implemented | phase 2 and 6–10 |
| Release 2 responsive visual refresh | Implemented | version 2.1 plus manual UI review |
| Release 2.1 Windows desktop/fullscreen launcher | Implemented | version 2.1 |
| Customer online ordering, delivery and reconciliation | Implemented; cart-first checkout, searchable customer administration, repeat purchases, staff item additions/quantity edits with confirmed-price warnings, assigned acceptance, direct reconciliation and checked-order printing included | online phases 1-6 |
| Production runtime, backup, and recovery | Sprint 1/2 implemented; updates/support deferred | runtime and maintenance tests |
| Makro catalog enrichment and UAT import tooling | UAT only; production approval incomplete | manifest and `verify-uat.mjs` |

## Verification baseline — 2026-07-26

- Command: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
- Result: 69 run, 69 passed.
- The suite includes two project-context contract tests.
- Online tests cover account isolation/rate limiting/CSRF, catalogue/cart,
  idempotent orders, reservations, staff transitions, reconciliation, payment,
  delivery-time payment-method confirmation/override, customer contact display,
  staff-added items/current-price confirmation warnings, combined delivery
  assignment/start, and exactly-once sale/stock conversion.
- The reconciliation test now derives the current Bangkok business date. Its
  former fixed 2026-07-23 date became stale and caused a false failure after
  that day; application business logic was not changed.

## Makro/UAT data status — 2026-07-26

- Import manifest: 388 rows; 385 exact Makro matches with images.
- Verified production barcodes: 0; production-ready rows: 0.
- UAT database: integrity `ok`, 0 foreign-key errors, 386 active products,
  0 zero-price products, 31 synthetic barcodes, and 385 matching images.
- Mock pricing: imported zero-price products use cost × 1.20 rounded up to the
  next 5 baht; 0 active products are below the margin rule or off the 5-baht
  step. The pre-update database is retained under `uat_runtime/backups/`.
- Policy: smallest sale unit only.
- Conclusion: suitable for interface/UAT review only. It must not be promoted to
  production until the owner confirms barcodes and selling prices.
- Portability gap: preparation/import scripts contain a hard-coded external
  source path and require a development Node runtime.

## Documentation state

The compact context set is current as of the date above. Older documents remain
valuable detailed history but contain version-oriented wording (for example,
`README.md` still leads with 1.0) and must not be treated as the sole current
status source.


## Online ordering operating model

- Lifecycle: submitted → accepted → preparing → reconciling → ready →
  delivering → completed. Rejection, customer/staff cancellation, and expiry
  are terminal and retain history.
- Stock: submission reserves; edits update the reservation; rejection,
  cancellation, or access-triggered expiry releases; completed delivery
  converts it in the same transaction that creates the sale and deducts stock.
- Payment: customers choose cash or transfer at delivery. Delivery staff must
  reconfirm the actual method at handoff and can record a cash/transfer change;
  cash records received amount/change. Customer slip
  upload and self-cancellation are removed; cancellation is requested through
  the admin-configured LINE ID or mobile number.
- Customer entry supports phone-first account lookup/automatic creation with a
  four-digit numpad PIN, plus one-time guest checkout with an optional PIN.
- Reconciliation: prepared quantities must be complete, then every active item
  is barcode-scanned or manually confirmed with a reason before ready/delivery.
- Permissions: cashier can view/accept/prepare/reconcile/assign/deliver;
  Manager/Admin additionally verify transfers, cancel, reset/deactivate/correct
  customers, and manage ordering/payment/location settings.
- Settings cover open/closed state/message, hours, minimum/maximum, expiry,
  LINE ID/mobile contact, delivery fees/minimums/room rules/order, reusable transfer
  accounts/active-account selection/QR, and per-product order/quantity limits.
- Customer order history shows only payment-at-delivery wording, not bank
  account details. Desktop Launcher auto-printing is limited to POS receipts
  and checked-order summaries through a separate receipt print agent. Stock
  sheets and other documents retain the normal browser print preview.
- Online settings are split into schedule, transfer-account, and delivery
  location sections. POS includes a direct shortcut to online order management.
