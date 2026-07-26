# Module Dependencies

## Shared dependency flow

`create_app` configures runtime paths and initializes `database` and `auth`.
Every blueprint depends on those shared layers. Templates depend on the
authentication context (`current_staff`, `csrf_token`) and shared shell/assets.

## High-impact modules

| Module | Direct consumers | Regression risk |
|---|---|---|
| `pos_app/database.py` / `schema.sql` | all routes/services/tests | Existing data, startup, seed idempotency, foreign keys |
| `pos_app/auth.py` | all protected routes/templates | Login, expiry, CSRF, permissions |
| `customer_auth.py` / `routes/online.py` | customer catalogue, checkout, history, slips | Customer isolation, CSRF, session expiry |
| `services/online_orders.py` | customer submission and staff fulfilment | Reservation races, transitions, exactly-once conversion |
| `services/sales.py` | POS completion and void workflows | Money totals, stock, receipts, audit, billing |
| `services/money.py` | sales, reporting/closing, UI formatting boundaries | Rounding and totals |
| `templates/base.html`, `app.css`, `v2.css` | nearly every screen | Responsive layout, navigation, role-specific UI |
| `routes/reporting.py` | closing, billing, reports, CSV | Settlement boundaries, cash totals, permissions |
| `pos_desktop.py` / `display_state.py` | Windows Release 2.1 launch flow | Ports, process ownership, fullscreen state |

## Domain coupling

- A completed/voided sale affects `sales`, `sale_items`, products,
  `stock_movements`, optional billing records, audit, receipt/history,
  dashboard/reporting, and reconciliation.
- Receiving affects product quantity/cost, receipt tables, stock movements,
  supplier UX, audit, and profit on later sales.
- Stock-count application affects products, movements, count result/application
  records, audit, and subsequent sales.
- Reconciliation consumes completed unsettled sales and assigns
  `settled_reconciliation_id`; reports aggregate the same sales timestamps and
  payment codes.
- Role/permission changes affect route decorators and navigation visibility.
- Runtime-root changes affect database, uploads, backups, secret key, display
  state, and launcher logs.
- Submitted online orders reserve stock without reducing physical quantity.
  Cancellation/rejection/expiry releases it; delivery completion calls the
  existing sale service and atomically converts the reservation, deducts stock,
  creates one receipt, and links `online_orders.sale_id`.
- Slips and the optional bank QR use protected `uploads/online-payments`;
  backups include the complete uploads tree.
- Makro preparation scripts consume external product/price source JSON plus
  cached Makro metadata/images, generate review artifacts, and populate only
  `uat_runtime`. Their output touches catalog, stock opening movements, product
  images, categories/units, and UAT settings, but must not touch production
  runtime data.

Use the full suite when changing any high-impact module.
