# Saengngam Minimart POS — Version 3.0.4

Prepared 2026-07-30.

## Combined terms and PDPA access

- The customer online header has one touch-friendly
  “เงื่อนไขการใช้งานและ PDPA” button on customer ordering pages.
- The button opens the existing public `/order/policy` route. The policy stays
  readable without LINE login and does not load the LINE authentication
  script.
- This release provides a combined public notice; it does not add a mandatory
  acceptance checkbox, consent timestamp, or stored consent record.

## Product-image disclaimer and contact

- The combined page explains that packaging, labels, and product appearance may
  differ from displayed images and may be changed by the manufacturer or
  distributor without prior notice.
- Quantity and unit follow the displayed product and order details.
- Customers who receive a different item or are unsure can contact the store
  using the phone number and LINE ID configured in POS online settings.
- Phone and LINE actions are rendered as touch-friendly links; contact values
  are not duplicated or hard-coded in the policy template.

## Compatibility

- No database schema or migration change.
- Existing customer authentication, online ordering, product images, sales,
  stock, private-LAN access, privacy controls, runtime data, uploads, and
  backups are preserved.

## Verification

- Focused public-policy, public-host, and release-identity suites: 25 passed.
- Browser verification passed at desktop and mobile breakpoints with no
  horizontal overflow or console warnings/errors.
- Full suite: 158 tests completed—157 passed and one existing
  filesystem-capability skip.
