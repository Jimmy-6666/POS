# Saengngam Minimart POS — Version 3.1.1

Status: released 2026-07-31

Migration: none

Production includes Version 3.1.1 through the cumulative Version 3.1.2
deployment approved on 2026-07-31.

## Scope

Version 3.1.1 is a focused cashier usability and POS-button refinement:

- After Cashier changes cart quantity with `+`, `−`, direct quantity entry, or
  removes a line, focus returns to the barcode/search field without scrolling
  the page. The next barcode can therefore be scanned immediately.
- The blocking manual-price dialog now has an explicit `ยกเลิก` action.
  Cancellation closes the prompt, discards the unresolved line, clears the
  lookup, returns the selector to the main menu, and focuses the scanner field.
  It does not create a placeholder product, cart line, manual-price reference,
  or audit record.
- Main manual-menu position 9 (bottom-right of the first 3×3 page) is reserved
  for a fixed `ตั้งราคาขาย Manual` button. It opens the same positive
  whole-baht, audit-backed workflow as scanning `MANUALPRICE`.
- Manager/Admin cannot create or move a top-level menu into position 9.
  Product position 9 inside a configured menu remains available, preserving
  the full 3×3 product capacity.
- The `นำออก` control in POS-button settings now has a complete destructive
  button style instead of relying on an unstyled browser button.

## Preserved behavior

- The barcode scanner remains blocked while the manual-price dialog is open.
  The Cashier must either confirm a valid price or explicitly cancel before
  scanning another item.
- A confirmed manual-price line still receives a one-use audit-backed
  `MP-########` reference, without changing the catalog selling price.
- Global search, configured text-only menus, pagination, checkout, stock,
  receipt, and online-order behavior are unchanged.
- No database schema or migration is added.

## Verification gate

Before release:

1. Run focused Release 3.1.0, 3.1.1, manual-price, POS, and settings tests.
2. Run the full unit-test suite because cashier sale initiation is
   release-critical.
3. Verify in headless UAT that all cart controls return focus to
   `#productLookup`, cancellation writes nothing, slot 9 opens the manual-price
   dialog, and the settings remove button is visibly styled.
4. Verify UAT health, version/static assets, then deploy Production only after
   explicit approval.

## Verification result — 2026-07-31

- Focused regression: 24/24 passed.
- Full suite: 188 tests completed; 187 passed and one existing
  capability-dependent test skipped.
- Headless Edge UAT at 1920×1080 confirmed R3.1.1 and POS asset v36, fixed
  Manual Price position 9, scanner focus after `+`, `−`, direct quantity edit,
  and removal, plus both unknown-barcode and fixed-Manual cancel paths.
- Neither cancel path called the manual-price POST endpoint or changed the
  cart. The unique unknown test barcode created zero products and zero audit
  rows.
- The settings `นำออก` control computed to a red background, white text,
  10px radius, and 42px minimum height. No page JavaScript errors occurred.
- UAT health/database, SQLite integrity, and foreign keys passed.
- The approved cumulative Version 3.1.2 Production deployment includes all
  Version 3.1.1 behavior. Production health, migrations, protected tasks,
  private-LAN configuration, firewall, database integrity, and data
  preservation passed after deployment.
