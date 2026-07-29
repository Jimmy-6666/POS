# Saengngam Minimart POS — Version 3.0.5

Prepared 2026-07-30.

## Registration consent

- First-time LINE customer profile completion requires a checked acceptance
  control for “เงื่อนไขการใช้งานและนโยบายความเป็นส่วนตัว (PDPA)”.
- The browser marks the checkbox as required and the server independently
  rejects profile review when acceptance is missing.
- Acceptance is carried through the existing review/confirmation step.
  Completed customer profiles are not asked to accept again when edited.
- This release does not add a consent timestamp or stored consent record.

## Policy presentation

- The terms/PDPA text opens the existing public `/order/policy` page in a
  responsive modal.
- Browsers without native dialog support retain the normal standalone policy
  link as a fallback.
- The Release 3.0.4 policy and product-image disclaimer content is preserved.
- The policy button is removed from the customer header.

## Registration wording

- “ชื่อสำหรับติดต่อ” is now
  “ชื่อสำหรับติดต่อ (สามารถใช้ชื่อเล่นได้)”.
- “สถานที่จัดส่ง” is now
  “สถานที่จัดส่ง (เปลี่ยนแปลงตอนสั่งซื้อได้)”.

## Compatibility

- No database schema or migration change.
- Existing LINE identity, completed customer profiles, ordering, sales, stock,
  private-LAN access, runtime data, uploads, and backups are preserved.

## Verification

- Focused LINE-auth, online phase 1, public-host, and release-identity suites:
  33 passed.
- Browser verification passed at 390 px mobile, 768 px tablet, and 1280 px
  desktop widths with no horizontal overflow. The policy popup remains on the
  profile page, its close control is 44 px, and opening the link does not
  change the checkbox state.
- Full suite: 158 tests completed—157 passed and one existing
  filesystem-capability skip.
