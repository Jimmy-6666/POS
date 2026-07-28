# แสนงาม มินิมาร์ท POS — Version 2.4

Released 2026-07-28.

## Highlights

- Product creation supports mobile camera capture alongside desktop file
  browsing. Captured images use the existing validation, compression, and
  storage path only when the product form is submitted.
- Cashier-initiated POS item voids require server-verified active Manager or
  Admin PIN authorization. The completed audit links the cashier, authorizer,
  sale, item, product, quantity, unit price, amount, and any entered reason.
- Reconciliation shows valid recorded item-void totals. Migration 25 adds the
  additive historical close snapshot `reconciliations.void_total_satang`.
- Product pricing shows both current weighted-average cost and latest valid
  receiving cost without per-row lookup queries.
- Customer order details use consistent three-line item rows, Thai five-stage
  delivery progress, cancellation/refresh handling, and customer stock-state
  controls. Staff order/reconciliation screens use Thai labels and preserve
  operational ordering.
- New submitted online orders alert from the POS shortcut with a circular
  count badge, pulse, local looping sound, autoplay-safe retry, and mute
  preference. Cashiers may cancel an online order through `ready`, but never
  after delivery begins; cancellation retains reservation release, history,
  and audit records.

## Runtime and upgrade

- Desktop release defaults to port `8002` and `runtime/`; UAT uses port `8001`
  and `uat_runtime/`.
- Customer ordering remains at `https://online.raisanngam.com/order` with LINE
  LIFF identity verification.
- Startup applies additive migration 25 (`reconciliations.void_total_satang`)
  where required. It does not delete or rewrite historic sales, stock, or
  audit records.
- Restart the POS after upgrading so runtime permission seeds, migrations, and
  browser assets are applied. No new configuration is required.

## Verification

- Full test suite: 121 passed on 2026-07-28.
- UAT health: `ok`, database: `ready`.
- LIFF configuration confirmed through `/api/auth/config`.

## Production note

The UAT catalogue still includes mock prices and some synthetic barcodes.
Owner-approved production prices and real barcodes remain required before a
production catalogue rollout.
