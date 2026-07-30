# Saengngam Minimart POS — Version 3.0.6

Prepared 2026-07-30.

## Quick product editing

- Manager/Admin users have a new “แก้ไขสินค้าด่วน” entry at the bottom of
  “สินค้าและคลัง”.
- The page starts with an autofocus exact-barcode scan. Unknown barcodes and
  products that already have an image both show the same “ไม่พบสินค้า”
  confirmation and expose no product details.
- Eligible products can update a selected/captured image with preview,
  whole-baht selling price, three-line Thai name, category, and unit.
- On phones, an eligible scan opens a compact full-viewport editor above the
  app bars. Image actions sit beside the preview, the form stays on one screen
  at normal mobile heights, and the close action returns directly to scanning.
  Very short viewports retain an internal-scroll fallback for keyboard safety.
- The most recently saved quick-edit price is remembered in the signed session
  for that staff account and prefilled for the next scanned item. Another
  logged-in staff account keeps its own remembered value.
- A successful save records `quick_edit_product` audit data, retains the
  existing `change_price` audit when price changes, and returns to the empty
  scanner for the next item.
- Eligibility is checked again inside the write transaction, so a direct POST
  or concurrent image update cannot edit a product that already has an image.

## Collapsible sidebar

- Every staff sidebar heading is an accessible expand/collapse button. One
  `^` caret rotates 180 degrees for collapsed state; no letter `V/v` is used.
- “ขายหน้าร้าน” and “ออเดอร์ออนไลน์” start expanded. Stock count, product and
  inventory, analytics, and administration start collapsed.
- Section choices are retained locally. The existing compact desktop sidebar
  continues showing all menu icons, and mobile keeps the section controls.

## Embedded public policy

- `/order/policy?embedded=1` remains available on the approved customer host.
- Only that embedded policy response permits same-origin framing through
  `X-Frame-Options: SAMEORIGIN` and CSP `frame-ancestors 'self'`.
- The standalone policy and every other public page retain frame denial.

## Compatibility

- No database schema or migration change.
- Existing product UUID/barcode identity, normal product editing, stock,
  online availability, images, sales, and customer policy content are
  preserved.

## Verification

- Focused quick-edit/sidebar/public-host suite: 23 passed.
- Wider release-critical regression suite: 58 passed.
- Browser verification passed the unknown barcode, already-imaged product,
  image preview, save-and-return, per-staff remembered price, repeat-scan
  rejection, collapsible sidebar, and desktop/tablet/mobile responsive flows
  with no console warnings/errors.
- Mobile-dialog follow-up verification passed 10 focused/context tests.
  Browser QA at 393×873 and 360×640 showed no document or form overflow, kept
  the save button inside the viewport before and after preview, returned to the
  scanner from the close action, preserved the desktop layout, and logged no
  console warnings/errors.
- Canonical Production port 8000 was restarted after this follow-up. Health is
  `ok`, `/login` references `v306.css?v=3`, and the served CSS/quick-editor JS
  SHA-256 values match the verified source files.
- Full suite: 166 tests completed—165 passed and one existing
  filesystem-capability skip.
- Canonical Production port 8000 was restarted on 2026-07-30. The live
  Cloudflare response for `/order/policy?embedded=1` returns
  `X-Frame-Options: SAMEORIGIN` with CSP `frame-ancestors 'self'`; standalone
  `/order/policy` retains `DENY` and `frame-ancestors 'none'`.
