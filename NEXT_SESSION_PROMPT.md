# Thai Minishop POS — Version 2.4.2 next-session hands-on prompt

Continue from the published Version 2.4.2 baseline in this workspace. Work
hands-on only after the owner gives a specific approved fix or sprint. Do not
start a new sprint or broaden product scope on your own.

## Required opening checks

1. Read `AGENTS.md`, then read only `AI_CONTEXT.md`, `PROJECT_MAP.md`,
   `FEATURE_STATUS.md`, `DECISIONS.md`, `CODING_RULES.md`, and
   `DESIGN_RULES.md`.
2. Confirm the branch/tag and run `git status --short`. Preserve all existing
   data and uncommitted work; never reset, clean, or overwrite it.
3. Read `VERSION_2.4.2.md` and the newest `CHANGELOG.md` section before changing
   release behavior.
4. If the task touches customer ordering, verify UAT at
   `http://127.0.0.1:8001/health` and check LIFF configuration through
   `/api/auth/config`.
5. If the task touches backup, inspect the Backup page status and
   `uat_runtime/support/remote-backup-status.json`. Never copy secrets,
   private keys, passwords, databases, or runtime files into Git or support
   output.
6. Run focused tests for every change. Run the full suite for shared logic,
   schema, auth, sales, inventory, reconciliation, backup, or release work.

## Version 2.4.2 facts

- UAT runs on port 8001; the desktop release defaults to port 8002.
- LINE LIFF customer authentication is active at
  `https://online.raisanngam.com/order`.
- POS and online negative-stock permissions are separate.
- Customer deletion is audited anonymization and permits re-registration with
  the same former LINE identity/phone.
- Product identity is exclusively immutable `product_uuid`. SKU, barcode, and
  name are mutable business fields and must never be used to match products.
- Admin TOTP is the only optional second factor, applies only after a valid
  admin password, and must never create the authenticated session early.
- XLSX product import/export is admin-only. Import previews do not mutate the
  database; confirmed updates match by `product_uuid` only; existing stock is
  read-only; import records only safe audit metadata.
- Product camera capture uses the existing product-image validation and saves
  only when the product form is submitted.
- Cashier POS void initiation requires a server-verified active Manager/Admin
  PIN; Cashier online-order cancellation needs no PIN but is allowed only from
  `submitted` through `ready`, never after delivery begins.
- Database ZIPs exclude product images. Product images sync by delta to the
  VPS; replaced/deleted remote snapshots move to `file-backups/`.
- The UAT VPS image baseline contains 385 product images. Production catalogue
  still needs owner-approved real barcodes and prices; UAT mock values are not
  production approval.
- Daily backup time is set on the Backup page and runs only while the POS is
  open during that minute.
- Version 2.4.2 verification baseline: 122 tests passed on 2026-07-28. Rerun
  rather than carrying this count forward.
  rather than carrying this count forward.

## Safe task process

Classify the task through `PROJECT_MAP.md`, then open only the smallest route,
service, template/JS/CSS, schema, and test scope needed. State affected
modules, migration impact, and risk before changing code. Use additive,
data-preserving migrations; preserve audit history; enforce permissions on the
backend; and update only relevant documentation plus `CHANGELOG.md`.
