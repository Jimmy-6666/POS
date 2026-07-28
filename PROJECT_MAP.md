# Project Map

## Runtime path

`app.py` → `pos_app.create_app()` → database/auth initialization → registered
Flask blueprints → Jinja templates and local static assets.

`pos_desktop.py` manages the Windows desktop experience and starts/controls the
Release 2.2 server. Batch files select the port and runtime root.

## Source map

| Area | Primary files |
|---|---|
| App/config | `app.py`, `pos_app/__init__.py` |
| Authentication, sessions, CSRF, permissions, public-host isolation | `pos_app/auth.py`, `pos_app/routes/auth.py`, `pos_app/public_host_access.py`, `pos_app/web_security.py` |
| Database bootstrap/migrations | `pos_app/database.py`, `pos_app/schema.sql` |
| Dashboard/health | `pos_app/routes/main.py`, `index.html` |
| Product/catalog/price control | `pos_app/product_identity.py`, `pos_app/services/product_spreadsheet.py`, `pos_app/routes/products.py`, product/reference/price templates, `product-form.js` |
| Register, held bills, sales, receipts, voids | `pos_app/routes/pos.py`, `pos_app/services/sales.py`, POS/sales/receipt templates, `pos.js` |
| Money conversion/change | `pos_app/services/money.py` |
| Receiving, adjustments, ledger, suppliers | `pos_app/routes/inventory.py`, inventory templates |
| Blind stock count | `pos_app/routes/stock_count.py`, stock-count templates, `stock-count.js`, local barcode vendors |
| Closing, billing, reports | `pos_app/routes/reporting.py`, reconciliation/billing/report templates, `billing-report.js` |
| Staff, settings, audit, backup | `pos_app/routes/admin.py`, admin templates |
| Runtime maintenance, signed updates, support bundles | `pos_app/routes/maintenance.py`, `services/signed_updates.py`, `services/support_bundle.py`, `apply-signed-update.ps1` |
| Customer ordering/auth/cart/history | `pos_app/routes/online.py`, `customer_auth.py`, `templates/online/`, online JS/CSS |
| Online fulfilment/reservations | `services/online_orders.py`, `routes/online_staff.py`, staff/reconciliation templates |
| Online settings/customers/locations | `routes/online_admin.py`, online admin/customer templates |
| Shared UI | `pos_app/templates/base.html`, `static/css/app.css`, `static/css/v2.css`, `static/js/sidebar.js` |
| Receipt UI | `receipt.html`, `static/css/receipt.css`, `receipt-popup.js` |
| Windows launch/display | `pos_desktop.py`, `pos_app/launcher.py`, `pos_app/display_state.py`, `start-*.bat`, `install-*.bat` |
| Production backup/recovery | `pos_app/services/backup.py`, `pos_app/services/file_sync.py`, `pos_app/services/remote_backup.py`, `pos_app/backup_cli.py`, `backup-production.ps1`, `scripts/*recovery*.ps1` |
| VPS provisioning | `deploy/vps/*.sh` |
| UAT fixtures | `seed_uat.py`, `start-uat.bat`, `install-uat.bat`, `uat_runtime/` (generated) |
| Makro catalog preparation | `work/makro-pos-import/*.mjs`, `imports/makro-products/` inputs/artifacts, `outputs/` review workbooks |
| Automated verification | `tests/test_phase1.py`, `test_phase2.py`, `test_phase3_5.py`, `test_phase6_10.py`, `test_inventory.py`, `test_billing.py`, `test_version_2_1.py`, `test_version_2_2.py`, `test_release_3_transactions.py`, `test_public_host_access.py`, `test_sprint3_maintenance.py` |

Templates are under `pos_app/templates/`; static files are under
`pos_app/static/`. Runtime databases, browser profiles, uploads, backups,
imports, generated outputs, and UAT data are not source modules.

## Scope packets

- UI-only page change: relevant template + page JS + `app.css`/`v2.css` only
  where needed + rendering/behavior test.
- Sales/payment change: POS route + `services/sales.py` + `money.py` if needed +
  POS template/JS + phase 3–5/billing tests.
- Inventory change: inventory or stock-count route + affected templates/JS +
  inventory/phase 6–10 tests.
- Reporting/closing change: `reporting.py` + affected template/JS + phase 6–10
  or billing tests.
- Auth/admin change: auth/admin route + relevant template + phase 1/2 tests.
- Schema change: `schema.sql` + additive migration in `migrations.py` + affected
  domain code/tests + `DATABASE_OVERVIEW.md`.
- Online ordering change: affected customer/staff/admin route +
  `services/online_orders.py` for lifecycle/reservations + online UI +
  `test_online_phase*.py`; include sales tests when completion changes.
- Launcher change: desktop/launcher/display files + batch file + version 2.1
  tests.
- Makro/UAT import change: relevant `work/makro-pos-import` scripts + manifest,
  review workbook, UAT verifier, and database integrity/foreign-key checks.
  `fetch-metadata-images.mjs` accepts explicit raw JSON/CSV input and output
  paths; these scripts use development Node tooling and are not deployable POS
  runtime code.

See `MODULE_DEPENDENCIES.md` for cross-module impact.

Production lifecycle files are kept at the repository root for operator use.
They use production-common.ps1 and never modify start-uat.bat.

The backup service is independent of Flask requests. It uses the SQLite online
backup API, publishes only verified archives, and never restores over the
active runtime. File sync is allow-listed and records its inventory under
`runtime/config/file-sync-inventory.json`.
