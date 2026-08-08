# Release 3.2.1 — VPS LINE Bot manual commands

**Status:** Verified deployment candidate for the separate VPS LINE Bot service.

## Scope

Release 3.2.1 changes only the LINE Bot workflow, its focused tests, and its
operator documentation. It does not modify `pos_app`, the Windows POS
Production/UAT installations, POS schema or migration, or POS business data.
The visible Windows POS identity remains 3.2.0.

## Commands

- `/check barcode` performs one signed, read-only POS lookup. A found product
  returns its name, barcode, and current selling price. A missing barcode is
  reported once and no flow or follow-up action is created.
- `/bot barcode|name|price` accepts a product name containing spaces because
  its three fields use pipe delimiters. Barcode and name are required; selling
  price must be positive whole baht.
- `/bot` performs POS lookup before opening a flow. It creates an unknown
  product or completes a Placeholder with zero cost, then uses the normal
  group-shared confirmation. Any allowed-group member may confirm, and the
  signed command records the actual confirmer.
- A named existing product is shown but never overwritten by `/bot`.
- Neither command sends images to POS or invokes Gemini. Normal results use
  the originating LINE Reply token and retain the existing durable fallback
  only when delayed delivery is required.

## Verification

- Focused LINE Bot, signed integration, Vision, Gemini-budget, and release
  regression: 60/60 passed.
- Full suite: 267 tests run, 266 passed and one existing filesystem-link
  capability test skipped; no failures.
- `git diff --check` passed and the release changes no `pos_app` source file.
