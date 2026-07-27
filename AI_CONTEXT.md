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
- Python dependencies: Flask and Waitress only.
- Release 2.1 desktop launcher uses port `8002` and `runtime/`.
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

On 2026-07-27, `python -m unittest discover -s tests -v` ran 69 tests and all
passed, including customer contact UI, delivery payment-method confirmation,
receipt-only print-agent behavior, stock-sheet print-preview isolation, and the
online ordering lifecycle. Staff can add or reduce order items before picking;
price/total changes retain the customer's confirmed price snapshot and show a
customer-confirmation warning. Product price, receiving, and stock-adjustment pages
also support manager/admin name, SKU, and barcode lookup; online customer
administration supports phone/name/public-ID search.

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

Sprint 1 production foundation and Sprint 2 backup/recovery foundation are
implemented: canonical runtime paths, startup validation, migration history,
deterministic dependency locking, verified SQLite online backups, incremental
allow-listed file sync with delayed quarantine, SFTP transport, recovery-drill
scripts, and Windows lifecycle tasks. The production and backup tasks use Task
Scheduler; the firewall rule remains limited to Private/LocalSubnet. Signed
updates, admin maintenance dashboard, and remote support remain deferred to
Sprint 3.
