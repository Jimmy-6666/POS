# Architecture Decisions

Append decisions; do not rewrite history. A decision change must state what it
supersedes and why.

| ID | Decision | Consequence |
|---|---|---|
| D-001 | Offline-first Flask + SQLite + Jinja + vanilla JS/CSS | No required cloud, Docker, Node, React, CDN, or frontend build step. |
| D-002 | Windows host with private-LAN access | Waitress listens on the configured port; do not expose the app publicly without a separate security decision. |
| D-003 | Thai-first, touch-first UI | Labels/workflows prioritize Thai cashiers and large, direct controls; receipt output supports 80 mm printing. |
| D-004 | Monetary values use integer satang | Convert only at input/output boundaries; never use binary float for stored money. |
| D-005 | Server owns business truth | Re-read price, cost, stock, totals, permissions, and payment rules on the server; browser totals are advisory. |
| D-006 | Sales and stock mutations are atomic and auditable | Use explicit transactions for multi-row writes and retain movement/audit history. |
| D-007 | Schema evolution is additive and data-preserving | Base schema is idempotent; startup migrations in `database.py` support older databases. |
| D-008 | Roles are admin, manager, cashier with server-side permission checks | Menu visibility is UX only and must never replace route authorization. |
| D-009 | Release/UAT runtime data is isolated by `POS_RUNTIME_ROOT` | Current Release 2.2 uses `runtime/`; UAT uses `uat_runtime/`; tests use temporary databases. |
| D-010 | Original requirements remain authoritative | Compact AI documents provide navigation and current state but cannot silently narrow the accepted contract. |
| D-011 | Routine AI work uses scoped context packets | Read six compact files, then only the affected module/UI/test/data files. Full-repository review requires explicit need. |
| D-012 | Makro import tooling is development-only | Deployed POS stays Python-only; catalog barcodes and prices require owner approval. |
| D-013 | Online stock is reserved at submission and deducted only at delivery completion | Cancellation, rejection, and expiry release it; conversion, sale, payment, receipt, and audit commit once atomically. |
| D-014 | Customer identity uses a separate hashed-token session and non-enumerable public IDs | Customer routes never inherit staff authority; order access checks ownership. |
| D-015 | Expiry and notifications use access-triggered checks and local polling | No background/cloud dependency; relevant access expires orders and staff alerts poll every 15 seconds. |
| D-016 | Active, positively priced products are online-eligible by default; transfer destinations are reusable with one selected account | An additive migration enables existing products; managers can select an account without re-keying it. |
| D-017 | UAT customer ordering supports zero-price items, guest checkout, and payment at delivery | Supersedes D-016’s positive-price gate and the initial transfer-slip workflow for UAT; phone contact is snapshotted, optional 4-digit PIN creates a reusable account, and delivery staff confirm cash/transfer at handoff. |
| D-018 | Reconciliation prints a checked-order summary; fiscal sale and payment stay atomic at delivery | Early printing does not record payment; it states it is not proof of payment and D-013 remains the stock/financial boundary. |
| D-019 | Delivery staff reconfirm cash/transfer at handoff; automatic printing is limited to the Desktop Launcher profile | A changed method updates the order, payment, sale, and audit log. Other browsers offer explicit receipt/summary links. |
| D-020 | Receipt auto-printing uses a token-protected queue and off-screen kiosk browser; the Launcher otherwise prints normally | Narrows D-019 only: POS receipts and checked-order summaries auto-print; stock sheets and other documents use browser preview. |
| D-021 | Manager/Admin price changes save directly from product edit or filtered barcode lookup | Supersedes preview; changes remain server-validated in satang and create `change_price` audits. |
| D-022 | Staff order edits use current prices but retain the confirmed-price snapshot; assignment saves at delivery start | Edits atomically update reservation, totals, history, and audit; they warn on reconfirmation. The owner is default courier, but ready-order selection can change it. |
| D-023 | Runtime paths; Task Scheduler; Private/LocalSubnet firewall | Preserve legacy data. |
| D-024 | New online orders will use verified LINE LIFF identity; guest and new phone/PIN checkout retire while historic data remains | Supersedes D-017 entry flow: every new order links to verified LINE ID. Cloudflare HTTPS is customer-only; staff stays local unless approved. |
| D-025 | Negative stock is a configured operating mode applied consistently by server-side sale and online validation | When enabled sales may go below zero; transaction, stock-movement, and audit records preserve shortage visibility. |
| D-026 | Customer deletion is an audited anonymizing tombstone, not a relational delete | Preserve customer/order references and staff/time audit data; clear direct identifiers and unique constraints so the same person can register again. |
