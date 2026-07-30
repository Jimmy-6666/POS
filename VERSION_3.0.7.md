# Saengngam Minimart POS — Version 3.0.7

Prepared 2026-07-30.

## Camera barcode scan

- `/products/quick-edit` now provides a touch-friendly “สแกนด้วยกล้อง”
  action in addition to the existing manual, USB, and Bluetooth scan input.
- The quick editor and blind stock count share one local camera-scanner
  helper. It prefers the browser `BarcodeDetector` and falls back to the
  bundled ZXing reader without a CDN or network dependency.
- On an HTTPS/localhost origin the action supports live rear-camera scanning.
  On the shop LAN's normal HTTP origin it automatically opens native camera
  capture and reads the photographed barcode, preserving a working mobile
  path despite browser secure-context restrictions.
- Camera streams and scanner controls stop after a result, when the user
  closes live scanning, or when the page is left. Duplicate results cannot
  submit the lookup more than once.

## Mobile price numpad

- After an eligible product scan on a phone, the full-viewport editor opens
  directly to a custom whole-baht selling-price numpad.
- The scanned product name and barcode stay visible in the fixed editor
  header. The first number replaces the remembered/current price; later
  numbers append normally, with clear and backspace controls.
- Confirming the price reveals the existing photo, Thai name, category, unit,
  and save form. The price keypad can be reopened from the price field.
- The server retains the existing integer-baht validation and per-staff
  remembered-price behavior; the numpad is only a faster mobile input layer.

## Stock-count scan recovery

- An unknown barcode now shows “ไม่พบสินค้า” without opening quantity entry.
  The rejected code is cleared and focus immediately returns to the barcode
  input so staff can scan the next item.
- A successful lookup retains the accepted flow and focuses quantity entry.
  A lookup sequence guard prevents a late response from overriding a newer
  scan.

## Price-control scan loop

- On `/products/prices`, an exact-barcode result keeps selling-price entry
  selected. Enter saves once, returns to the empty lookup page, and restores
  barcode-input focus for the next scan.
- Name, SKU, and non-exact searches retain their query after a save. Failed
  saves also retain the scanned result so staff can correct the price.

## Price-control missing-product creation

- A search with no matching product opens a responsive add-product modal with
  whole-baht price, three-line Thai name, category, and unit. It deliberately
  has no product-image input.
- Save creates an active UUID product with zero cost/stock and no image inside
  one audited transaction. Duplicate barcodes are rechecked under the write
  lock, and success returns to the empty focused price-control scanner.
- Each staff session remembers only the last successfully saved active
  category and unit for the next missing product. Price and name reset, and
  inactive references are ignored.
- The modal reuses the mobile price numpad and visual field system only. Its
  server action and JavaScript state are independent of quick product editing.

## Quick-edit image preview

- File selection and camera capture now use a dedicated quick-edit preview
  lifecycle instead of the shared full product-form script.
- Preview uses a CSP-compatible `data:` URL instead of a blocked `blob:` URL.
  Long filenames cannot expand the mobile grid; image and action columns stay
  inside the one-screen editor.
- Preview visibility, current-image replacement, removal, and async stale-read
  protection are explicit. Cache keys are JS `v=6` and CSS `v=3`.

## Missing-product creation and remembered fields

- A scan matching an already-imaged product now says “สินค้านี้มีรูปแล้ว” and
  returns to the next scan after confirmation. Direct and concurrent POSTs
  cannot bypass the server-side image check.
- An unknown barcode opens the same compact editor in create mode. Staff enter
  the Thai product name, whole-baht price, category, unit, and optional image;
  save creates an audited UUID product with zero cost/stock and `is_active=1`.
- The last successfully saved price, category, and unit are remembered per
  signed-in staff account. Inactive remembered references are ignored.
- The quick-edit JavaScript cache key is `v=5`.

## Compatibility

- No database schema or migration change.
- Existing no-image editing, image preview/upload, transactional save, audit,
  permissions, and desktop/tablet behavior are preserved.
- Barcode scanning remains available through manual entry and USB/Bluetooth
  hardware when a camera is unavailable.

## Verification

- Focused price-control regression: 7 passed. Headless Edge verified repeated
  Enter locking plus the no-image create modal at 360×640 and 1024×768.
- Post-deploy read-only Headless Edge QA found barcode `8854334004607`,
  focused its price input, loaded JS `v=2`, and reported no resource error.
- A missing-barcode Production QA opened the mobile modal/numpad without
  image controls or overflow, then closed without submitting or creating data.
- Focused quick-edit, product-image, and Release 3.0.7 regressions: 26 passed.
- Browser QA at 360×640 verified first-digit replacement, multi-digit entry,
  visible product identity, keypad reopen, and the complete post-confirmation
  editor with no document/form overflow or console error.
- Isolated browser QA verified that unknown scans keep the empty barcode input
  active while successful scans focus quantity.
- Playwright Edge at 360×640 under the Admin-equivalent CSP verified browse
  and camera preview, remove/restore, a real 576×1280 JPEG with a long filename,
  bounded columns, no form/document overflow, and no console error.
- Physical camera permission and barcode focus remain customer-device
  operational checks because the QA browser has no shop camera hardware.
- Full suite: 173 tests completed — 172 passed with one existing
  filesystem-capability skip. `pip check` passed.
- Local port-8000 runtime, version, health, firewall, backup schedule, served
  assets, and database integrity pass. Read-only QA made no product save and
  preserved the pre-restart 479-product catalog. Site-LAN verification is deferred
  because the server is temporarily on another LAN; by owner instruction the
  accepted `192.168.0.200/24` contract/config remains unchanged. The expected
  startup Scheduled Task is also absent and requires an Administrator
  PowerShell session to restore.
