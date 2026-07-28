# แสนงาม มินิมาร์ท POS — Version 2.4.1

Released 2026-07-28.

## Product form hotfix

- `/products/new` now includes the required `ราคาขาย (บาท)` field directly in
  the form and stores its server-validated satang value; it no longer forces a
  newly created product's selling price to zero.
- The price-page shortcut was removed from the new-product form only. The
  dedicated `/products/prices` page remains available from the product menu
  for bulk price maintenance.
- Product-image controls now occupy their own full-width section above the
  barcode field, so the stock-minimum control cannot be stretched by image UI.
- `/products/<product_uuid>/edit` displays the product's current image above
  the barcode field. Choosing a file or using the rear-camera capture control
  previews the replacement only; cancellation or removing the new selection
  leaves the current stored image intact.
- File browsing and camera capture are touch-friendly secondary buttons and
  both submit through the existing image validation, resize/compression, and
  runtime storage path. No image is persisted before form submission.

## Runtime and upgrade

- No database migration or configuration change is required.
- Restart the POS after upgrading so the updated templates and browser assets
  are served. Desktop remains port `8002`; UAT remains port `8001`.

## Verification

- Focused product/version regression: 26 tests passed on 2026-07-28.
- Full suite: 122 passed on 2026-07-28.
- UAT: health `ok`, database `ready`; LIFF configuration confirmed through
  `/api/auth/config`.
