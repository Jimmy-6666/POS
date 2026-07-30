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
- The active Release 3.0.7 Production instance uses port `8000`, `runtime/`,
  and is configured for fixed server address `192.168.0.200` on the trusted
  `192.168.0.0/24` private LAN. Windows currently reports
  `192.168.1.200/24` on a Public profile because the server is temporarily on
  another LAN; by owner instruction the accepted POS network config remains
  unchanged and site-LAN verification is deferred.
- UAT launcher uses port `8001` and `uat_runtime/`.
- The port `8002` profile is not the canonical customer Production instance.
- Customer ordering is integrated at `/order`; staff fulfilment is integrated
  at `/online-orders`. Products default to online-enabled, except the current
  Production catalog snapshot: 479 products are active, 362 have zero price,
  463 have no image, all have zero stock, and 10 are online-enabled.

An auxiliary Makro catalog preparation pipeline lives in
`work/makro-pos-import/`. It uses Node and Codex spreadsheet tooling only for
development/UAT data preparation; Node is not a POS runtime dependency. Its
retrieval step accepts explicit raw JSON/CSV input and output paths, preserves
an exact-Makro-ID result report, and its data must not be treated as
production-ready without barcode and price approval.

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

On 2026-07-30, `python -m unittest discover -s tests -q` completed 173 tests:
172 passed with one filesystem-capability skip, including the Release 3.0.7
camera barcode scan, CSP-safe bounded image preview, missing-product quick
creation, already-imaged rejection, per-staff price/category/unit memory,
shared stock-count scanner, price-control missing-product creation with
per-staff category/unit memory and save/refocus, mobile price numpad,
Release 3.0.6 quick editor,
collapsible sidebar,
embedded-policy header fix, Release 3.0.5 registration consent, Release 3.0.4
combined terms/PDPA notice, product-image disclaimer, POS-configured customer
contact links, Release 3.0.3 default-product-image, net-best-seller,
global-search, Release 3.0.2 product browse/camera preview, private-LAN staff login/session
access, outside-LAN rejection, customer contact UI, delivery payment-method confirmation,
receipt-only print-agent behavior, stock-sheet print-preview isolation, and the
online ordering lifecycle. Release 3 transaction regressions cover concurrent
checkout, void, expiry, and idempotent order submission. Sprint 3 security
regressions cover pre-login CSRF, configured private-LAN staff access, remote Admin
host isolation and 2FA, signed-update reauthentication, and structured support
redaction. Release 3 recovery and runtime regressions cover the full
database-and-product-image bundle and in-process schedule validation. Flask
3.1.3 is installed and the dependency set passes `pip check`. Local Release
3.0.7 runtime/health/assets pass. The expected `SaengngamPOS-Production`
startup task is currently absent and requires an Administrator PowerShell
session to restore.
LINE LIFF verifies customer identity before the POS
creates a customer session and delivery profile. Staff can add or reduce order items before picking;
price/total changes retain the customer's confirmed price snapshot and show a
customer-confirmation warning. Product price, receiving, and stock-adjustment pages
also support manager/admin name, SKU, and barcode lookup; online customer
administration supports phone/name/public-ID search, admin-PIN-confirmed
anonymizing deletion, and customer re-registration after deletion. Suspended
LINE customers receive a stable blocked page instead of a LIFF login loop.

The canonical Production database contains 479 active products. The read-only
post-deploy snapshot is 362 zero-price, 463 no-image, all zero-stock, and 10
online-enabled products.
SQLite quick check and foreign-key verification pass.

## Canonical references

- Product contract: `REQUIREMENTS_V1.0.md`
- Architecture/navigation: `PROJECT_MAP.md`, `MODULE_DEPENDENCIES.md`
- Feature and verification state: `FEATURE_STATUS.md`
- Data model: `DATABASE_OVERVIEW.md`, then `pos_app/schema.sql`
- Historical detail: `PROJECT_PLAN.md`, `IMPLEMENTATION_STATUS.md`,
  `DATABASE_SCHEMA.md`, release notes, and `CHANGELOG.md`
- Installation/operation: `README.md`, `FIRST_INSTALLATION.md`

## Default next priority

No new product scope should be invented. The next catalog task remains
customer selling-price entry and photography, followed by an explicit decision
to enable selected products online.

Version 3.0.7 is the current implementation baseline. Manager/Admin quick edit
accepts manual/USB/Bluetooth barcode input plus a shared local
BarcodeDetector/ZXing camera action. Normal HTTP LAN access automatically
falls back to native barcode photo capture. On phones, a found product opens
directly to a whole-baht numpad while keeping its name and barcode visible.
Already-imaged products are named and rejected; an unknown barcode opens the
same editor to create an audited, active UUID product. Price, category, and
unit memory are isolated per staff. Quick edit owns its file/camera preview
lifecycle, uses Admin-CSP-compatible data URLs, and bounds the mobile grid;
sidebar and embedded-policy behavior remain.
Blind stock count keeps the barcode input active after an unknown
scan and opens quantity input only after a successful lookup. Canonical
port-8000 Production was restarted onto Release 3.0.7
with live asset, database-integrity, and catalog-preservation verification.
It retains Version 3.0.5 first-time LINE profile consent, Version 3.0.4
policy/disclaimer content, Version 3.0.3 default-image and net-best-seller
behavior, Version 3.0.2 image-preview behavior, Version 3.0.1 private-LAN
access, and Version 3.0.0 hardening.
Requests outside `192.168.0.0/24` remain blocked.
The Windows server address is static
`192.168.0.200/24`; firewall exposure stays Private/LocalSubnet only. It also
retains Version 2.4's
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
Bangkok-time schedule; it runs only while the POS is open. A separate verified
full recovery bundle includes current product images for handoff and drills.
