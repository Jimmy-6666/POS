# Version 3.1.8 — 80 mm POSPrinter receipt rendering

## Release status

Released to the local Production POS on 2026-08-03 and published as the POS
GitHub release on 2026-08-05.

## Scope

- Uses the installed POSPrinter POS-80 driver's native
  `80(72)mm x 297mm` printable form, preserving the physical 80 mm roll and
  preventing right-edge clipping.
- Draws the approved `receipt-logo.png` inside the single SYSTEM GDI receipt
  job. This replaces the unreliable printer-stored RAW logo command, which
  could work interactively but not for completed sales from the SYSTEM server.
- Retains the single pre-receipt cash-drawer pulse and all existing receipt
  fields, sale, inventory, and reconciliation behavior.

## Compatibility

- No database migration, data rewrite, POS API change, or LINE Bot integration
  change.
- The VPS-only LINE Bot code is intentionally outside this POS release.

## Verification

- Focused receipt regression: 3/3 passed.
- Generated Windows GDI C# renderer compiled without printing; the encoded
  command is 20,676 characters, within the Windows command-line limit.
- Isolated UAT full suite: 205 passed with one existing capability skip.
- Production health, SQLite quick check, and foreign-key check passed.
- A customer confirmed the real SYSTEM-path receipt shows the logo and fits
  the 80 mm roll.
