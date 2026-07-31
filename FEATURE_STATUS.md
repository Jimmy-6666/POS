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
| Billing customers and payment | Implemented; Admin/Manager may configure and settle, Cashier denied | billing, V3.1.2 |
| Receiving, weighted-average cost, adjustment, ledger, suppliers | Implemented | inventory |
| Blind stock count | Implemented | phase 6–10 |
| Closing/reconciliation | Implemented; closing snapshots valid item-void totals | phase 6–10, V2.4 |
| Dashboard, daily/monthly reports, CSV | Implemented | phase 6–10 |
| Staff/settings/audit/backup/maintenance | Implemented; Manager may use Settings while staff/Audit/backup/maintenance remain Admin-only | phase 2, maintenance, V3.1.2 |
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
| Release 3.0.8 blocking POS manual price and audit export | Deployed 2026-07-30; 178 passed, 1 capability skip; additive migration 27 | `VERSION_3.0.8.md`, release 3.0.8, sales/runtime tests |
| Release 3.0.9 isolated local POS user and reboot-safe launcher | Released 2026-07-31; no migration | `VERSION_3.0.9.md`, launcher/runtime tests |
| Release 3.1.0 cashier-first text-only POS button grid | Deployed 2026-07-31; Migration 28; 185 passed, 1 capability skip | `VERSION_3.1.0.md`, `tests/test_release_3_1_0.py` |
| Release 3.1.1 cashier focus/manual-price refinement | UAT verified 2026-07-31; no migration; 187 passed, 1 capability skip | `VERSION_3.1.1.md`, `tests/test_release_3_1_1.py` |
| Release 3.1.2 daily price, offline create, Manager Settings/billing | UAT verified 2026-07-31; additive Migrations 29–30; 194 passed, 1 capability skip | `VERSION_3.1.2.md`, `tests/test_release_3_1_2.py` |
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

- Camera barcode quick edit, a mobile whole-baht numpad, CSP-safe bounded image
  preview, unknown-product creation, already-imaged rejection, per-staff field
  memory, stock-count recovery, and price-control create/refocus shipped.
- Full suite: 173 completed — 172 passed and one capability skip. Headless
  360×640 preview/numpad/focus checks and port-8000 health/assets passed.
- No schema migration; see `VERSION_3.0.7.md` for the retained details.

## Version 3.0.8 implementation baseline — 2026-07-30

- The post-release Windows account split keeps the server under `SYSTEM` and
  the attach-only launcher under the standard `POS` user. A launcher hotfix
  copies a read-only standard-library Python runtime to `desktop-python/`, so
  the passwordless POS account no longer needs access to the Admin user's
  private Python installation. The launcher loads `runtime_paths.py` directly
  without bootstrapping Flask, and hidden startup failures now create a POS-
  writable diagnostic plus a visible error. Runtime/UI smoke validation and
  11 focused regressions pass; no schema or business-data change. The
  post-reboot display-state file now lives under the POS-writable
  `runtime/pos-desktop/` parent so server recreation cannot inherit the
  repository-root deny ACL. A live scheduled-task run as `POS` wrote this
  state successfully and the print-agent authorization endpoint returned 200.
- Zero-price, unknown-barcode, and `MANUALPRICE` POS lines require a blocking
  positive whole-baht Cashier price. Local Thai audio prompts, scan suspension,
  touch numpad, and search refocus support the next-item loop. The deployed
  voice follow-up uses the owner-approved Thai audio at true 1.2× speed.
- Confirmed unknown barcodes create offline-only zero-price placeholders.
  Receipt lines store and show one-use audit-backed `MP-########` references.
- Audit Log filters by action and exports permission/CSRF-protected UTF-8 CSV.
  Migration 27 adds nullable unique manual-price references without rewriting
  existing sale items.
- Full suite: 179 completed — 178 passed and one existing capability skip.
  Headless mobile/desktop plus Production-LAN popup, scan-lock, focus, audio,
  and asset checks passed without confirming a price or creating a sale.
- Production migration 27, localhost/LAN health, SQLite quick check, foreign
  keys, and data preservation passed: 668 products and 0 sales remain.
- Post-release Windows startup separates the port-8000 server
  (`SaengngamPOS-Production`, `SYSTEM`, boot) from the attach-only launcher
  (`SaengngamPOS-Desktop`, standard local `POS`, logon). A local shared
  print-agent token preserves kiosk printing without letting the launcher own
  or stop the server. The account has a Public Desktop recovery shortcut.
- Current localhost health and print-agent authorization pass. Canonical LAN
  verification is pending because the observed adapter is `192.168.1.200/24`
  Public while the accepted configuration remains `192.168.0.200/24` Private.

## Version 3.0.9 release baseline — 2026-07-31

- Formalizes the two-context Windows runtime: the Production server runs as
  `SYSTEM` at boot, while an attach-only launcher runs for the passwordless
  standard local `POS` user at interactive logon.
- Elevated, repeatable setup enforces Users/non-Administrators membership,
  least-privilege ACLs, a read-only shared Desktop Python runtime, a protected
  local print-agent token, both Scheduled Tasks, and the Public Desktop
  recovery shortcut.
- Reboot-safe mutable state lives at
  `runtime/pos-desktop/display_state.json`. Visible diagnostics and
  POS-writable logs cover hidden launcher failures.
- Live POS-context state writing and print-agent HTTP 200 passed; 11 focused
  launcher/runtime regressions pass. Release-focused tests passed 13/13; the
  full suite completed 180 tests with 179 passed and one existing capability
  skip. No database or business-data change.
- Local Production repair/restart now serves Version 3.0.9 with ready health,
  print-agent HTTP 200, valid SQLite/foreign keys, and 669 products/0 sales.
  Full verification stops only at the owner-managed static-network gate.
- See `VERSION_3.0.9.md` for setup, repair, verification, and network gates.

## Version 3.1.0 release baseline — 2026-07-31

- All staff logins enter `/pos`; a fresh login collapses the sidebar and
  `ขายหน้าร้าน` is the first sidebar section.
- POS manual selection is a configurable text-only 3×3 menu/product grid.
  There are no product-image requests in this grid. Continuous positions
  paginate after every nine slots while search remains global.
- Product buttons show no barcode, use up to two enlarged name lines, and use
  approximately double-sized price text following 1366×768 UAT review.
  One-line names are vertically centered in the two-line name area.
- Menu buttons show only a larger centered two-line name; successful checkout
  clears lookup state and returns the selector to the top-level menu.
- Manager/Admin configuration is permission/CSRF protected and audited.
  Migration 28 adds only the two mapping tables without seeding or rewriting
  the migrated product catalog.
- Closing money fields share a touch Numpad; no new closing PIN exists.
- Final focused regression passed 20/20. The full suite completed 186 tests
  with 185 passed and one existing capability skip. Headless Edge at 1920×1080 confirmed
  3×3 menu/product pagination, viewport fit, no image requests, and Numpad
  input/focus behavior.
- Production port 8000 is Release 3.1.0. Migration 28 preserved 735 products,
  0 sales, and 0 sale items; SQLite integrity and foreign keys passed.
  Elevated verification passed runtime, protected startup/desktop tasks,
  Private/LocalSubnet firewall, static LAN, health, manager login, direct POS
  landing, collapsed sidebar, and Version 3.1.0 asset identity.

## Version 3.1.1 UAT candidate — 2026-07-31

- Cart quantity and remove actions return focus to the barcode/search field.
- Manual-price prompts now have an explicit no-write cancel path while
  retaining scanner blocking until confirm or cancel.
- Top-level menu slot 9 is a fixed Manual Price action; server validation
  reserves that group position while product slot 9 remains valid.
- POS-button settings now visibly style the `นำออก` action.
- No migration. Focused regression passed 24/24; the full suite completed 188
  tests with 187 passed and one existing capability skip.
- Headless Edge UAT passed R3.1.1/asset-v36 identity, slot-9 placement,
  +/−/direct-quantity/remove focus recovery, unknown and fixed-Manual
  no-write cancellation, computed destructive-button styling, and zero page
  errors. The test barcode created no product or audit row. SQLite integrity
  and foreign keys passed. Production remains healthy on Version 3.1.0.

## Version 3.1.2 source candidate — 2026-07-31

- A checked product flag forces the existing audit-backed whole-baht manual
  price workflow on every POS sale while preserving the real product name,
  UUID, receipt identity, and unchanged master price.
- Checkout revalidates the flag and manual reference server-side.
- New-product UI omits online controls and server-side creation defaults
  offline; existing products and online flags are preserved.
- Manager now has the existing Settings permission, can use `/settings`, and
  can receive partial or bulk billed payments. Cashier remains denied and the
  other Admin-only surfaces remain protected.
- Additive Migration 29 adds one checked boolean defaulting false; Migration
  30 grants the Manager permission without rewriting business rows.
- Focused regression passed 33/33. The full suite passed 194 tests with one
  existing capability skip. Headless UAT, SQLite integrity, foreign keys, and
  asset-v37 passed; the temporary product flag was restored and Production
  remains healthy on Version 3.1.0.

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
