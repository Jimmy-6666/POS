# Saengngam Minimart POS — Version 3.1.0

Date: 2026-07-31

## Purpose

Version 3.1.0 makes the cashier workflow easier for staff who normally sell by
barcode and need only a small, curated set of large touch buttons for products
without a practical barcode.

## Accepted behavior

- Every staff role lands on `/pos` after a successful login. A supplied `next`
  destination does not bypass this cashier-first entry point.
- The `ขายหน้าร้าน` sidebar section is first. A fresh login collapses the
  sidebar automatically; the existing expand/collapse control remains.
- The POS search/scanner, cart, held bills, manual-price prompt, payment,
  printing, and audit behavior remain in place.
- The old category-chip rail and image catalog are removed from the POS sale
  screen. Manual selection uses a text-only 3×3 grid and does not load product
  images or the default-image asset.
- Product buttons omit barcode text, reserve up to two large lines for the
  product name, and show the selling price at approximately twice the prior
  type size so the available button area is used efficiently. A one-line name
  is vertically centered within the reserved name area while a two-line name
  retains the full two-line layout.
- Menu buttons show only the configured name, centered at a larger size with
  a two-line limit. The menu number, helper instruction, and manual-button
  eyebrow are not shown; group titles align centrally with the Back control.
- The first grid level contains independently configured button menus. Opening
  a menu shows its configured products using the same text-only 3×3 layout.
- Position is continuous: 1–9 is page 1, 10–18 is page 2, and so on. Empty
  positions remain intentionally empty. Previous/Next controls appear only
  when another page exists.
- A non-empty search remains global across active products and may still add an
  exact barcode directly. Unknown/zero-price/manual-price behavior remains the
  Version 3.0.8 blocking audited workflow.
- After a sale completes successfully, the lookup is cleared and manual
  selection returns to the top-level menu ready for the next customer.
- Manager/Admin can use `สินค้าและคลัง > ตั้งค่าปุ่มขาย` to create, rename,
  position, enable, or disable a button menu and to add, move, or remove active
  products inside it. Cashiers cannot access this configuration route.
- Configuration writes use CSRF protection, explicit transactions, server-side
  permission checks, duplicate-position protection, and immutable audit logs.
- The close-round form has one shared on-screen Numpad for its four whole-baht
  money inputs. It includes digits, `00`, backspace, clear, and next-field
  controls. Version 3.1.0 does **not** add a close-round PIN requirement.

## Database

Additive Migration 28 creates:

- `pos_button_groups`: independent menu name, global position, active state,
  actor references, and timestamps.
- `pos_button_items`: group/product mapping, global position inside the group,
  actor references, and timestamps.

Unique constraints protect one top-level menu per position and one product and
one position per group. Existing products, categories, sales, stock, images,
and configuration rows are not rewritten.

## Compatibility and release boundary

- Product barcodes remain required by the product master. A button mapping
  determines manual visibility and does not reinterpret the product category.
- Existing Release 3.0.9 Windows account isolation, launcher, print-agent,
  startup tasks, network policy, and runtime paths remain the deployment
  baseline.
- This document records the Version 3.1.0 source contract. Production must not
  be advanced until focused, full-suite, and UAT visual/interaction checks pass
  and the owner explicitly authorizes release.

## Verification

- Release/affected regression set: 57/57 passed.
- Full suite: 185 completed, 184 passed, and one existing capability skip.
- Headless Microsoft Edge at 1920×1080 rendered exactly nine 3×3 text buttons
  on page 1 at both menu and product levels, exposed item 10 on page 2, made no
  product-image/default-image request, and kept the POS controls within the
  viewport.
- Closing Numpad interaction produced `1200` from `1`, `2`, `00` and moved
  focus to the next money field.
- A subsequent 1366×768 UAT check confirmed no barcode element, a 32px product
  name, a 41px price, and the intended two-line name limit; 19 focused
  UI/regression tests passed after this refinement.
- The final 1366×768 UAT check confirmed two-line menu and product names,
  vertically aligned menu navigation, no helper labels, and automatic
  top-level-menu reset after a successful sale.
