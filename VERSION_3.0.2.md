# Saengngam Minimart POS — Version 3.0.2

Released 2026-07-29.

## Product-image preview hotfix

- Fixed the product add/edit form so selecting an image file or taking a photo
  immediately displays the unsaved preview.
- Product-image event listeners are initialized before the optional profit
  summary. Missing profit fields can no longer stop the image controls with a
  JavaScript error.
- Selecting a new image temporarily hides the current saved image. Removing the
  unsaved selection restores the current image on the edit form.
- Added an explicit `[hidden]` CSS rule for the current image and preview, and
  changed the `product-form.js` cache key to `v=3`.
- Camera and file uploads continue through the existing server-side validation
  and product-image runtime folder. Images are saved only when the product form
  is submitted.

## Compatibility

- No database schema or migration change.
- Existing product records, saved images, runtime configuration, private-LAN
  access, privacy policy, backups, and security controls are preserved.
- The server remains at `192.168.0.200`; other POS terminals and iPad/tablet
  browsers on `192.168.0.0/24` continue to use the Release 3.0.1 LAN policy.

## Verification

- Focused product-image and release-identity suite: 13 passed.
- Browser interaction passed browse preview, camera-input preview,
  remove/restore, hidden-state layout, and an iPad-size `820x1180` viewport;
  no console error was recorded.
- Full Python suite: 153 passed with one existing filesystem-capability skip.
