# Unreleased — Release 3.0

## Sprints 1–2 — transaction correctness

- Moved authoritative POS cart, stock, reservation, price, cost, and payment
  validation under the same `BEGIN IMMEDIATE` transaction that records the
  sale. Concurrent devices can no longer both validate the same stock before
  either stock mutation commits.
- Moved sale/void-item reads under the void write lock, added a guarded
  `voided_quantity` update, and allowed partial/full decimal voids for weighted
  products. Concurrent requests cannot over-refund or over-restock a sale.
- Synchronized the desired fresh-database `sale_items` definition with the
  existing additive `voided_quantity` compatibility migration.
- Moved online-order expiry selection under its write lock and made each state
  transition conditional on the selected status and expiry time before
  releasing reservations.
- Moved customer idempotency lookup inside the order-creation write
  transaction and recover the existing order after an unexpected unique-key
  conflict, so concurrent retries return one order instead of an HTTP 500.
- Added deterministic transaction-order and real concurrency regressions for
  checkout, voids, decimal quantities, expiry, reservations, and idempotency.
- Verification: 30 focused tests and the 129-test full suite passed.

## Sprint 3 approval hardening

- Restricted Manager/Cashier login and authenticated staff sessions to
  localhost. The configured remote Admin hostname remains Admin-only and
  requires a second factor in addition to the external Cloudflare Access gate.
- Added a signed pre-session CSRF token to staff login because Cloudflare does
  not protect browser requests sent directly to localhost.
- Fixed signed-update Admin PIN reauthentication to read the current active
  staff record rather than an absent session-principal field.
- Redacted quoted JSON credentials, authorization values, cookies, sessions,
  tokens, and phone numbers from generated support bundles.
- Upgraded Flask from 3.1.1 to 3.1.3; the lock and local environment match and
  `pip check` passes.
- Verification: 30 focused security tests and the 148-test full suite passed.

## Public internet security — Sprint 3

- Made Admin two-factor authentication compulsory for `admin.raisanngam.com`:
  only a session created after a successful authenticator or recovery-code
  check can use that hostname. Old/LAN-only Admin sessions are revoked if
  presented remotely, and unenrolled Admins must enroll from the LAN first.
- Prevented two-factor authentication from being disabled through the remote
  Admin hostname. The server records non-sensitive audit events for required
  enrollment and revoked remote sessions.

## Public internet security — Sprint 2

- Added explicit trusted-host validation, local-proxy-only forwarded-header
  handling, HTTPS-only public-session cookies, HSTS, CSP, anti-framing,
  MIME-sniffing, referrer, permission, and private-cache response protections.
- Removed customer-facing barcode and exact stock disclosure from catalog and
  cart validation responses, kept barcode snapshots internal to order creation,
  and made stock-shortage messages non-enumerating.
- Restricted customer return URLs to local order paths, reused a verified LINE
  customer session before starting LIFF, and replaced checkout DOM insertion of
  customer-controlled data with safe text-node rendering.

## Public internet security — Sprint 1

- Added disabled-by-default, hostname-based separation for the approved
  customer and Admin public hosts. The customer host permits only customer
  ordering and LINE-authentication routes; the Admin host rejects customer,
  health, and print-agent routes and permits staff sessions only for Admins.
- Added remote-login filtering and server-side Admin-role enforcement so
  Manager and Cashier accounts remain localhost-only even when a pre-existing session
  cookie is presented to the Admin host.


# Version 2.4.2 — Released 2026-07-28

## Online-order notifications

- Added the submitted-order circular/pulsing badge beside `ออเดอร์ออนไลน์` on
  the staff online-order list.
- Restricted summary polling and local looping audio to `/pos` and
  `/online-orders`. Sidebar navigation to either page carries a recent gesture
  marker so alert playback retries immediately on arrival.
- The online-order list now refreshes its current filtered view when polling
  detects a newly submitted order, with the alert attempt retained.

# Version 2.4.1 — Released 2026-07-28

## Product form hotfix

- Restored the direct selling-price field on `/products/new`; its value is now
  converted to satang and saved by the server instead of being overwritten to
  zero. The product-price shortcut is removed only from this form because the
  price can be set inline.
- Moved product-image controls into a full-width area above the barcode field,
  preventing the minimum-stock input from expanding to the image-control row.
- Product edit shows the current image before the barcode field and supports
  previewing a replacement from browse or rear-camera capture. Both controls
  use touch-friendly shared secondary-button styling; removal clears only an
  unsubmitted replacement selection.

# Version 2.4 — Released 2026-07-28

## Approved sprint 1

- Added product-camera capture on the new-product form for supported mobile
  browsers, including a preview/remove control. Captures use the exact same
  multipart validation and runtime storage path as desktop file uploads and
  are not saved until the product form submits.
- Added cashier-initiated, Manager-authorized item voids. The server validates
  an active Manager PIN (or a Manager/Admin's own PIN), applies the existing
  failed-PIN protection, and never records PIN values. Successful void audits
  retain cashier, authorizer, sale, item, quantity, product/price, amount, and
  reason data while the existing atomic stock/sale update remains intact.
- Added reconciliation `ยอดยกเลิกรวม` from valid recorded void items for the
  active closing window and stored it in additive migration 25 for historical
  close summaries.
- Matched Product list price/create actions to the shared glass-style menu
  button and added latest valid receiving cost to product pricing with one
  window-query instead of N+1 lookups.

## Approved follow-up fixes

- Replaced the editable Void quantity field with the POS-style touch `− / +`
  control and added the existing login-style PIN numpad to Void authorization.
- Product pricing now also shows the read-only current weighted-average cost
  alongside the latest valid receiving cost; selling-price editing is unchanged.
- POS barcode input now detects fast keyboard-wedge scans globally, returns
  focus to the barcode field on scanner Enter, and rebuilds scanner characters
  from physical key codes so numeric scans remain correct under a Thai keyboard
  layout.
- Made Void reasons optional while retaining an entered reason in the void and
  audit history.

## Approved online sprint 1

- Updated the customer order-detail screen with fixed-height, three-line item
  rows: two-line product names with ellipsis, compact quantities, and aligned
  line totals. Added the customer-facing five-state delivery progress display,
  removed only the customer payment-status text, kept payment-at-delivery data
  intact, made the repeat action single-line, and simplified the header to the
  catalog and order-history links.

## Approved online sprint 1.1

- Added a customer-visible status refresh action while an order is active. It
  is hidden after completion, cancellation, rejection, or expiry; cancelled
  orders now show the red `ยกเลิก` status with an intentionally empty five-step
  progress indicator.
- Added a permission-gated staff cancel action to the online-order detail page.
  It requires a confirmation dialog and reason, then reuses the existing
  transactional cancellation, reservation release, history, and audit path.
- Removed customer-visible available-quantity values. Out-of-stock products
  now show a disabled `สินค้าหมด` action only when online negative stock is
  disabled; when it is enabled, the existing configured cart limit remains
  operational without presenting the limit as stock.
- Moved the staff `ยกเลิกออเดอร์` action to the order heading, matching the
  shared primary-action size and keeping `กลับหน้ารายการ` at the far right;
  its red danger treatment, confirmation dialog, and server-side permission
  check remain.

## Approved online sprint 2

- Translated every customer-facing order and payment status shown in the staff
  online-order list, while retaining the existing internal status values for
  filtering and lifecycle validation.
- Reordered only the reconciliation display: incomplete items retain their
  original order and completed items move to the bottom immediately after a
  barcode scan or manual confirmation. No lifecycle, reservation, audit, or
  permission behavior changed.

## Approved online sprint 3

- Moved new-online-order attention from the sidebar to the POS shortcut for
  `จัดการออเดอร์ออนไลน์`. Its count and reduced-motion-aware pulse reflect
  only submitted orders.
- Added the supplied local order-alert MP3. It loops while submitted orders
  remain, stops as soon as none remain, respects the existing mute setting,
  and retries playback after a touch or key interaction when browser autoplay
  protection initially blocks it. Polling and server permissions are unchanged.
- Enlarged the POS alert count into a high-contrast circular counter with a
  clearer pulse while submitted orders remain.

## Approved online delivery cancellation follow-up

- Cashiers can now cancel online orders before they leave for delivery
  (`submitted` through `ready`) without Void-style PIN authorization. The
  existing transaction still releases reservations and retains the staff actor,
  reason, status history, and audit record. Orders already delivering or final
  remain protected from cancellation.

# Version 2.3 — Released 2026-07-28

## Release summary

- Published immutable `product_uuid` product identity across product-facing
  routes, browser payloads, held carts, inventory and online-order boundaries.
  The legacy numeric `products.id` remains private relational storage; SKU and
  barcode remain mutable unique business fields.
- Published admin-only Google Authenticator-compatible TOTP login, encrypted
  secrets, one-time hashed recovery codes, pre-session verification challenges,
  throttling/replay protection, and non-sensitive security audit events.
- Published admin-only product XLSX export/template and previewed, explicitly
  confirmed atomic import. Import uses UUID-only updates, protects existing
  stock ledgers, and reports safe row-level validation results.
- Published cache-aligned POS product selection after the UUID client migration,
  so current browsers use the matching touch-to-cart handler.

## Product XLSX details

- Added admin-only product XLSX export, upload preview, and explicit atomic
  import confirmation. The workbook has stable headers, a frozen header row,
  text SKU/barcode cells, active category/unit/status dropdowns, and an
  instructions sheet.
- `product_uuid` is the only import update key. Blank UUID creates a new
  system-identified product; unknown, invalid, or duplicated UUIDs are
  rejected. SKU and barcode remain mutable unique business values and cannot
  match existing products.
- Existing stock is read-only in XLSX; a new product's initial stock creates an
  audited opening-balance ledger movement. Import/export audits retain only the
  actor, filename, time, and summary counts.
- Prevented a no-op XLSX round trip from reporting product changes solely
  because historical text has trailing whitespace. Preview details now list
  only created/updated rows, with Thai name plus final cost and selling prices.
- Bumped the POS client asset version after switching cart identity to
  `product_uuid`, ensuring cached browsers load the matching tap-to-add handler.
- XLSX confirmation now revalidates update targets, active references, and
  business-key uniqueness after acquiring `BEGIN IMMEDIATE`; a changed target
  rolls back the whole batch. Each created or updated product also receives a
  non-sensitive per-product audit entry that records only changed field names.

# Version 2.2 — Released 2026-07-28

## Release summary

- Published verified LINE LIFF customer identity, registered-name and delivery
  profile confirmation, suspended-customer handling, and audited anonymizing
  deletion with re-registration support.
- Published the compact two-step checkout, five recent delivery snapshots,
  independent POS/online negative-stock settings, and current-price staff order
  adjustments with customer-confirmation warnings.
- Published the admin maintenance/support workflow and signed-update hand-off.
- Split database backups from product images. Database ZIPs stay small; product
  images sync by hash, replaced/deleted VPS snapshots move to `file-backups/`,
  and administrators can view status or set the daily send time.
- UAT VPS baseline contains 385 product images. Final release verification is
  recorded in `FEATURE_STATUS.md`.

## Sprint 2 follow-up — customer lifecycle and checkout

- Split negative-stock control into separate POS and online settings. Repeat
  products and cart hydration now honor the online setting when stock is below
  zero. LINE login throttling is configurable and defaults to 12 failures per
  IP in five minutes; suspended accounts do not consume that allowance.
- Restyled saved-delivery selection as a responsive Glass UI dialog and split
  the saved contact name and phone into clearly separated lines.
- Added migration 22 for a customer-registered contact name and audited
  lifecycle fields. LINE display name is retained separately.
- Suspended LINE identities now receive a stable Thai blocked page rather than
  repeatedly returning to LIFF login.
- Retired the customer PIN-reset interface. Online customer administration now
  shows customer code, LINE name, registered name, and an admin-only deletion
  action that requires the current admin PIN.
- Customer deletion preserves relational history and auditability while
  anonymizing direct identifiers and releasing the LINE/phone unique values for
  later re-registration.
- Simplified customer checkout to delivery plus payment followed by one compact
  confirmation. Changed delivery contact details are order snapshots only, and
  customers may select one of five distinct recently used delivery details.

## Sprint 2 — LINE LIFF customer identity

- Added server-side LINE ID-token verification, POS-owned customer sessions,
  authenticated identity endpoints, and a required delivery profile.
- Retired new phone/PIN registration, guest checkout, and PIN account login for
  online ordering; historical data remains intact.
- Added migration 21 and the production LIFF/Cloudflare setup runbook.
- Show a clear Thai message when a LINE customer's delivery-profile phone number
  is already linked to a different customer, rather than exposing a SQLite error.
- Add a review step for a LINE customer's delivery phone: the customer must
  choose แก้ไข or ยืนยัน after seeing “กรุณาตรวจสอบเบอร์อีกครั้ง” before it is saved.

## Online operations update

- Removed active customer slip-upload, transfer-account, and staff
  transfer-verification workflows. Online orders now retain only cash/transfer
  selection for confirmation at delivery; historic payment data is preserved.
- Made the existing negative-stock setting effective across POS sales, online
  reservations, and staff online-order edits. It now defaults to enabled to
  preserve the established operating behavior and remains manager-configurable.
- Made staff/customer session cookies Secure for HTTPS requests while retaining
  direct localhost HTTP operation; trusted reverse-proxy support is opt-in via
  `POS_TRUST_PROXY=1`.
- Made scheduled backup reporting local-first: a verified local archive is kept
  and reported even when VPS upload or file sync fails (`local_complete_remote_failed`).

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

- Split product images from the database ZIP. The Backup page now sends only
  changed images, archives a VPS snapshot before a replacement/local deletion,
  shows the latest server-upload result, and stores a daily Bangkok send time.

- Added an independent local backup service using SQLite's online backup API,
  staged ZIP publication, integrity/foreign-key checks, manifests, SHA-256
  checksums, sanitized recovery metadata, locking, and verified retention.
- Preserved the legacy `data/pos.db` archive member while making
  `database/pos.db` the canonical backup location.
- Replaced the working admin backup path with the verified backup service while
  retaining the existing permission and CSRF boundary.
- Added incremental allow-listed product-file sync with hash change detection,
  persistent inventory, immediate archival on replacement/deletion,
  retry/backoff, and backup-id linkage.
- Added restricted outbound OpenSSH SFTP transport with temporary remote names,
  atomic rename, completion markers, and optional download checksum
  verification. No VPS password or private key is stored in the repository.
- Fixed the Windows OpenSSH invocation to pass strict host-key options as
  separate arguments, ensuring the configured pinned `known_hosts` file is
  honored during automated SFTP backup runs.
- Added Windows backup/sync runners, an administrator-configurable daily
  in-process schedule, VPS provisioning/retention scripts, and non-destructive
  recovery-drill scripts. Installation/repair removes the legacy duplicate
  `SaengngamPOS-Backup` task.
- Added Sprint 2 maintenance and recovery tests. Signed update, administrator
  maintenance dashboard, and remote-support workflow remain Sprint 3 scope.

## Sprint 3 maintenance, signed updates, and support

- Added the admin-only **ดูแลระบบ** dashboard with live runtime health,
  verified backup summary, maintenance audit events, and a Thai responsive UI.
- Added redacted support ZIP generation and download. Bundles exclude the
  database, uploads, configuration, secret key, and browser profiles; the POS
  never opens remote support automatically.
- Added staged signed-update verification: versioned manifest, SHA-256 script
  hash, Windows Authenticode status, and pinned publisher thumbprint are all
  required. Applying requires the current admin PIN and the detached runner
  checks the signature/thumbprint again before handing off to the signed script.

## Version 2.3 scope — Product UUID foundation (approved Sprints 1–2)

- Added migration 23 to create, backfill, uniquely index, and make immutable
  `products.product_uuid`. The migration preserves all numeric foreign-key
  history and safely converts valid held-bill carts to UUID references.
- Switched product-facing POS, inventory, stock-count, product-management, and
  online-order boundaries to UUID-only identity. SKU and barcode remain mutable
  and unique business fields; they are not matching keys.
- Added regression coverage for legacy migration/backfill, immutability,
  UUID-only public payloads, and SKU/barcode changes retaining product identity.

## Version 2.3 scope — Admin two-factor authentication (approved Sprint 3)

- Added migration 24 and an admin-only Google Authenticator-compatible TOTP
  login step. PIN/password verification creates no staff session until the
  second factor succeeds; manager and cashier login remains unchanged.
- Added encrypted TOTP secrets, QR setup/fallback secret display, one-time
  hashed recovery codes, replay protection, failed-factor rate limiting, and
  audited enable/disable/recovery-code/login events without sensitive values.
- Added a verified second-admin recovery reset which invalidates the target
  administrator's pending challenges and active sessions before re-enrollment.
