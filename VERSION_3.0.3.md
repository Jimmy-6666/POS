# Saengngam Minimart POS — Version 3.0.3

Released 2026-07-29.

## Default product image

- Products without a saved image use the approved local
  `pos_app/static/img/noimage.png` asset.
- The default appears consistently in the POS catalog, customer online
  catalog, online cart and repeat-purchase cards, staff order details, and
  existing product edit forms.
- The supplied PNG is preserved byte-for-byte with SHA-256
  `89f12bb18e95f7c08ce8b756ebf9dd2fb1d659165bb3b4a34ede0383942ede0c`.

## Best-selling online catalog

- `/order` replaces the “สินค้าทั้งหมด” pill with “สินค้าขายดี” and selects
  it by default.
- Product order uses all-time net sold quantity from both POS sales and
  completed online-order sales. Voided quantities are subtracted.
- Products with no sales remain available after sold products. Ties use the
  existing online sort order and Thai product name.
- Category pages retain their category scope and use the same best-selling
  order.
- Search remains global across every category, including when the incoming
  URL contains an old category parameter.

## Compatibility

- No database schema or migration change.
- Product-image uploads, existing product images, stock, sale, Void, online
  order, private-LAN, privacy-policy, backup, and security behavior are
  preserved.
- The server remains at `192.168.0.200`; other POS terminals and iPad/tablet
  browsers on `192.168.0.0/24` continue to use the Release 3.0.1 LAN policy.

## Verification

- Focused online, image, Void, and release-identity suite: 30 passed.
- Full Python suite: 157 tests completed—156 passed and one existing
  filesystem-capability skip.
- Browser reached the local `/order` page and reported the expected Thai page
  title. Deeper browser interaction was not performed because the browser
  security policy prohibited the connected LINE access; no alternate browser
  or policy workaround was used.
