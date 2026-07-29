# Feature Status

Status reflects implementation, not a promise that every path is defect-free.
The original acceptance contract remains `REQUIREMENTS_V1.0.md`; release notes
and detailed verification remain in their linked version documents and tests.

| Capability | State | Main verification |
|---|---|---|
| Offline Flask/SQLite/Windows/LAN foundation | Implemented | phase 1 |
| Staff auth | Pre-login CSRF; staff allowed on configured private LAN only; remote Admin host requires Admin role plus TOTP/recovery code | phase 2, 2FA, public host |
| Product/catalog/images/pricing | Implemented; immutable UUID/XLSX flow, camera/file preview, approved no-image default, shared menu actions, current/last receiving cost | product, XLSX, V2.4, V3.0.2, V3.0.3 |
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
| Version 2.4.1 product-form hotfix | Released 2026-07-28 | direct price, product-image layout/current preview, touch camera control |
| Version 2.4.2 online-alert update | Released 2026-07-28 | list badge, scoped sound/polling, sidebar gesture retry, auto-refresh |
| Release 3.0 customer-delivery hardening | Approved; 151 passed, 1 capability skip | `RELEASE_3.0.md`, `VERSION_3.0.0.md` |
| Release 3.0.1 private-LAN access hotfix | Released 2026-07-29; 153 passed, 1 capability skip | `VERSION_3.0.1.md`, public-host/runtime tests |
| Release 3.0.2 product-image preview hotfix | Released 2026-07-29; 153 passed, 1 capability skip; no migration | `VERSION_3.0.2.md`, V2.4 form regression |
| Release 3.0.3 default-image and online best-seller update | Released 2026-07-29; 156 passed, 1 capability skip; no migration | `VERSION_3.0.3.md`, online phases 2 and 6 |
| Customer online ordering, delivery, and reconciliation | Implemented; verified LINE identity, public privacy policy, delivery-payment lifecycle, customer order-detail sprint 1, active-order refresh/cancel/stock-state sprint 1.1, and Thai staff workflow sprint 2 | online phases 1–6, public host |
| Makro catalog enrichment/import tooling | UAT only; portable raw JSON/CSV retrieval with exact-ID report; production approval incomplete | `work/makro-pos-import/README.md`, manifest and `verify-uat.mjs` |

## Version 2.3 baseline — 2026-07-28

- `.venv\Scripts\python.exe -m unittest discover -s tests -q`: 103 passed.
- UAT health was `ok` with a ready database; LIFF configuration was confirmed.
- Migrations 23 (product UUID) and 24 (admin TOTP) are additive and preserve
  existing business records.

## Version 2.4 release baseline — 2026-07-28

- Camera/void/cost/online workflow release; 121 tests, UAT/LIFF verified.

## Version 2.4.1 release baseline — 2026-07-28

- Direct product price/image hotfix; no migration; 122 tests, UAT/LIFF verified.

## Version 2.4.2 release baseline — 2026-07-28

- Online-order list badge, scoped audio/polling, sidebar gesture retry, and
  new-order refresh; no migration. Full suite: 122 passed; UAT/LIFF verified.

## Version 3.0.0 release baseline — 2026-07-28

- Transaction, public-host security, production verification, recovery bundle,
  and clean committed-source packaging controls are complete; no new schema
  migration. Full suite: 151 passed, with one symlink test skipped because the
  Windows test filesystem did not permit link creation.
- Isolated Windows runtime acceptance passed health, runtime Version 3.0.0,
  recovery-bundle verification, empty-target restore, and product-image
  recovery. Physical peripherals and live Cloudflare/LINE/provider checks
  remain customer-site operational gates.

## Version 3.0.1 release baseline — 2026-07-29

- Staff POS login and authenticated sessions are allowed from
  `192.168.0.0/24`; requests outside that configured private LAN remain
  blocked. Public customer/Admin hostname isolation and remote Admin 2FA are
  unchanged.
- Server Wi-Fi is static `192.168.0.200/24`, gateway `192.168.0.1`, DNS
  `8.8.8.8`/`8.8.4.4`; firewall is inbound TCP `8002`, Private profile,
  LocalSubnet only.
- Live runtime checks passed local and LAN `/health` plus LAN `/login`.
  Focused suite: 29 passed; full suite: 153 passed with one existing
  filesystem-capability skip. No schema migration.

## Version 3.0.2 release baseline — 2026-07-29

- Product add/edit forms now bind file and camera preview events before the
  optional profit summary. Missing profit fields no longer terminate the
  product-form script.
- Selecting a replacement hides the current image; removing the unsaved
  selection restores it. Explicit hidden-state CSS and `product-form.js?v=3`
  prevent stale layout/cache behavior.
- Focused suite: 13 passed. Browser browse/camera preview, remove/restore, and
  iPad-size layout passed without console errors. Full suite: 153 passed with
  one existing filesystem-capability skip.
- No schema migration and no server-side image-storage change.

## Version 3.0.3 release baseline — 2026-07-29

- Products without saved images use the approved local `noimage.png` asset in
  POS, customer ordering/cart/repeat items, staff order detail, and product
  edit views. The asset SHA-256 is pinned by a release-identity regression.
- `/order` defaults to “สินค้าขายดี”; ranking uses all-time
  `quantity - voided_quantity` across shared POS/online sale items. Unsold
  products remain visible after sold products, category pages retain scope,
  and non-empty search ignores category so it stays global.
- Focused suite: 30 passed. Full suite: 157 tests completed—156 passed and one
  existing filesystem-capability skip. Browser reached the local `/order` page, but
  deeper browser inspection was not performed because its security policy
  prohibited the connected LINE access.
- No schema migration.

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
