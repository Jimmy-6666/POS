# Database Overview

## Migration history

The existing additive startup migrations remain in pos_app/database.py.
Sprint 1 adds the schema_migrations table and records the existing schema
version 19 as legacy-ad-hoc-migrations. Future migrations use
pos_app/migrations.py and record version, name, checksum, application version,
UTC timestamp, and success state. A failed migration prevents startup.

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
- Historical sale items snapshot product name, price, cost, and quantity.
- Stock changes have corresponding immutable movement records.
- Foreign keys are enabled per connection; WAL is enabled for LAN concurrency.
- A completed sale may be settled once through
  `sales.settled_reconciliation_id`.
- Sessions are stored server-side; only token hashes are persisted.
- Schema version 17 enables `is_online_available` for all existing products
  once and defaults new products to online. The customer catalogue still
  excludes inactive products and products with a zero selling price.
- `online_bank_accounts` stores reusable transfer destinations. The selected
  active account is copied to the existing online payment settings so customer
  and order views retain their established interface.
- `customers.is_guest` distinguishes one-time checkout identities.
  `online_orders.contact_phone` and `contact_name` preserve guest delivery
  contact details without making the phone a reusable login credential.
- `online_orders.sale_id` is unique. Items retain original/current quantity,
  name/barcode/current price, and `customer_confirmed_unit_price_satang`.
  Existing rows are backfilled from their prior price snapshot; a null confirmed
  price identifies a product added by staff after customer submission.
- Reservations become `released` on cancellation/expiry or `converted` in the
  transaction that creates the sale and stock movements.
- `sales.delivery_fee_satang` records the explicit receipt delivery charge.

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
