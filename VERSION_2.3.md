# แสนงาม มินิมาร์ท POS — Version 2.3

Released 2026-07-28.

## Highlights

- Every product now has a globally unique, immutable `product_uuid`. Product
  communication between routes, browser payloads, inventory, sales, held
  carts, and online ordering uses this UUID. The numeric product key remains
  internal relational storage only; SKU and barcode are mutable business
  fields and never determine product identity.
- Admin accounts can protect login with RFC 6238 TOTP compatible with Google
  Authenticator, Microsoft Authenticator, Authy, and similar applications.
  Setup requires verification, secrets are encrypted at rest, recovery codes
  are one-time and hashed, and the authenticated session is not created until
  the second factor succeeds.
- Admin product management can export an XLSX template and import XLSX through
  a preview and explicit confirmation. Updates use `product_uuid` only; blank
  UUIDs create products. Existing stock cannot be overwritten, while a new
  product's opening stock creates an audited ledger movement.
- The XLSX importer blocks formulas, validates all rows, keeps blank update
  fields unchanged unless explicitly cleared, runs atomically, revalidates
  targets and uniqueness while locked, and records summary plus non-sensitive
  per-product audits.

## Runtime

- Desktop release: port `8002`, runtime root `runtime/`.
- UAT: port `8001`, runtime root `uat_runtime/`.
- Customer ordering: `https://online.raisanngam.com/order` using configured
  LINE LIFF identity.
- Python runtime remains Flask/Waitress/SQLite with no Node, Docker, CDN, or
  frontend build requirement.

## Upgrade

Install the pinned dependencies before starting a pre-2.3 installation:

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Startup applies additive migrations 23 (immutable product UUID) and 24
(admin-only two-factor state) without deleting existing data. Restart the POS
after upgrading so the server applies migrations and browser assets reload.

Before production promotion, run the complete test suite and review
`FEATURE_STATUS.md`. UAT catalog values with synthetic barcodes/mock prices are
not automatically approved as production master data.

## Verification

- Full test suite: 103 passed on 2026-07-28.
- UAT health reported `ok` with database `ready`.
- LIFF configuration was confirmed through `/api/auth/config`.
