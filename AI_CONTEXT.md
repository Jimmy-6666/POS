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
- The active Release 3.1.3 Production instance uses port `8000` and `runtime/`.
  `SaengngamPOS-Production` starts the server under `SYSTEM` at Windows startup;
  `SaengngamPOS-Desktop` opens an attach-only launcher for the local standard
  `POS` account at logon. The account has no password, cannot administer the
  machine, and has a Public Desktop recovery shortcut. The launcher uses the
  read-only shared standard-library runtime under `desktop-python/`; it does
  not depend on or grant access to an Admin user's private Python installation.
  Mutable launcher state is shared through
  `runtime/pos-desktop/display_state.json`, whose parent ACL remains writable
  when the server recreates the file after a reboot.
- Release 3.1.3 retains the browser print-agent and installed Windows printer
  driver while making it observable from the standard `POS` account. Its
  bounded `runtime/pos-desktop/print-diagnostics.log` correlates completed
  transactions, queue/agent/render/browser acknowledgement stages by opaque
  job ID and is opened through a Launcher button. It never records a token,
  PIN, session, or payment evidence, and logging cannot affect a sale.
- The accepted network contract remains fixed server address `192.168.0.200`
  on trusted private LAN `192.168.0.0/24`. Release 3.1.0 elevated Production
  verification passed the static network and Private/LocalSubnet firewall
  checks.
- UAT launcher uses port `8001` and `uat_runtime/`.
- The port `8002` profile is not the canonical customer Production instance.
- Customer ordering is integrated at `/order`; staff fulfilment is integrated
  at `/online-orders`. Products default to online-enabled, except the current
  Production catalog snapshot: 742 products are active, 51 have zero price,
  726 have no image, all 742 have zero stock, and 199 are online-enabled.

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

On 2026-07-30, `python -m unittest discover -s tests -q` completed 179 tests:
178 passed with one filesystem-capability skip, including Release 3.0.8
blocking manual prices, audit-backed receipt references, Audit filtering/CSV,
version-26 migration startup, and the Release 3.0.7
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
3.1.0 localhost runtime, migration 28, integrity, and assets pass. The
background server task, attach-only POS desktop task, shared local print-agent
token, shared Desktop Python runtime, kiosk ACLs, and recovery shortcut are
installed. The shared runtime passed `ctypes`/`tkinter`/`urllib` smoke
validation, direct `pos_desktop` import without Flask, and full Tk launcher UI
initialization. A live `SaengngamPOS-Desktop` run under the `POS` security
context updated the shared display state after a server restart, and the
token-protected print-agent returned HTTP 200. Eleven focused
launcher/runtime regressions pass. Release 3.1.0 elevated verification
confirmed the canonical `192.168.0.200/24` Private LAN and firewall contract.
Release 3.0.9 verification on 2026-07-31 passed 13/13 focused tests and the
full 180-test suite with 179 passed and one existing filesystem-capability
skip.
LINE LIFF verifies customer identity before the POS
creates a customer session and delivery profile. Staff can add or reduce order items before picking;
price/total changes retain the customer's confirmed price snapshot and show a
customer-confirmation warning. Product price, receiving, and stock-adjustment pages
also support manager/admin name, SKU, and barcode lookup; online customer
administration supports phone/name/public-ID search, admin-PIN-confirmed
anonymizing deletion, and customer re-registration after deletion. Suspended
LINE customers receive a stable blocked page instead of a LIFF login loop.

The canonical Production database contains 742 active products. The read-only
post-deploy snapshot is 51 zero-price, 726 no-image, all zero-stock, and 199
online-enabled products; sales and sale items remain 0.
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

Version 3.1.0 introduced
POS cashier-first: every staff login enters `/pos`, fresh login collapses the
sidebar, and `ขายหน้าร้าน` is first. Manual selection is an independently
configured text-only 3×3 menu/product grid with nine-position pagination and
global search; it does not load product images. Manager/Admin configuration is
audited and Migration 28 adds only `pos_button_groups` and
`pos_button_items`. Closing money fields share an on-screen Numpad and do not
require a new PIN. Final focused regression passed 20/20; the full suite
completed 186 tests with 185 passed and one existing capability skip. Headless
1920×1080 verification confirmed 3×3 paging, no product-image requests,
viewport fit, and Numpad focus behavior. Production Migration 28, data
preservation, runtime health, protected tasks, firewall/static LAN, manager
login, default POS landing, asset versions, and empty configured-menu state
all passed. The accepted scope is documented in `VERSION_3.1.0.md`.

Version 3.1.1 is released. It returns scanner focus
after POS cart quantity/removal actions, adds an explicit no-write cancel path
to manual-price prompts, reserves top-level menu slot 9 for the same audited
workflow as `MANUALPRICE`, and styles the settings removal action. Product
slot 9 inside a menu remains usable. There is no migration. Focused regression
passed 24/24; the full suite completed 188 tests with 187 passed and one
existing capability skip. Headless Edge UAT passed R3.1.1/asset-v36 identity,
all four cart-focus actions, both no-write cancel paths, slot 9, computed
removal styling, and zero JavaScript errors. UAT integrity and foreign keys
passed. It is deployed cumulatively through Version 3.1.2.
See `VERSION_3.1.1.md`.

Version 3.1.2 is the current Production release and includes 3.1.1. A product
may require a fresh audit-backed whole-baht price for every POS line while
retaining its real UUID/name and unchanged master price. New products now
start active but offline; explicit online enablement remains on Edit and
existing flags are preserved. Managers can now use `/settings` and clear
individual or bulk billed balances; Cashiers remain denied and the other
Admin-only surfaces stay protected. Additive Migration 29 adds the
default-false product flag and Migration 30 grants the existing Settings
permission to Manager without rewriting business rows. Focused regression
passed 33/33; the full suite passed 194 tests with one capability skip.
Headless Edge UAT, asset-v37, SQLite integrity, and foreign keys passed.
Production Migrations 29–30 preserved 742 active products and zero sale
history. Protected SYSTEM/POS startup tasks, static LAN, firewall, runtime,
health, database integrity, and the Public Desktop recovery shortcut passed
after deployment. See `VERSION_3.1.2.md`.

Version 3.1.3 is the current Production diagnostic build. It intentionally
keeps the established browser/driver receipt method while the `POS` user tests
the actual driver. The server records transaction/queue events and the hidden
agent records its launch, claim, print request, afterprint/timeout, and ack in
the readable local diagnostic log. No migration or business-data rewrite was
made. Full regression passed 194 tests with one existing capability skip;
Production 8000 and UAT 8001 health were ready after deployment. See
`VERSION_3.1.3.md`.

Version 3.0.9 formalizes the
separate `SYSTEM` server and standard local `POS` launcher setup, repair,
least-privilege ACL, shared Desktop Python, reboot-safe display state, and
Public Desktop recovery behavior documented in `VERSION_3.0.9.md`. It retains
Version 3.0.8 POS zero-price,
unknown-barcode, and reserved `MANUALPRICE` lines now require a blocking,
positive whole-baht Cashier entry with keyboard or touch numpad. Approved
Thai alerts use the selected voice at true 1.2× speed. Each confirmed line receives a one-use
audit-backed `MP-########` reference stored and printed on the receipt; Audit
Log can filter by action and export CSV. Additive migration 27 stores the
reference without rewriting existing sale items.
Manager/Admin quick edit
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
port-8000 Production was restarted onto Release 3.0.9
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
scripts, and Windows lifecycle tasks. Task Scheduler separates the
`SYSTEM` background server from the standard-user POS desktop launcher;
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
