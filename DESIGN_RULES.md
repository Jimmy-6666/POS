# Design Rules

## Product experience

- Thai language first and understandable to minimart staff.
- Optimize for fast cashier flow: scanning, search, quantity adjustment,
  payment, confirmation, and receipt.
- Touch-friendly on Windows desktop, iPad/tablet, and mobile LAN clients.
- Use large targets, legible totals, clear selected/disabled/error states, and
  visible keyboard focus.
- Avoid decorative complexity and unnecessary animation.
- Preserve familiar workflows and screen structure unless redesign is
  explicitly requested.

## Existing visual system

- `base.html` is the shared shell.
- `app.css` contains the base system; `v2.css` contains the current Release 2
  refinements. Extend existing tokens/classes before creating new patterns.
- Tahoma-first typography is an accepted Release 2 choice.
- POS has a fixed desktop/tablet cart and a mobile cart drawer.
- Receipt layout is isolated in `receipt.css` and must remain compatible with
  80 mm browser printing.
- Local vendor assets support barcode generation/scanning; do not introduce a
  CDN dependency.

## Responsive and accessible behavior

- Verify desktop, tablet, and narrow mobile layout for changed shared UI.
- Keep primary actions reachable without excessive scrolling.
- Do not encode meaning by color alone.
- Preserve semantic labels, input modes, autofocus only where workflow-safe,
  and `aria-live` feedback used by scanner/payment flows.
- Keep print-only and screen-only behavior explicit.

## Customer ordering

- Use the separate mobile-first Thai customer shell, two-column narrow-phone
  product grid, large cart/payment controls, and explicit empty/error/closed
  states.
- Never expose cost, profit, suppliers, internal notes, inactive products, or
  staff-only history.
- Show customer status/payment labels in Thai while keeping internal codes in
  English.
- Reconciliation keeps barcode input workflow-safe and provides an explicit,
  audited manual fallback.

## UI change checklist

Before finishing: check Thai copy, touch target size, focus/keyboard use,
overflow, empty/error/loading state, role visibility, mobile layout, and print
impact. For POS changes, also check scanner focus and duplicate-submit
protection.
