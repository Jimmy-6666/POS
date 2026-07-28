# Coding Rules

## Scope

- Understand the affected workflow before editing.
- Change the fewest cohesive files; avoid unrelated formatting, renames,
  moves, rewrites, and architecture changes.
- Reuse existing routes, services, components, utilities, and conventions.
- Do not modify completed business workflows unless the request requires it.
- Keep source identifiers/comments in English and user-facing content Thai
  first.

## Flask and security

- Use the application factory and existing blueprints.
- Enforce authentication/permissions on the server.
- Require and validate CSRF on state-changing browser requests.
- Treat all request data as untrusted; validate types, ranges, state, and
  ownership.
- Do not trust price, cost, totals, discounts, stock, or permission values from
  JavaScript.
- Do not expose secrets, database files, arbitrary filesystem paths, or runtime
  browser profiles.

## Money, sales, and inventory

- Store money as integer satang; use `services/money.py` at boundaries.
- Use transactions for operations spanning sales, items, payments, stock,
  movements, reconciliation, or audit records.
- Roll back the entire operation on failure.
- Record stock movement and audit history where the existing workflow does.
- Preserve receipt uniqueness and historical product/cost snapshots.

## Database

- Avoid schema changes unless required.
- Never delete an existing table/column or discard user data incidentally.
- Update both `schema.sql` for new databases and an idempotent additive
  migration in `database.py` for existing databases.
- Enable/retain foreign-key behavior and use parameterized SQL.
- Update `DATABASE_OVERVIEW.md` and tests for any schema/migration change.

## Verification

- Add or update focused regression tests for changed behavior.
- Run focused tests first.
- Run the full suite for shared logic, schema, auth, sales, inventory,
  reconciliation, or release preparation.
- Report exact commands and pass/fail counts; never hide baseline failures.

## Documentation

Documentation is part of the deliverable. Update only affected compact docs,
then `CHANGELOG.md`. Add a decision only for durable architectural/business
choices. Never duplicate the entire requirement contract into status files.
The six compact first-read Markdown files may contain up to 1,600 words each;
move deeper history and procedures to linked documents.

## Auxiliary import tooling

- Treat `work/`, `imports/`, `outputs/`, and `uat_runtime/` as a separate
  development/UAT workflow, not as POS runtime dependencies.
- Never promote synthetic barcodes, zero sale prices, or unreviewed catalog
  mappings to production.
- Replace hard-coded external input paths with explicit configuration before
  calling an import workflow portable or repeatable.
