# AI Context

## Product

Thai-first, offline-first point-of-sale system for แสนงาม มินิมาร์ท. It runs on
Windows, serves trusted devices over a private LAN, supports touch workflows,
and prints 80 mm receipts through the browser.

## Current implementation

- Flask 3.1 application factory with Waitress deployment.
- SQLite with foreign keys, WAL, additive startup migrations, audit records,
  and transaction-protected sales/inventory operations.
- Server-rendered Jinja HTML plus local vanilla JavaScript and CSS.
- No Docker, Node, React, cloud service, CDN, or frontend build step.
- Python runtime dependencies include Flask, Waitress, `pyotp`, `cryptography`,
  `qrcode`, and `openpyxl`; the last is used by the admin-only product XLSX
  import/export feature.
- Release 2.4.2 desktop launcher uses port `8002` and `runtime/`.
- UAT launcher uses port `8001` and `uat_runtime/`.
- Legacy launcher uses port `8000` and the repository root runtime.
- Customer ordering is integrated at `/order`; staff fulfilment is integrated
  at `/online-orders`. Products default to online-enabled; UAT permits zero-price
  catalogue items while inactive products remain hidden.

An auxiliary Makro catalog preparation pipeline lives in
`work/makro-pos-import/`. It uses Node and Codex spreadsheet tooling only for
development/UAT data preparation; Node is not a POS runtime dependency. The
pipeline currently depends on an external, hard-coded source path and its data
must not be treated as production-ready without barcode and price approval.

## Non-negotiable behavior

- Preserve `REQUIREMENTS_V1.0.md` and all later accepted additions.
- Thai UI first; English identifiers/comments are acceptable.
- Prices and monetary totals are integer satang in the database.
- Sales totals, authorization, prices, cost, stock, and permissions are
  validated server-side.
- Important writes must be atomic and auditable.
- Existing data must survive schema evolution; never delete tables/columns as
  an incidental migration.
- Keep assets local and the project movable to another Windows PC.

## Current health

On 2026-07-28, `python -m unittest discover -s tests -q` completed 129 tests
successfully, including customer contact UI, delivery payment-method confirmation,
receipt-only print-agent behavior, stock-sheet print-preview isolation, and the
online ordering lifecycle. Release 3 transaction regressions cover concurrent
checkout, void, expiry, and idempotent order submission. LINE LIFF verifies customer identity before the POS
creates a customer session and delivery profile. Staff can add or reduce order items before picking;
price/total changes retain the customer's confirmed price snapshot and show a
customer-confirmation warning. Product price, receiving, and stock-adjustment pages
also support manager/admin name, SKU, and barcode lookup; online customer
administration supports phone/name/public-ID search, admin-PIN-confirmed
anonymizing deletion, and customer re-registration after deletion. Suspended
LINE customers receive a stable blocked page instead of a LIFF login loop.

The UAT database passes SQLite integrity and foreign-key checks. It contains
386 products; all active products now have mock selling prices calculated as
unit cost plus at least 20%, rounded up to the next 5 baht. Some still use
synthetic barcodes, so this remains test/catalog-preparation data only.

## Canonical references

- Product contract: `REQUIREMENTS_V1.0.md`
- Architecture/navigation: `PROJECT_MAP.md`, `MODULE_DEPENDENCIES.md`
- Feature and verification state: `FEATURE_STATUS.md`
- Data model: `DATABASE_OVERVIEW.md`, then `pos_app/schema.sql`
- Historical detail: `PROJECT_PLAN.md`, `IMPLEMENTATION_STATUS.md`,
  `DATABASE_SCHEMA.md`, release notes, and `CHANGELOG.md`
- Installation/operation: `README.md`, `FIRST_INSTALLATION.md`

## Default next priority

No new product scope should be invented. Follow the user's next feature
priority. If catalog deployment is selected, first complete owner approval of
selling prices and real barcodes and make the import input path portable.

Version 2.4.2 is the current published baseline. It retains Version 2.4's
product camera capture, Manager-authorized POS item voids, reconciliation void
totals, current/latest cost pricing, customer/staff online-order workflow
improvements, and submitted-order sound/badge alerts. It also restores direct
selling-price entry at product creation and fixes the product image controls
and existing-image preview. It limits order-alert polling/audio to POS and
the online-order list, adds the list badge, and refreshes it for new orders.
Sprint 1 production foundation
and Sprint 2 backup/recovery foundation are
implemented: canonical runtime paths, startup validation, migration history,
deterministic dependency locking, verified database-only SQLite online backups,
incremental product-image sync with VPS archival before replace/delete, SFTP transport, recovery-drill
scripts, and Windows lifecycle tasks. The production task uses Task Scheduler;
the daily backup schedule runs inside the active POS process, and the firewall
rule remains limited to Private/LocalSubnet. Signed
Sprint 3 is implemented: an admin-only maintenance page reports runtime and
verified backup status, creates redacted local support bundles, and can hand a
staged update to a Windows runner only after manifest hash plus pinned
Authenticode signer verification. It has no automatic download, private key,
or remote-control channel; see `docs/SIGNED_UPDATE_AND_SUPPORT.md`.
The Backup page records the latest VPS result and provides an in-process daily
Bangkok-time schedule; it runs only while the POS is open.
