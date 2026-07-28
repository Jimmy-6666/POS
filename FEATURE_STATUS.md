# Feature Status

Status reflects implementation, not a promise that every path is defect-free.
The original acceptance contract remains `REQUIREMENTS_V1.0.md`.

| Capability | State | Main verification |
|---|---|---|
| Offline Flask/SQLite/Windows/LAN foundation | Implemented | phase 1 |
| Staff auth | PIN plus admin TOTP | phase 2, 2FA |
| Product/catalog/image/reference/price management | Implemented; edit-form pricing plus name/SKU/barcode price lookup, direct audited save, and admin-only XLSX export/preview/atomic import keyed only by immutable `product_uuid` | phase 3–5, 6–10, product XLSX |
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
| Release 2.2 LINE customer lifecycle, compact checkout, maintenance, and split VPS backup | Released 2026-07-28 | version 2.2 plus full suite |
| Release 2.3 immutable product identity, admin TOTP, and admin XLSX product management | Released 2026-07-28 | 103-test full suite, UAT health/LIFF verification |
| Customer online ordering, delivery and reconciliation | Implemented; LINE LIFF identity, safe customer lifecycle, compact checkout, and five recent delivery snapshots. Guest/PIN/slip workflows are retired. | online phases 1-6 |
| Production runtime, backup, recovery, maintenance and support | Implemented; separate database/image backup, VPS image history, status/schedule UI, support bundles, and pinned signed-update hand-off | runtime and maintenance tests |
| Makro catalog enrichment and UAT import tooling | UAT only; production approval incomplete | manifest and `verify-uat.mjs` |

## Version 2.2 verification baseline — 2026-07-28

- Command: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
- Result: 88 run, 88 passed on 2026-07-28.
- The suite includes two project-context contract tests.
- Online tests cover LINE verification/profile/session/CSRF, catalogue/cart,
  idempotent orders, reservations, staff transitions, reconciliation, payment,
  delivery-time payment-method confirmation/override, customer contact display,
  staff-added items/current-price confirmation warnings, combined delivery
  assignment/start, and exactly-once sale/stock conversion.
- The reconciliation test now derives the current Bangkok business date. Its
  former fixed 2026-07-23 date became stale and caused a false failure after
  that day; application business logic was not changed.

## Makro/UAT data status — 2026-07-26

- The 388-row UAT import has 385 image matches, 31 synthetic barcodes, mock
  cost-plus-20%-rounded prices, and no zero-price active products.
- It is interface/UAT-only: owner-approved barcodes/prices and a portable input
  path are still required before production use.

## Product UUID and admin XLSX verification — 2026-07-28

Migration 23, admin TOTP, and the admin XLSX product flow are verified: 103
tests passed. XLSX tests cover admin-only server authorization, reusable export
template, UUID-only update behavior, blank-UUID creation, formula/invalid UUID/
duplicate UUID rejection, stock-ledger protection, preview non-mutation, and
transaction rollback. Export/import round trips also ignore harmless trailing
text whitespace and do not report it as an update. Confirm-time revalidation
under `BEGIN IMMEDIATE` catches deleted update targets and per-product audits
retain only changed field names, never workbook values.

## Version 2.3 verification baseline — 2026-07-28

- Command: `.venv\Scripts\python.exe -m unittest discover -s tests -q`
- Result: 103 run, 103 passed on 2026-07-28.
- UAT: `http://127.0.0.1:8001/health` returned `status: ok` and
  `database: ready`; `/api/auth/config` confirmed that LIFF is configured.
- The release includes migration 23 (`product_uuid`) and migration 24
  (admin TOTP). Both are additive startup migrations and preserve existing
  business records.

## Documentation state

The compact context set is current as of the date above. Older documents remain
valuable detailed history but contain version-oriented wording (for example,
`README.md` still leads with 1.0) and must not be treated as the sole current
status source.


## Online ordering operating model

- Lifecycle: submitted → accepted → preparing → reconciling → ready →
  delivering → completed. Rejection, customer/staff cancellation, and expiry
  are terminal and retain history.
- Stock: POS and online negative-stock controls are independent. Submission reserves; edits update the reservation; rejection,
  cancellation, or access-triggered expiry releases; completed delivery
  converts it in the same transaction that creates the sale and deducts stock.
- Payment: customers choose cash or transfer at delivery. Delivery staff must
  reconfirm the actual method at handoff and can record a cash/transfer change;
  cash records received amount/change. Customer slip upload, transfer-account
  management, and transfer verification are removed; cancellation is requested
  through the admin-configured LINE ID or mobile number.
- Customer entry uses verified LINE LIFF. First login collects a registered
  name, confirmed phone and delivery default; LINE name remains separate.
  Suspended accounts see a blocked page; guest/PIN entry and reset are retired.
- Checkout combines delivery/payment, snapshots changes without editing the
  profile, and offers five distinct recent delivery details.
- Reconciliation: prepared quantities must be complete, then every active item
  is barcode-scanned or manually confirmed with a reason before ready/delivery.
- Permissions: cashier can view/accept/prepare/reconcile/assign/deliver;
  Manager/Admin additionally cancel, reset/deactivate/correct customers, and
  manage ordering and delivery-location settings.
- Settings cover open/closed state/message, hours, minimum/maximum, expiry,
  LINE ID/mobile contact, delivery fees/minimums/room rules/order, and
  per-product order/quantity limits.
- Customer order history shows only payment-at-delivery wording, not bank
  account details. Desktop Launcher auto-printing is limited to POS receipts
  and checked-order summaries through a separate receipt print agent. Stock
  sheets and other documents retain the normal browser print preview.
- Online settings cover schedule and delivery locations. POS includes a direct
  shortcut to online order management.
