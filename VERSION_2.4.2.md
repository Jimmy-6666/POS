# แสนงาม มินิมาร์ท POS — Version 2.4.2

Released 2026-07-28.

## Online-order notification update

- `/online-orders` now shows the submitted-order count in a circular, pulsing
  badge immediately after the Thai page title `ออเดอร์ออนไลน์`.
- Local order audio is created and polled only on `/pos` and the online-order
  list. Other staff pages neither poll the order summary nor play its sound.
- A sidebar tap that navigates to either alert page records the user gesture;
  the destination can retry the alert immediately without requiring a second
  tap in the page content.
- While on `/online-orders`, a newly detected submitted order plays the alert
  and reloads the current filtered list so the new row appears without a
  manual refresh.

## Runtime and upgrade

- No database migration, configuration, permission, or lifecycle change is
  required. Existing 15-second local polling and mute preference remain.
- Restart after upgrading so the updated template, JavaScript, and CSS assets
  are served. Desktop remains port `8002`; UAT remains port `8001`.

## Verification

- Focused online/POS/version regression: 16 tests passed on 2026-07-28.
- Full suite: 122 passed on 2026-07-28.
- UAT: health `ok`, database `ready`; LIFF configuration confirmed through
  `/api/auth/config`.
