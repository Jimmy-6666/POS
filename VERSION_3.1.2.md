# Saengngam Minimart POS — Version 3.1.2

Status: released and deployed 2026-07-31

Migrations: additive Migrations 29–30

Production baseline is Version 3.1.2.

## Per-product daily manual price

- `products.requires_manual_price` marks an active catalog product whose
  selling price must be entered by the Cashier for every POS line.
- Exact barcode scanning, global search, and configured product buttons all
  return the flag through the existing POS APIs. Selecting the product opens
  the existing blocking whole-baht Numpad with the real product name and
  barcode.
- The entered price applies only to that one cart line. It does not update the
  product master selling price.
- Each confirmed entry keeps the existing one-use, staff-bound
  `MP-########` audit reference. Quote and checkout revalidate the reference,
  staff, product UUID, barcode, and price server-side, so a client cannot
  bypass the prompt with the catalog price.
- `enter_pos_manual_price` and `sell_with_manual_price` audits include the
  real product UUID/name and reason `product_manual_price`.
- Receipts and sale history keep the real product name for this reason while
  retaining the manual-price reference. Generic `MANUALPRICE`, unknown
  barcode, and legacy zero-price line naming remains unchanged.
- The Cashier may still cancel the blocking dialog through the Version 3.1.1
  no-write cancel path.

## New-product online default

- The standard new-product page no longer displays online availability, sort,
  or maximum-quantity controls. `เปิดใช้งาน` remains checked by default.
- The server ignores forged online fields on create and writes the new product
  as offline. Manager/Admin may enable online availability later from the edit
  page.
- Quick Edit, missing-product Price Control, POS placeholders, and default
  XLSX creation also create products offline unless the import explicitly
  contains an approved online value.
- Existing products and their current online availability are not rewritten.

## Manager settings and billed-balance settlement

- The Manager role now receives the existing `settings.manage` permission and
  can open and save `/settings`, maintain the lists and billing customers
  shown on that page, and use `/billing`.
- Managers can receive a partial billed payment or clear selected outstanding
  balances in bulk. Existing `receive_billing_payment` and
  `receive_bulk_billing_payment` audits retain the acting Manager staff ID.
- Cashiers remain denied by the server. Staff management, Audit Log, backups,
  maintenance, account security, and product XLSX remain Admin-only.
- The sidebar exposes Settings and billed-balance management to Managers
  without exposing the other Admin-only links.

## Data and compatibility

- Migration 29 adds only
  `requires_manual_price INTEGER NOT NULL DEFAULT 0 CHECK (... IN (0,1))`.
- Every existing product receives `0`; no price, stock, image, UUID, online
  flag, sale, or audit row is rewritten.
- Fresh databases default both the manual-price flag and online availability
  to `0`.
- Migration 30 idempotently grants the existing `settings.manage` permission
  to the Manager role. It does not rewrite a sale, billed balance, payment,
  product, stock movement, or existing audit.

## Verification

- Focused Release 3.1.2, billing, permission, migration, and XLSX regression:
  33/33 passed.
- Full suite: 194 tests passed with one existing filesystem-capability skip.
- `pos.js` passed Node syntax validation and `git diff --check` passed.
- Headless Edge on UAT verified R3.1.2/asset-v37, active/offline create UI,
  edit-only online controls, flagged positive-price scan, real product name,
  whole-baht prompt, `MP-########` reference, cart price, removal, and scanner
  focus recovery. The product flag was restored and no sale or stock movement
  was created. The only browser resource warning was the pre-existing missing
  `/favicon.ico`.
- UAT SQLite integrity passed with zero foreign-key violations; Migrations 29
  and 30 are recorded as successful under 3.1.2.

## Production deployment — 2026-07-31

- The canonical port-8000 Production instance now runs Version 3.1.2 and
  returns ready health. Port-8001 UAT remained ready throughout deployment.
- Migrations 29 and 30 applied successfully. SQLite integrity is `ok`, foreign
  key violations are zero, and the manual-price product column is present.
- The 742-product catalog was preserved with all 742 products active. Sales,
  sale items, and billed sales remain zero, matching the pre-deploy snapshot.
- The missing Windows startup tasks were repaired to the accepted Version
  3.0.9 security model: `SaengngamPOS-Production` runs under `SYSTEM` at boot
  and `SaengngamPOS-Desktop` launches for the passwordless standard `POS` user
  at logon with `-Desktop -AttachOnly`. The Public Desktop recovery shortcut,
  static `192.168.0.200/24` LAN configuration, Private/LocalSubnet firewall,
  shared desktop Python, and full Production verification all passed.
- A verified database/image backup, full recovery bundle, and Version 3.1.0
  source rollback were created before the deployment.
