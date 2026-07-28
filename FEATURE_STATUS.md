# Feature Status

Status reflects implementation, not a promise that every path is defect-free.
The original acceptance contract remains `REQUIREMENTS_V1.0.md`; release notes
and detailed verification remain in their linked version documents and tests.

| Capability | State | Main verification |
|---|---|---|
| Offline Flask/SQLite/Windows/LAN foundation | Implemented | phase 1 |
| Staff auth | PIN plus admin TOTP | phase 2, 2FA |
| Product/catalog/images/pricing | Implemented; immutable UUID/XLSX flow, camera capture, shared menu actions, current/last receiving cost | product, XLSX, V2.4 |
| POS, sales, receipts, void/refund | Implemented; cashier initiation requires active Manager/Admin server PIN authorization with touch Void controls | phase 3–5, V2.4 |
| Billing customers and payment | Implemented | billing |
| Receiving, weighted-average cost, adjustment, ledger, suppliers | Implemented | inventory |
| Blind stock count | Implemented | phase 6–10 |
| Closing/reconciliation | Implemented; closing snapshots valid item-void totals | phase 6–10, V2.4 |
| Dashboard, daily/monthly reports, CSV | Implemented | phase 6–10 |
| Staff/settings/audit/backup/maintenance | Implemented | phase 2, maintenance |
| Release 2 responsive visual refresh and desktop launcher | Implemented | version 2.1 |
| Release 2.2 customer lifecycle, compact checkout, maintenance, backup | Released 2026-07-28 | version 2.2 |
| Release 2.3 product UUID, admin TOTP, admin XLSX | Released 2026-07-28 | 103-test baseline |
| Version 2.4 product, POS, reconciliation, and online-order updates | Released 2026-07-28 | V2.4 plus online phases, 121-test full suite |
| Customer online ordering, delivery, and reconciliation | Implemented; verified LINE identity, delivery-payment lifecycle, customer order-detail sprint 1, active-order refresh/cancel/stock-state sprint 1.1, and Thai staff workflow sprint 2 | online phases 1–6 |
| Makro catalog enrichment/import tooling | UAT only; production approval incomplete | manifest and `verify-uat.mjs` |

## Version 2.3 baseline — 2026-07-28

- `.venv\Scripts\python.exe -m unittest discover -s tests -q`: 103 passed.
- UAT health was `ok` with a ready database; LIFF configuration was confirmed.
- Migrations 23 (product UUID) and 24 (admin TOTP) are additive and preserve
  existing business records.

## V2.4 sprint 1 verification — 2026-07-28

- Dedicated V2.4 tests cover image upload/camera markup, invalid image input,
  Manager authorization/PIN rejection, audit linkage, void totals, latest cost,
  query count, and shared product action styles.
- `.venv\Scripts\python.exe -m unittest discover -s tests -v`: 114 passed.

## Version 2.4 release baseline — 2026-07-28

- Published product-camera capture, Manager-authorized POS voids, item-void
  reconciliation totals, current/latest cost pricing, customer order-detail
  improvements, Thai staff workflow labels, online-order alerts, and Cashier
  pre-delivery cancellation.
- Full suite: 121 passed. UAT health was `ok` with database `ready`; LIFF was
  confirmed through `/api/auth/config`.

## Approved online sprint 1 verification — 2026-07-28

- Customer item layout, five-stage progress, payment-status removal, and
  two-link customer header are covered by an added online phase 3 regression.
- `python -m unittest tests.test_online_phase1 tests.test_online_phase2 tests.test_online_phase3 tests.test_online_phase4 tests.test_online_phase5 tests.test_online_phase6 -v`: 33 passed.

## Approved online sprint 1.1 verification — 2026-07-28

- Added online phase 3–4 regressions for the customer refresh/cancelled
  display, hidden availability with both online negative-stock modes, and the
  staff cancellation confirmation/transaction path.
- Focused phase 3–4: 16 passed; full online phases 1–6: 33 passed.

## Approved online sprint 2 verification — 2026-07-28

- Added phase 4–5 regressions for Thai staff-list status/payment labels and
  reconciliation card ordering after barcode and manual confirmation.
- Focused phase 4–5: 8 passed; full suite: 119 passed.

## Approved online sprint 3 verification — 2026-07-28

- POS alert UI now presents submitted-order count and attention at the online
  order shortcut instead of the sidebar. Local looping audio uses the existing
  15-second summary poll, mute preference, and browser-gesture retry path.
- Focused phases 4–5: 9 passed; full suite: 120 passed.

## Approved online delivery cancellation follow-up — 2026-07-28

- Cashier cancellation is available only from `submitted` through `ready`.
  Server-side status revalidation blocks orders that are delivering or final;
  successful cancellation keeps the existing reservation release, status
  history, and staff audit record.
- Focused phases 4–6: 14 passed; full suite: 121 passed.

## Online ordering operating model

- Lifecycle: submitted → accepted → preparing → reconciling → ready →
  delivering → completed. Rejection, cancellation, and expiry retain history.
- Stock reservations release on terminal order changes; delivery completion
  atomically creates the sale, payment, receipt, and stock movements.
- Customers use verified LINE LIFF, confirmed profile/contact details, and
  payment-at-delivery cash or transfer. Guest/PIN/slip workflows are retired.
- POS and online negative-stock permissions are independent. Manager/Admin
  retain customer/order administration; cashiers retain operational fulfilment.
- The desktop launcher auto-prints only POS receipts and checked-order
  summaries. Stock sheets and other documents use browser print preview.

## Documentation state

The compact context set is current as of the latest verified sprint. Older
documents remain useful history but must not override the accepted contract.
