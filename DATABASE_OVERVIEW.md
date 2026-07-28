# Database Overview

## Migration history

The existing additive startup migrations remain in pos_app/database.py.
Sprint 1 adds the schema_migrations table and records the existing schema
version 19 as legacy-ad-hoc-migrations. Version 20 enables the existing
negative-stock setting because earlier releases displayed it without applying
it to sales. Version 21 adds verified LINE customer identity/profile and saved
delivery defaults. Version 22 adds registered customer names and lifecycle
fields for auditable anonymizing deletion. Version 23 backfills immutable
product UUIDs, adds required/immutable database guards, and converts valid
held-bill cart identities to UUIDs without rewriting historic relational keys.
Future migrations use
pos_app/migrations.py and record version, name, checksum, application version,
UTC timestamp, and success state. A failed migration prevents startup.

Version 24 adds admin-only encrypted TOTP state, one-way-hashed recovery codes,
and short-lived pre-session login challenges. No password, TOTP secret, TOTP
code, or recovery code is recorded in audit data.

Version 25 adds `reconciliations.void_total_satang`. It is an additive closing
snapshot of the valid, recorded item-void amount during that closing window;
it does not alter historic sales, refund, or stock records.

Version 26 adds `staff_sessions.two_factor_verified_at`. Only a session created
after a successful Admin second-factor challenge receives this marker; existing
sessions are preserved for LAN use but cannot be used on the public Admin host.

SQLite is the single local source of truth. `pos_app/schema.sql` defines new
databases; `pos_app/database.py` initializes seed data and applies idempotent,
data-preserving startup migrations. Current seeded `schema_version` is 19.

## Domains and tables

| Domain | Tables |
|---|---|
| References/settings | `categories`, `units`, `adjustment_reasons`, `payment_methods`, `settings` |
| Identity/security | `roles`, `permissions`, `role_permissions`, `staff`, `staff_sessions`, `login_events`, `audit_logs` |
| Catalog | `products` |
| Sales/payments | `receipt_sequences`, `sales`, `sale_items`, `held_bills`, `sale_voids`, `sale_void_items` |
| Billing/credit | `billing_customers`, `billed_sales`, `billed_sale_payments` |
| Inventory/receiving | `stock_movements`, `stock_receipts`, `stock_receipt_items`, `suppliers` |
| Stock count | `stock_count_sessions`, `stock_count_participants`, `stock_count_items`, `stock_count_attempts`, `stock_count_results`, `stock_count_applications` |
| Closing | `reconciliations`; settlement link lives on `sales` |
| Online identity | `customers`, `customer_sessions`, `customer_login_events` |
| Online orders | `delivery_locations`, `online_order_sequences`, `online_orders`, `online_order_items`, `online_order_status_history` |
| Online payment/stock | `online_bank_accounts`, `online_order_payments`, `stock_reservations`, `order_reconciliation_events` |

## Invariants

- Monetary columns ending in `_satang` are integers.
- Product stock and count quantities are real values because some products
  allow decimal quantities.
- Barcodes and receipt numbers are unique.
- `products.product_uuid` is a globally unique immutable UUID. It is the only
  product identity exposed to routes, browser payloads, and module boundaries;
  `products.id` remains a private numeric foreign key for historic tables.
  SKU and barcode are unique mutable business fields, never identity keys.
- Historical sale items snapshot product name, price, cost, and quantity.
- Stock changes have corresponding immutable movement records.
- Foreign keys are enabled per connection; WAL is enabled for LAN concurrency.
- A completed sale may be settled once through
  `sales.settled_reconciliation_id`.
- Each successful void links the original sale cashier through `sales.cashier_id`
  and the authorizing active Manager/Admin through `sale_voids.voided_by`.
  Item-level records retain product identity, quantity, and the refund amount;
  the audit payload additionally snapshots the product name and unit price.
- `reconciliations.void_total_satang` is calculated from `sale_void_items` for
  the applicable cashier and closing window, then stored with the close so
  historical reconciliation summaries remain stable.
- Sessions are stored server-side; only token hashes are persisted. A public
  Admin session must also carry the server-side second-factor verification
  marker and belong to an Admin account with two-factor authentication enabled.
- Schema version 17 enables `is_online_available` for all existing products
  once and defaults new products to online. The customer catalogue still
  excludes inactive products and products with a zero selling price.
- Historic `online_bank_accounts` records are retained for data preservation,
  but no new customer-facing transfer destination is configured or displayed.
- `customers.line_user_id` is unique and comes only from successful LINE ID
  token verification. New online orders require a completed LINE profile;
  registered name, phone/location/room defaults are retained for delivery.
- Deleting a customer preserves the original `customers.id` and related orders,
  marks the row deleted, records the responsible staff and time, removes direct
  LINE/contact identifiers, and substitutes a unique tombstone phone value.
  The prior LINE identity and phone may therefore create a new customer later.
- `online_orders.sale_id` is unique. Items retain original/current quantity,
  name/barcode/current price, and `customer_confirmed_unit_price_satang`.
  Existing rows are backfilled from their prior price snapshot; a null confirmed
  price identifies a product added by staff after customer submission.
- Reservations become `released` on cancellation/expiry or `converted` in the
  transaction that creates the sale and stock movements.
- `sales.delivery_fee_satang` records the explicit receipt delivery charge.
- `settings.allow_negative_stock` controls POS sales and
  `settings.online_allow_negative_stock` independently controls online
  reservations. Both default to `1`; when enabled, negative movements remain
  fully auditable. Online customer controls use the configured per-order limit
  rather than an unavailable-stock ceiling when online negative stock is on.
- Historic `online_order_payments` records are retained, but customer slip
  upload and staff transfer verification are no longer active. New online
  orders select cash or transfer for confirmation at delivery only.
- Sprint 3 adds no business-data table: `maintenance.manage` is a seeded,
  admin-only permission. Support-bundle and signed-update actions write the
  existing immutable `audit_logs` table; staged packages and support ZIPs stay
  in their dedicated runtime directories.
- `settings.backup_schedule_enabled` and `settings.backup_schedule_time` store
  the daily Asia/Bangkok database-plus-product-image sync preference. They are
  operational settings only; no business-data migration is required.

## Migration rule

For a required schema change:

1. describe data and compatibility impact before coding;
2. add the desired shape to `schema.sql`;
3. add an idempotent migration to `initialize_database()`;
4. preserve all existing rows and relationships;
5. add tests for fresh and pre-existing database behavior;
6. increment the schema version and update this file plus `CHANGELOG.md`.

`DATABASE_SCHEMA.md` contains older detailed design/history. Use the live schema
and migration code as implementation truth when they differ.
