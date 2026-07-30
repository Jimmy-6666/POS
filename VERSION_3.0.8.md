# Saengngam Minimart POS — Version 3.0.8

Prepared 2026-07-30.

## Blocking manual-price sale

- POS products whose catalog price is 0 cannot be sold at 0. An exact scan or
  product-card selection opens a blocking whole-baht price dialog.
- An unknown scanned barcode opens the same dialog. Confirmation creates an
  active, offline-only placeholder product with zero master price, cost, and
  stock, then adds the line at the entered price. Later scans keep requiring a
  manual price until a Manager/Admin updates the master product.
- Scanning the reserved barcode `MANUALPRICE` opens the dialog without first
  looking up a product.
- Scanner input is suspended while the dialog is open. A fast hardware scan
  cannot overwrite or submit the price field. After a valid confirmation,
  focus returns to the empty product search for the next item.
- Local Thai WAV alerts say “ไม่พบสินค้า กรุณาระบุราคา” for zero-price or
  unknown products and “กรุณาระบุราคา” for `MANUALPRICE`.

## Approved voice and Cashier numpad follow-up

- Both alerts use the owner-approved natural Thai voice at true 1.2× speed.
  The longer alert retains a distinct pause between its two phrases; the
  shorter alert is the latter phrase cut from the same approved audio.
- The blocking dialog provides touch digits 0–9, clear, and backspace in
  addition to physical keyboard entry. Input remains positive whole baht with
  the existing seven-digit server limit.
- Fast hardware scans still cannot overwrite or submit the active price.
  Mobile 360×640 and 360×600 QA keeps the dialog, numpad, and submit action on
  one screen without document or dialog overflow.

## Audit and receipt tracking

- Every confirmed manual price creates an immutable `enter_pos_manual_price`
  audit record for the signed-in Cashier, barcode, price, reason, time, and IP.
- Each line receives a monotonic audit-backed reference such as
  `MP-00000001`. The receipt item name shows this reference, and the same value
  is stored on `sale_items.manual_price_reference`.
- Sale completion revalidates the reference, Cashier, product, barcode, and
  price under the sale transaction. References cannot be reused, and
  `sell_with_manual_price` ties the line to its receipt and audit history.
- Audit Log supports an action filter and UTF-8 CSV export. Export is
  permission-checked, CSRF-protected, unbounded by the screen's 1,000-row
  display limit, and records its own `export_audit_logs` audit.

## Database migration

- Additive migration 27 adds nullable
  `sale_items.manual_price_reference`.
- A partial unique index prevents reuse while preserving all existing sale
  items as null. No existing price, product, sale, receipt, or audit data is
  rewritten.

## Compatibility and verification

- Existing positive-price POS sales, online confirmed-price completion,
  voids, stock movements, payment methods, receipt numbering, product
  management, quick edit, and price-control workflows remain unchanged.
- Manual prices are positive whole baht and never update the product's master
  selling price.
- Focused manual-price, audit, migration, transaction, online, and identity
  regressions passed. The full suite completed 179 tests: 178 passed with one
  existing filesystem-capability skip. `pip check` and syntax checks passed.
- Headless Edge at 360×640 and 1280×800 passed popup bounds, hardware-scan
  rejection/price restoration, search refocus, audio loading, running
  reference display, Audit filter, and CSV export.
- Canonical Production port 8000 was backed up and deployed. Migration 27,
  localhost/LAN health, served assets, SQLite quick check, foreign keys, and
  preservation of 668 products with 0 sales passed.
- Production smoke used dummy `0001` through `192.168.0.200`, opened a real
  zero-price product and `MANUALPRICE` without confirming, and therefore
  created no placeholder, manual-price audit, sale, or sale item.
- The previously known `SaengngamPOS-Production` startup Scheduled Task
  remains absent and needs an Administrator repair operation before automatic
  startup after Windows restart can be verified.
