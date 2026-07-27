# Version 2.1 — Development

## Sprint 3 — Update agent, maintenance, and remote support

- Added HMAC/SHA-256 release manifest and package verification, isolated staging,
  versioned release activation, automatic failure rollback, and schema-aware
  manual rollback.
- Added a durable allow-listed maintenance job queue and Thai admin dashboard for
  backup, VPS sync/test, update, support bundle, restart, and job status.
- Added sanitized support bundles and signed, expiring, replay-resistant remote
  requests with local administrator approval. No remote shell or arbitrary command
  execution is exposed.
- Added focused Sprint 3 regression tests and operational release/support docs.

## Online operations update

- Split the configurable customer-order store name onto one line per word in
  the top-left home logo, so “แสนงาม มินิมาร์ท” renders as two balanced lines.
- Added staff-side product additions and quantity changes before picking. These
  use current server prices, update stock reservations and unpaid order totals
  atomically, retain the customer's confirmed price snapshot, and show a clear
  warning to reconfirm changed prices with the customer.
- Moved delivery controls into the order-detail right column, removed the
  separate assignment button, and combined courier selection/change with the
  “บันทึกและออกจัดส่ง” action. Notes now sit below the operational workflow.
- Added additive schema version 19 for customer-confirmed item price snapshots.
- Added direct audited sale-price editing to product details and name/SKU/barcode
  lookup to price control, receiving, and stock adjustment. Exact barcode scans
  select the product and move focus to the next data-entry field.
- Added phone, name, and public-ID search to online customer administration.
- Cleaned the manual stock-count print layout so app navigation never appears
  on the sheet, and added category header rows before each product group.
- Added home/cart SVG cues to the customer shop, admin-configurable LINE/mobile
  contact actions with local vector icons, and removed bank-account details from
  customer order history in favor of payment-at-delivery wording.
- Refreshed staff order item summaries with product images and responsive glass
  cards. Delivery staff now reconfirm the actual cash/transfer method at handoff;
  method changes update the order, payment, sale, and audit records atomically.
- Delivery completion now returns to the completed order instead of opening a
  receipt page. Desktop Launcher sessions print automatically to the default
  printer, while ordinary browsers no longer open an unsolicited print dialog
  and provide an explicit print link instead.
- Limited silent printing to POS receipts and checked-order summaries by moving
  kiosk printing into a separate token-protected receipt worker. The main POS
  browser now keeps normal print preview for manual stock-count sheets and all
  other documents.
- Added repeatable UAT mock pricing: cost plus at least 20%, rounded up to a
  5-baht step. The current UAT database has 0 zero-price products and retains a
  pre-pricing backup.
- Split online settings into focused schedule, transfer-account, and delivery
  location sections; corrected oversized delivery-location checkboxes.
- Added reusable bank accounts with an active-account selector while retaining
  the established customer payment interface.
- Added an online-order shortcut beside held bills on the POS screen and made
  “ตั้งราคาขาย” prominent on product, receiving, and new-product pages.
- Added schema version 17. Existing products are online-enabled once and new
  products default to online; inactive products remain hidden from customers.
- Added schema version 18 with guest checkout contact snapshots, phone-first
  account lookup/automatic creation, and fixed four-digit numpad PIN entry.
- UAT now displays zero-price products, offers free delivery from 100 baht,
  supports cash/transfer at delivery without slips, and directs cancellation
  requests to Line @114rbvoi.
- Refreshed the customer cart with POS-style controls, add-to-cart feedback,
  themed popups and progress bars; simplified staff picking to a summary before
  the dedicated reconciliation step.
- Reworked the cart as a cart-first mobile step with “ซื้ออีกครั้ง” from prior
  orders, fixed payment-dependent cash tender visibility, and clarified the
  optional PIN label.
- Corrected the cart item renderer to keep image, item details, remove control,
  and quantity controls in one mobile card; split checkout into separate
  delivery, payment, and final order-confirmation steps.
- Replaced the catalogue cart dialog with a dedicated glass-style mobile cart
  page, including direct quantity controls, item removal, repeat purchases,
  return-to-shopping navigation, and a fixed checkout summary.
- Extended the green-white glass treatment across all customer-facing pages,
  removed the duplicated product list from final confirmation, and added
  rate-limited inline PIN login when checkout detects an existing phone account.
- Increased form-control contrast and added red field-level validation with
  focus/scroll guidance; legacy carts now hydrate current product images and
  prices from server validation instead of showing placeholders.
- Staff now select an order owner before acceptance, move directly from picking
  to reconciliation, can manually confirm without a reason, return to the order
  after completion, reopen ready orders for item edits, and print a checked-order
  summary immediately. POS sales also send receipts straight to the default
  printer through the receipt-only kiosk-printing worker.

## Documentation and workflow

- Added a compact six-file AI context set, project/module/database maps,
  durable decision and coding/design rules, and a repository-level AI working
  contract.
- Preserved the original Release 1.0 requirements and later release notes as
  authoritative sources instead of replacing them with summaries.
- Added routine search exclusions for generated runtime, browser, database,
  import, and output artifacts to reduce discovery time and token usage.
- Added automated project-context contract tests and recorded the latest
  2026-07-26 verification baseline: 52 of 52 tests pass.
- Made the reconciliation test derive the current Bangkok business date. Its
  fixed 2026-07-23 date had become stale; no reconciliation business logic was
  changed.
- Added the previously omitted Makro catalog/UAT preparation workflow to the
  project map and recorded its non-production state: missing approved barcodes,
  zero selling prices, synthetic UAT barcodes, and non-portable source paths.
- Marked legacy plan, schema, status, and Release 1.0 README content clearly as
  historical/detail sources while retaining every original requirement.

## Added in 2.1

- Added a mobile Thai customer ordering site with phone/PIN accounts, opt-in
  current catalogue, cart, delivery locations, cash/transfer checkout,
  protected slips, history, repeat order, and early cancellation.
- Added transactional reservations, idempotent submission, access-triggered
  expiry, local staff alerts, payment verification, controlled adjustment,
  picking, barcode/manual reconciliation, assignment, and cash collection.
- Integrated completed orders with the existing sale, receipt, payment and
  stock-movement logic. Reservation conversion, one linked sale, explicit
  delivery fee, and stock deduction commit atomically.
- Added schema version 16, granular online permissions, delivery/payment/shop
  settings, customer PIN reset/deactivation/phone correction, and protected
  online-payment media included in backups.

- Added a friendly Python/Tkinter Desktop Launcher with server status and window controls.
- Login opens in a normal app window, successful login switches to fullscreen, and logout restores normal size.
- Added `start-server.bat` without a persistent CMD window and a one-click Desktop shortcut.
- Widened the sales cart and enlarged its key text and touch controls for easier reading.
- Removed discount controls from the register, enlarged item names and prices, and aligned delete with the quantity controls.
- Stabilized the scan-payment layout by fully hiding cash helper controls and added the item count above the amount due.
- Added combined transfer totals to daily closing history and daily/monthly sales reports.

## Release 2.0

## Changed

- Restored the original Tahoma-first font, simplified product cards to image/name/price, and returned cash entry to the clean non-suggested amount layout.
- Balanced the payment dialog into equal left/right panels and enlarged the cash controls for touch use.
- Fixed Dashboard contrast so green buttons use white text and non-button links remain readable on light backgrounds.
- Modernized the visual system while keeping the same Thai minimart workflow and business rules.
- Redesigned the POS screen for faster scanning, searching, category browsing, and cart editing.
- Added a fixed desktop/iPad cart and a mobile cart drawer so checkout no longer requires long page scrolling.
- Improved cash and scan-payment screens with clearer totals, smart cash amounts, validation, and duplicate-submit protection.
- Simplified the dashboard into actionable sales, bill, profit, low-stock, trend, and quick-action sections.
- Added active navigation states, compact register navigation, mobile bottom navigation, and clearer menu grouping.
- Standardized management forms, tables, spacing, typography, touch targets, focus states, and responsive behavior.
- Added Release 2 launcher on port `8002`; the original app remains unchanged on port `8000`.

## Compatibility

- Existing roles, permissions, inventory logic, stock counts, receipt printing, voids, reports, and SQLite architecture are retained.
- Release 2 uses its own runtime data copy, so testing it will not change the original app database.

## Sprint 1 production foundation

- Added canonical runtime-path resolution for database, secret, uploads,
  backups, logs, support, staging, releases, browser profiles, and config.
- Added machine-readable startup validation for path containment, directories,
  secret preservation, disk space, write access, host/port, SQLite integrity,
  and foreign keys.
- Added backward-compatible schema_migrations history with a version 19
  legacy bridge and deterministic failure handling for future migrations.
- Added exact dependency lock file and Windows production lifecycle scripts for
  installation, verification, repair, start, stop, restart, and uninstall.
- Added idempotent Task Scheduler startup and a Private/LocalSubnet-only
  production firewall rule.

## Sprint 2 backup, VPS sync, and disaster recovery

- Added an independent local backup service using SQLite's online backup API,
  staged ZIP publication, integrity/foreign-key checks, manifests, SHA-256
  checksums, sanitized recovery metadata, locking, and verified retention.
- Preserved the legacy `data/pos.db` archive member while making
  `database/pos.db` the canonical backup location.
- Replaced the working admin backup path with the verified backup service while
  retaining the existing permission and CSRF boundary.
- Added incremental allow-listed product-file sync with hash change detection,
  persistent inventory, delayed deletion, remote quarantine, retry/backoff,
  and backup-id linkage.
- Added restricted outbound OpenSSH SFTP transport with temporary remote names,
  atomic rename, completion markers, and optional download checksum
  verification. No VPS password or private key is stored in the repository.
- Added Windows backup/sync runners, a daily `SaengngamPOS-Backup` scheduled
  task, VPS provisioning/retention scripts, and non-destructive recovery-drill
  scripts.
- Added Sprint 2 maintenance and recovery tests. Signed update, administrator
  maintenance dashboard, and remote-support workflow remain Sprint 3 scope.
