# Release 3.2.1 — VPS LINE Bot manual commands

**Status:** Deployed to the separate Live VPS LINE Bot service on 2026-08-08.

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
- The seven release-specific `/bot` and `/check` tests passed in the Production
  VPS venv before the switch. The venv deliberately has no QR generator test
  utility; runtime decoding remains restricted to linear barcode formats and
  continues to reject QR/2D formats.
- Source, protected configuration, and an online Bot-SQLite backup were taken
  before the atomic release-symlink switch. Local and public health returned
  `ok`, port 8010 remained localhost-only, the service stayed active with no
  warning journal entries, and both live and backup Bot databases passed
  `PRAGMA quick_check` after deployment.
