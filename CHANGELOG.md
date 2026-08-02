# Release 3.1.5 PRD LINE Bot Hotfix 1 source revision — 2026-08-02

- Published one cumulative source package on the exact GitHub `v3.1.5` base
  commit with the approved LINE Bot candidate, signed POS integration,
  Migration 31, and Production repair retained together.
- Added persistent loading and validation of the protected Production LINE
  integration environment for the SYSTEM server path.
- Fixed the post-reboot Public Desktop shortcut: the standard-user
  attach-only launcher no longer attempts to read the server-only LINE secret
  file. Server, backup, and verification paths still load it, so the
  SYSTEM/Administrators-only ACL remains unchanged.
- Packaging and verification did not restart or replace the running
  Production server and did not include runtime data, databases, uploads,
  credentials, private keys, browser profiles, or virtual environments.
- Final focused regression passed 33/33. The full candidate suite completed
  222 tests with 221 passed and one existing filesystem-capability skip.

# LINE Bot candidate on Release 3.1.5 — 2026-08-02

- Synchronized the approved LINE group product-maintenance bot onto GitHub
  Release 3.1.5 without replacing its SYSTEM backup-key/SFTP repair, lifecycle
  scripts, or Production/UAT version identity.
- Added a separate VPS LINE Messaging API service with signed webhook
  validation, group allowlisting, Quote + `บอท` and actual `@bot` triggers,
  visible message-action choices, and one active one-minute flow per
  `(groupId, userId)`.
- Added linear-barcode-only decoding with a 10-second bound. Downloaded image
  bytes remain memory-only; Quote ownership references expire after 24 hours
  and are swept every five minutes.
- Existing products show current name, cost, and selling price before the
  price-change flow. Cost accepts exact satang, selling price remains positive
  whole baht and must exceed nonzero cost, and the existing
  `requires_manual_price` flag is retained.
- Missing and `สินค้าไม่ทราบชื่อ (...)` products use the create/complete flow
  with defaults `อื่น ๆ`/`ชิ้น`, active/offline state, and no image step.
- Added the opt-in timestamped HMAC POS boundary, idempotent command and
  revision checks, source-hash audit provenance, and additive Migration 31.
  Failed POS connections retry every five minutes without expiry and retain
  failure logs; later success is announced in the original group with the
  requester mentioned.
- Removed every product-image add/edit option from the LINE Bot. Normal POS
  product-image maintenance is unchanged.
- Added VPS/systemd setup, LINE Console guidance, Production deployment prompt,
  and focused integration/workflow regression tests.
- Verification passed 43 focused tests (42 passed, one filesystem-capability
  skip) and the complete 221-test suite (220 passed, the same skip).

# Release 3.1.5 — Production backup-connection repair 2026-08-02

- Diagnosed the failed 02:00 scheduled backup: the verified local SQLite
  archive completed, DNS/TCP 22 were healthy, but Windows OpenSSH under SYSTEM
  rejected the private key because its owner was the interactive Admin user.
- Repaired the live Production key owner to SYSTEM while preserving its
  content SHA-256 and SYSTEM/Administrators-only ACL. Read-only SFTP `pwd` and
  candidate `backup_cli test-connection` probes now pass under SYSTEM.
- Added repeatable Production secret-ACL repair and read-only SYSTEM
  connection-test scripts. Production repair warns rather than blocking local
  POS startup if optional VPS configuration is broken; Production verification
  reports the exact local secret problem.
- SFTP retries now retain the final bounded actionable error instead of
  logging only a generic retries-exhausted message. No key/database content is
  logged and the remote archive/image layout is unchanged.
- No migration or business-data change. Candidate focused tests pass 34/34,
  full suite 201/201, `pip check`, PowerShell parse, Python compile, dummy ACL
  repair, and SYSTEM connection checks pass.
- Post-deploy focused regression passed 23/23 and the full suite passed
  201/201. SQLite integrity, foreign keys, Migration 30, and all measured
  product/sales/stock row counts remained unchanged.
- After explicit owner approval, promoted the exact 26-file Release 3.1.5
  source to Production without a migration or business-data rewrite. Elevated
  lifecycle/runtime verification and `pip check` passed; Production port 8000
  and isolated UAT port 8001 finished `ok`/`ready`.
- Ran one explicitly approved full `backup-and-sync` under
  `NT AUTHORITY\SYSTEM`. Local and remote-download SHA-256 matched for
  `backup-20260801T181553Z.zip`; product-image sync uploaded 16/16 with zero
  errors.
- Scoped `stop-production.ps1` to the requested listener port and exact
  Production desktop script so isolated UAT below the install root is not
  stopped by a broad launcher match.
- Preserved the original 26-file 3.1.4 rollback archive and added a separate
  hash-verified two-entry rollback addendum for the later Production stop
  lifecycle change.

# Release 3.1.4 — Production release 2026-08-02

- Added automatic bottom scrolling to the POS `รายการขาย` container after
  every cart render so the most recently appended scan stays visible.
- Added scanner-focus recovery when the Cashier clicks a non-action area;
  interactive controls and open blocking dialogs retain their existing focus.
- Changed existing-product XLSX preview/import to ignore `stock_quantity`
  completely. Negative or stale exported balances no longer reject unrelated
  catalog edits and cannot bypass the stock ledger.
- Preserved new-product audited opening stock and its `opening_balance`
  movement. No schema migration or business-data rewrite is required.
- Advanced UAT and canonical Production to Release 3.1.4 and POS asset `v=38`
  after explicit owner approval.
- Focused Release 3.1.4, XLSX, POS focus, and sales regression passed 21/21.
  The full suite completed 197 tests with 196 passed and one existing
  filesystem-capability skip; `pip check` passed.
- Before Production approval, deployed the isolated source to UAT port 8001.
  Browser QA verified a
  ten-line cart at its exact scroll bottom, non-action focus recovery, dialog
  focus protection, asset `v=38`, cart cleanup without a sale, and zero
  console errors. The owner manually confirmed both Cashier behaviors.
- Live XLSX round-trip parsed all 670 UAT products, including four negative-
  stock rows, with zero rejected/errors and no writes.
- Before Production promotion, created a verified local database backup, full
  recovery bundle, and exact source rollback archive. The protected SYSTEM
  server and POS desktop startup tasks were repaired.
- Post-deploy focused tests passed 21/21, the elevated full suite passed
  197/197, and `pip check` passed. Production/UAT health, runtime Version 3.1.4,
  raw served/source asset hash, static network/firewall, SQLite quick check,
  zero foreign-key violations, Migration 30, and unchanged measured business
  row counts all passed.
- Recorded the process/UAC/UAT/runtime causes of deployment delay and the
  next-release checklist in `docs/DEPLOYMENT_LESSONS.md`.

# Release 3.1.3 — Production print-driver diagnostics update 2026-07-31

- Preserved the existing browser print-agent and Windows printer-driver path.
- Added a POS-user-readable, bounded `runtime/pos-desktop/print-diagnostics.log`
  that correlates sale/reconciliation, queue, browser-agent, print-request,
  afterprint/timeout, and acknowledgement events by job ID.
- Added a launcher button that opens the local log in Notepad for a `POS`
  account test without Codex access. The log excludes token/PIN/session data
  and cannot affect a completed transaction.
- Removed the printable iframe from automatic receipts. Edge now prints the
  actual top-level receipt HTML, then acknowledges the job on `afterprint`.
- Prevented the Wilai fallback helper and production launcher from running two
  hidden Edge print agents after restart.

# Release 3.1.2 — released 2026-07-31

- Added an additive per-product daily manual-price flag (Migration 29).
- Reused the blocking Cashier price Numpad for flagged positive-price
  products and retained their real product identity in Audit, sale items, and
  receipts.
- Added server-side quote/checkout enforcement so catalog price cannot bypass
  a flagged product's required manual price.
- Removed online controls from new-product UI and made every standard
  application create path offline by default without changing existing
  products.
- Added focused Release 3.1.2 migration, create-form, forged-request,
  POS API, manual-price, checkout, Audit, and receipt regression coverage.
- Granted Managers the existing Settings permission through additive
  Migration 30. Managers can use `/settings` and settle billed balances
  individually or in bulk; Cashiers remain denied and Admin-only staff,
  Audit, backup, maintenance, security, and XLSX functions remain protected.
- Verified 33 focused tests and the 194-test full suite with one existing
  filesystem-capability skip. Headless Edge UAT passed asset-v37, create/edit,
  flagged-product price prompt, real-name cart/reference, and focus recovery;
  SQLite integrity and foreign keys passed.
- Deployed the canonical port-8000 Production instance after verified local
  backup, full recovery bundle, and Version 3.1.0 source rollback. Migrations
  29–30 preserved 742 active products and the zero-sale history; integrity,
  foreign keys, runtime, static LAN, firewall, health, and version checks
  passed.
- Repaired the missing startup tasks during deployment. The server again runs
  as `SYSTEM` at boot and the attach-only launcher runs for the passwordless
  standard `POS` user at logon; the Public Desktop shortcut was preserved.
  Port-8001 UAT remained healthy.

# Release 3.1.1 — released 2026-07-31

- Returned focus to the POS barcode/search field after Cashier quantity
  increase, decrease, direct quantity edit, and line removal.
- Added explicit cancellation to the blocking manual-price dialog. Cancelling
  discards the unresolved line, writes no placeholder/cart/audit record, and
  returns to the main menu ready for the next scan.
- Reserved top-level menu position 9 for a fixed Manual Price button that
  reuses the audited `MANUALPRICE` workflow. Product slot 9 inside a menu
  remains available.
- Rejected Manager/Admin attempts to create or move a top-level menu into the
  reserved position and updated configuration guidance.
- Styled the `นำออก` control in POS-button settings as a destructive action.
- Added focused Release 3.1.1 regression coverage; no schema migration.
- Verification passed 24/24 focused tests and the full 188-test suite
  (187 passed, one existing capability skip). Headless Edge UAT verified all
  four cart-focus actions, slot 9, both no-write cancel paths, computed remove
  styling, zero JavaScript errors, SQLite integrity, and foreign keys.
- Released as the first of the two approved versions and deployed cumulatively
  through Version 3.1.2.

# Release 3.1.0 — 2026-07-31

- Changed every successful staff login to enter the POS sale screen and added a
  one-shot fresh-login sidebar collapse without changing later manual sidebar
  control.
- Moved the `ขายหน้าร้าน` sidebar section to the top.
- Replaced the POS category rail and image cards with a configurable text-only
  3×3 menu/product grid. Positions paginate in groups of nine, and global
  search, exact barcode scanning, cart, manual pricing, and payment remain.
- Tightened product-button typography after UAT review: barcode text is hidden,
  names use up to two substantially larger lines, and selling-price type is
  approximately doubled to fill the button without adding images.
- Vertically centered one-line product names inside the reserved two-line name
  area while retaining the two-line clamp and price separation.
- Simplified menu buttons to a centered two-line name only, removed the menu
  number/manual/helper labels, and aligned each open menu title with the Back
  control.
- Successful checkout now clears the lookup and returns the manual selector to
  the top-level menu for the next sale.
- Added Manager/Admin `ตั้งค่าปุ่มขาย` configuration with audited group/item
  create, update, move, enable/disable, and remove operations.
- Added additive Migration 28 for `pos_button_groups` and `pos_button_items`;
  no product, category, sale, stock, or image row is rewritten.
- Added a shared touch Numpad to the four close-round money inputs. No
  close-round PIN requirement was added.
- Added focused Release 3.1.0 coverage for migration integrity, permissions,
  audit records, APIs, text-only rendering, login landing, pagination wiring,
  and reconciliation Numpad behavior.
- Final verification passed 20/20 focused tests and the full 186-test suite
  (185 passed, one existing capability skip). A 1920×1080 headless check
  confirmed 3×3 paging, no image requests, viewport fit, and Numpad focus.
- Deployed canonical Production on port 8000 after creating a 3.0.9 source
  rollback and verified full recovery bundle. Migration 28 preserved 735
  products and 0 sales; integrity, foreign keys, protected server/desktop
  tasks, backup schedule, static LAN, firewall, health, manager login, direct
  POS landing, collapsed sidebar, and Version 3.1.0 assets all passed.

# Release 3.0.9 — 2026-07-31

- Advanced application, mobile badge, Production runtime, and Desktop
  Launcher identity to Version 3.0.9.
- Added `VERSION_3.0.9.md` as the accepted behavior, initial setup, repair,
  verification, security-boundary, and reboot-recovery contract for the local
  standard `POS` account.
- Release-focused tests pass 13/13. The full suite completed 180 tests: 179
  passed with one existing filesystem-capability skip.
- Fixed elevated install/repair initialization to run from the explicit
  installation root instead of inheriting `System32`, preventing a false
  `ModuleNotFoundError: pos_app` during UAC repair.
- Deployed local Production Version 3.0.9. Health/database readiness, SQLite,
  foreign keys, print-agent authorization, POS ACLs, and 669-product/0-sale
  preservation passed. Full verification stops only at the unchanged
  `192.168.0.200/24` Private-network gate.

- Fixed the POS-user `Python venv launcher ... Access is denied` startup error.
  The attach-only launcher now uses a read-only shared standard-library Python
  runtime at `C:\SanngamPOS\desktop-python` instead of resolving the `.venv`
  base interpreter under the Admin user's private `AppData`.
- Fixed the follow-up silent exit from that shared runtime: importing
  `pos_app.runtime_paths` had executed `pos_app/__init__.py` and required Flask
  before the launcher could write an error. The launcher now loads the
  standalone helper directly, and the hidden PowerShell wrapper records
  bootstrap output under `runtime\pos-desktop` plus shows a visible error.
- Fixed the remaining reboot-only `display_state.json` permission failure.
  Server and launcher now share `runtime\pos-desktop\display_state.json`, so a
  replacement file inherits the POS-writable parent ACL instead of the
  repository-root deny ACL. A live scheduled-task run as `POS` updated the
  state after server restart, and the protected print-agent returned HTTP 200.
- Elevated kiosk configuration builds and smoke-tests the shared runtime,
  imports `pos_desktop` without Flask, initializes the Tk launcher UI, updates
  the recovery shortcut, and leaves the `SYSTEM` server process and Production
  database untouched. Focused launcher/runtime regressions pass 11/11.
- Split Windows startup into `SaengngamPOS-Production` (`SYSTEM`, boot,
  background server) and `SaengngamPOS-Desktop` (standard local `POS`, logon,
  attach-only launcher). Closing or reopening the launcher no longer stops or
  replaces the server.
- Added a persistent local print-agent token, isolated POS Edge profiles,
  disabled Edge sign-in/sync prompts, and retained token-protected kiosk
  receipt printing.
- Added `configure-production-kiosk-user.ps1` to create the passwordless
  non-admin `POS` account, restrict source/runtime writes, register both tasks,
  and create `C:\Users\Public\Desktop\Saengngam POS.lnk`.
- Focused launcher/runtime tests pass 10/10. Production localhost health,
  single-listener, and print-agent 200/404 authorization checks pass.
- Full network verification stops at the accepted static-network gate: the
  active adapter is currently `192.168.1.200/24` Public while the retained POS
  contract is `192.168.0.200/24` Private. No network setting was changed.

# Release 3.0.8 — 2026-07-30

- Replaced both manual-price alerts with the owner-approved natural Thai
  voice at true 1.2× speed. The missing-product alert keeps the approved pause
  between “ไม่พบสินค้า” and “กรุณาระบุราคา”; the short alert is cut directly
  from the latter phrase. SHA-256 and WAV duration are pinned by regression.
- Added a 12-button touch numpad to the blocking Cashier price dialog:
  digits 0–9, clear, and backspace. Entry remains whole-baht, capped at seven
  digits, keyboard-compatible, and protected from fast hardware scans.
- Headless Edge at 360×640 and 360×600 passed all numpad actions, seven-digit
  cap, scanner restoration, save/refocus, zero overflow, and exact served
  audio hashes.
- Blocked zero-price POS sales from completing at 0. Zero-price products and
  unknown scanned barcodes now require a positive whole-baht Cashier price in
  a modal that suspends subsequent scanner input until confirmation.
- Added reserved barcode `MANUALPRICE` for direct manual-price lines.
- Added local Thai voice alerts for missing/zero-price items and the reserved
  manual-price barcode; no browser speech service or network is required.
- Unknown confirmed barcodes create active offline-only placeholder products
  with zero master price/cost/stock. Repeated sales keep prompting until the
  master price is set through product management.
- Added audit-backed running references (`MP-########`) to manual-price receipt
  lines. Server-side checkout revalidates Cashier, product, barcode, price,
  audit record, and one-time reference use.
- Added Audit Log action filtering and CSRF-protected UTF-8 CSV export, with
  export actions recorded in the audit log.
- Added migration 27: nullable `sale_items.manual_price_reference` plus a
  partial unique index. Existing sale items remain unchanged.
- Added a regression that starts from a simulated version-26 database, so
  migration 27 adds its column before creating the unique index.
- Full suite: 179 completed (178 passed, one existing capability skip);
  `pip check`, Python/JavaScript syntax, and diff checks passed.
- Headless Edge passed mobile/desktop popup bounds, hardware-scan rejection,
  next-search focus, audio, running reference, Audit filter, and CSV download.
- Deployed canonical Production on port 8000 after verified local backup
  `backup-20260730T134948Z.zip`. Migration 27, localhost/LAN health, served
  assets, SQLite quick check, foreign keys, and preservation of 668 products
  with 0 sales passed. Production smoke opened the zero-price and
  `MANUALPRICE` prompts without confirming, so it created no product, manual
  audit, sale, or sale item.
- Canonical verification reaches the existing operational warning that
  `SaengngamPOS-Production` is absent from Task Scheduler; the running service,
  version, migration, network, firewall/runtime checks before that gate pass.

# Release 3.0.7 — 2026-07-30

- Added “สแกนด้วยกล้อง” to `/products/quick-edit`, using the bundled
  BarcodeDetector/ZXing capability already used by stock count.
- Extracted one shared local camera-scanner helper for quick edit and stock
  count. It stops live streams on result, close, and page exit, prevents
  duplicate lookup submission, and keeps manual/USB/Bluetooth entry.
- Added automatic native photo-capture fallback for quick edit when the shop
  LAN's HTTP origin cannot use the secure-context live camera API.
- On phones, an eligible scan now opens a whole-baht price numpad immediately
  while keeping product name and barcode visible. The first digit replaces
  the remembered/current price; confirm reveals the existing one-screen editor
  and the keypad can be reopened from the price field.
- Fixed quick-edit image preview by moving file/camera event ownership into
  `product-quick-edit.js` and forcing an explicit visible state.
- Replaced the CSP-blocked quick-preview `blob:` URL with an allowed `data:`
  URL, added stale asynchronous-read protection, and constrained preview,
  actions, and long filenames to the mobile image grid. Cache keys are now
  quick-edit JS `v=6` and v3.0.7 CSS `v=3`.
- Changed quick-edit scan outcomes: an already-imaged product now shows
  “สินค้านี้มีรูปแล้ว” before returning to scan, while an unknown barcode
  opens the editor so Manager/Admin can create the missing product immediately.
- Quick-created products receive a UUID, zero cost/stock, server-enforced
  active status, and a `create_product` audit. Barcode/reference/price checks
  and the image-eligibility recheck remain inside the write transaction.
- Quick edit now remembers the last successful category and unit per staff in
  addition to whole-baht price; inactive remembered references are ignored.
  The quick-edit JavaScript cache key is now `v=5`.
- Fixed blind stock count so an unknown barcode shows a visible error, clears
  the rejected code, and immediately restores focus to the barcode input
  without opening quantity entry. Successful lookup still focuses quantity.
- Price control now treats an exact barcode as a scan loop: Enter saves once,
  clears the completed lookup, and focuses barcode entry for the next item.
  Name/SKU searches and failed saves retain their existing query.
- Missing price-control searches now open a responsive add-product popup with
  whole-baht price, Thai name, category, and unit but no image controls. Save
  creates an active, audited UUID product with zero cost/stock and returns to
  an empty focused scanner; duplicate protection is transactional and the
  quick-edit workflow remains independent.
- Price-control creation remembers only the last successful category and unit
  per staff session. Price/name reset, inactive references are ignored, and
  quick-edit memory keys remain separate.
- No database migration. Focused suites: 21 passed. Full suite: 173 tests
  completed (172 passed, one existing filesystem-capability skip); `pip check`
  passed.
- Browser QA at 360×640 passed first-digit replacement, multi-digit entry,
  keypad reopen, visible product identity, and the complete editor with no
  document/form overflow or console error. Isolated browser QA also passed the
  stock-count focus paths. Playwright Edge under the Admin-equivalent CSP
  passed browse/camera preview, remove/restore, a real 576×1280 JPEG with a
  long filename, bounded columns, and zero console errors.
- Restarted canonical Production port 8000 onto Release 3.0.7. Health is `ok`;
  the live v3.0.7 CSS and scanner/quick-edit/stock-count/price JavaScript
  match verified source exactly. Read-only QA preserved the current 479
  products (362 zero-price, 463 no-image, all zero-stock, 10
  online-enabled); SQLite quick check and foreign keys are clean.
- Site-LAN verification is deferred because the server is temporarily on
  another LAN. By owner instruction the accepted `192.168.0.200/24` POS
  config remains unchanged. `SaengngamPOS-Production` is absent from Task
  Scheduler and requires an Administrator PowerShell session to restore.

# Release 3.0.6 — 2026-07-30

- Added Manager/Admin “แก้ไขสินค้าด่วน” under “สินค้าและคลัง” with exact
  barcode scan, photo/file preview, whole-baht selling price, three-line Thai
  name, category, unit, audited save, and automatic return to the next scan.
- Remembered the last quick-edit price per signed-in staff account and
  prefilled it for the next item, without showing or accepting satang.
- Unknown barcodes and products that already have an image share the same
  “ไม่พบสินค้า” confirmation. The server rechecks image absence inside the
  write transaction to prevent direct or concurrent duplicate edits.
- Changed the found-product mobile UI to a compact full-viewport dialog above
  the app bars. Photo controls, preview, fields, close, and save fit without
  scrolling at verified 393×873 and 360×640 viewports; very short
  keyboard-constrained screens retain an internal-scroll fallback.
- Made every sidebar heading collapsible with one `^` caret rotated 180
  degrees for collapsed state. Online orders and POS sales start expanded;
  all other sections start collapsed.
- Allowed only `/order/policy?embedded=1` to be framed by the same customer
  origin while retaining frame denial for standalone policy and other pages.
- No database migration. Verification: 23 focused tests and 58 wider
  release-critical regressions passed. Browser QA passed the scan, preview,
  save, remembered-price, duplicate-rejection, sidebar, and responsive flows
  without console warnings/errors. The full suite completed 166 tests
  (165 passed, one existing filesystem-capability skip).
- The mobile-dialog follow-up passed 10 focused/context tests and Browser QA
  with no document/form overflow or console warnings/errors.
- Restarted canonical Production port 8000 for the mobile-dialog follow-up;
  health is `ok`, the CSS cache key is `v3`, and served CSS/JS hashes match
  the verified source.
- Restarted canonical Production port 8000 so the Python process loaded the
  embedded-policy header fix. Live Cloudflare verification now returns
  `SAMEORIGIN`/`frame-ancestors 'self'` for `?embedded=1`, while the standalone
  policy remains `DENY`/`frame-ancestors 'none'`.

# Release 3.0.5 — 2026-07-30

- Replaced the customer-header policy button with a required acceptance
  checkbox on first-time LINE profile completion.
- The terms/PDPA text is a link that opens the public combined policy in a
  responsive modal, with normal page navigation as a no-dialog fallback.
- Enforced acceptance on the server during the profile review/confirmation
  flow while leaving completed customer profile edits unchanged.
- Changed the registration labels to “ชื่อสำหรับติดต่อ (สามารถใช้ชื่อเล่นได้)”
  and “สถานที่จัดส่ง (เปลี่ยนแปลงตอนสั่งซื้อได้)”.
- No stored consent record or database migration.
- Verification: 33 focused LINE-auth/online/public-host/release-identity tests
  passed. Browser verification passed at mobile, tablet, and desktop widths
  with no horizontal overflow; popup use leaves the checkbox unchanged. The
  full suite completed 158 tests (157 passed, one existing
  filesystem-capability skip).

# Release 3.0.4 — 2026-07-30

- Added one touch-friendly “เงื่อนไขการใช้งานและ PDPA” button to the customer
  online header, linking to the existing public `/order/policy` route.
- Combined the existing privacy policy with product-image terms explaining
  that packaging, labels, and appearance may differ from displayed images,
  while quantity and unit follow product/order text.
- Added clickable phone and LINE contact details sourced from POS online
  settings for mismatched-item or pre-purchase questions.
- No consent-record storage, database migration, or change to customer
  authentication/order processing.
- Verification: 25 focused public-policy/public-host/release-identity tests
  passed. Browser verification passed at desktop and mobile breakpoints with
  no horizontal overflow or console warnings/errors. The full suite completed
  158 tests (157 passed, one existing filesystem-capability skip).

# Release 3.0.3 — 2026-07-29

- Added the approved local `noimage.png` default for products without a saved
  image across POS, customer ordering, cart/repeat items, staff order detail,
  and product edit views.
- Replaced the online “สินค้าทั้งหมด” filter with “สินค้าขายดี” as the
  default and ranked products by all-time net sold quantity from POS and
  completed online sales, subtracting Void quantities.
- Kept unsold products visible after sold products and retained global search
  across every category.
- Preserved the Release 3.0.1 private-LAN policy and Release 3.0.2 image upload
  behavior. No database migration.
- Verification: 30 focused tests passed; the full suite completed 157 tests
  (156 passed, one existing filesystem-capability skip). Browser loaded the local
  `/order` page, while deeper interaction was skipped because browser policy
  prohibited the connected LINE access.

# Release 3.0.2 — 2026-07-29

- Fixed the product add/edit form so file selection and camera capture display
  an immediate unsaved image preview.
- Initialized product-image listeners before the optional profit calculation
  and guarded missing profit elements, preventing the page-load JavaScript
  error that disabled both image inputs.
- Restored the saved product image when an unsaved replacement is removed,
  added explicit hidden-state CSS, and bumped the form script cache key.
- Preserved the Release 3.0.1 LAN access policy and public privacy policy. No
  database migration or server-side image-storage change.
- Verification: 13 focused tests passed; browser browse/camera preview,
  remove/restore, and iPad-size layout passed with no console error; the full
  suite passed 153 tests with one existing filesystem-capability skip.

# Release 3.0.1 — 2026-07-29

- Allowed authenticated staff POS access from the configured private network
  `192.168.0.0/24`; login and existing sessions remain blocked outside that
  network.
- Added the fixed server address `192.168.0.200` to trusted hosts while
  retaining the customer-host allow-list and remote Admin role/2FA controls.
- Included the public `/order/policy` route, Thai privacy-policy template, and
  regressions that were present on the deployed customer machine but missing
  from the Release 3.0.0 source commit.
- Added idempotent Windows static-network configuration for
  `192.168.0.200/24`, gateway `192.168.0.1`, Google DNS, Private network
  profile, and a Private/LocalSubnet-only TCP `8002` firewall rule.
- Updated runtime config, desktop/console launchers, release identity, build
  requirement, installation output, validation, and operations documentation.
- No database migration. Live local/LAN health and LAN login passed; 29 focused
  tests passed; the full suite passed 153 tests with one existing filesystem
  capability skip.

# Release 3.0

## Sprints 4–6 — customer delivery

- Published the customer privacy policy at `/order/policy` without requiring
  LINE authentication, including access through the approved customer host.
- Corrected production verification to require the in-process backup schedule
  and reject the obsolete Windows backup task that install/repair removes.
- Added a separate verified full recovery bundle containing the SQLite
  snapshot and regular product-image files; scheduled daily archives and
  incremental VPS image sync are unchanged.
- Set runtime, launcher, UAT launcher, and mobile badge identity to 3.0.0.
- Added committed-ref packaging with runtime/credential rejection, SHA-256,
  JSON manifest, and a customer-site acceptance checklist.
- Added a sanitized, crash-resumable customer-machine deployment playbook and
  reusable hands-on Codex prompt covering clean/upgrade protection, physical
  acceptance, key-only VPS backup, Cloudflare/LINE gates, and redacted
  readiness reporting.
- Verification: `pip check` passed; 21 focused tests passed with one
  filesystem-capability skip; isolated Windows health/backup/restore/image
  acceptance passed; full suite passed 151 tests with the same skip.

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
