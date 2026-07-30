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
| Release 3.0.4 combined terms/PDPA notice | Released 2026-07-30; 157 passed, 1 capability skip; no migration | `VERSION_3.0.4.md`, online phase 1, public-host tests |
| Release 3.0.5 registration consent popup | Implemented 2026-07-30; 157 passed, 1 capability skip; no migration | `VERSION_3.0.5.md`, LINE auth, online phase 1 |
| Release 3.0.6 quick product editor, collapsible sidebar, embedded-policy fix | Deployed 2026-07-30; 165 passed, 1 capability skip; no migration | `VERSION_3.0.6.md`, release 3.0.6, public-host tests |
| Release 3.0.7 scan/create/preview and focus workflows | Deployed 2026-07-30; 172 passed, 1 capability skip; no migration | `VERSION_3.0.7.md`, release 3.0.7, price/stock-count tests |
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

## Version 3.0.4 release baseline — 2026-07-30

- Public combined terms/PDPA includes the product-image disclaimer and POS
  phone/LINE contacts. It remains public without stored consent.
- Focused: 25 passed; browser desktop/mobile passed; full suite: 157 passed,
  one existing filesystem-capability skip.
- No schema migration.

## Version 3.0.5 release baseline — 2026-07-30

- First-time LINE profile completion requires a server-validated policy
  checkbox; its link opens the responsive policy modal. Registration labels
  include nickname and editable-delivery-location guidance.
- Focused: 33 passed; browser mobile/tablet/desktop passed; full suite:
  157 passed, one existing filesystem-capability skip.
- No stored consent record and no schema migration.

## Version 3.0.6 release baseline — 2026-07-30

- Manager/Admin quick edit handles no-image products by exact barcode, remembers
  whole-baht price per staff, saves transactionally with audit, and masks
  already-imaged products as “ไม่พบสินค้า”.
- A found product uses a compact full-viewport mobile dialog; 393×873 and
  360×640 browser QA keep image controls, fields, and save on one screen
  without document/form overflow.
- Sidebar groups collapse independently. Embedded policy permits same-origin
  framing only; all other public pages remain frame-denied.
- See `VERSION_3.0.6.md` for fields and verification.
- No schema migration.

## Version 3.0.7 release baseline — 2026-07-30

- Quick product editing adds a camera-scan action while retaining manual,
  USB, and Bluetooth barcode entry. Quick edit and stock count share one local
  BarcodeDetector/ZXing helper, and quick edit falls back to native photo
  capture on normal HTTP LAN origins.
- Mobile found-product flow opens directly to a custom whole-baht price
  numpad with the product name/barcode pinned above it. First-digit
  replacement and confirm/reopen remain. File/camera preview uses a CSP-safe
  data URL and stays bounded inside the mobile image grid.
- Already-imaged scans show their own rejection. Unknown barcodes open create
  mode; save creates an audited active UUID product with zero cost/stock.
  Price, category, and unit memory are isolated per staff.
- Blind stock restores focus after unknown barcodes. Price control saves exact
  scans on Enter; missing searches open an audited no-image create popup then
  return to scan. Category/unit memory is per staff; price/name reset.
- Focused suites: quick-edit 26 and price-control 7 passed. Full suite: 173
  completed — 172 passed and one existing filesystem-capability skip.
- Playwright Edge at 360×640 under Admin-equivalent CSP passed browse/camera
  preview, real JPEG/long filename, remove/restore, bounded columns, and zero
  overflow/console errors. Stock-count focus also passed; physical camera
  focus remains a customer-device operational check.
- Canonical port-8000 health and served-asset checks passed. Read-only QA made
  no product save; the pre-restart 479-product snapshot and integrity remain.
- Site-LAN verification is deferred while the server is temporarily on
  another LAN; the owner retained configured `192.168.0.200/24`/Private
  behavior unchanged. The startup Scheduled Task is absent and requires
  Administrator elevation to restore.
- No schema migration.

## Online ordering operating model

Sprint-specific verification history remains in `CHANGELOG.md` and the
focused online test modules.

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
