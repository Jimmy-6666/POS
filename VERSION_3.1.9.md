# Release 3.1.9 — VPS LINE Bot delivery hotfix

**Status:** Deployed to the separate VPS LINE Bot service on 2026-08-05.

## Scope

Release 3.1.9 is a new version of the LINE Bot on the VPS only.  It does not
modify `pos_app`, the Windows POS Production/UAT installations, the POS schema,
migrations, or POS business data.

## Why

The LINE Official Account had reached its monthly Push-message allowance.  A
confirmed product command could succeed at the POS but its final result could
be lost because the bot sent it by Push after an intermediate reply.

## Changes

- A normal confirmation sends one final success, validation, conflict, or
  initial-outage outcome through that event's LINE Reply token; no preliminary
  connecting Push is sent.
- Delayed outcomes are retained in an additive Bot-SQLite notification outbox
  and use a stable LINE retry key.  A monthly-limit rejection stays pending and
  is retried hourly without changing or duplicating the completed POS command.
- The service journal now records secret-free, opaque command and notification
  delivery outcomes for operational diagnosis.
- LINE user mentions use the current Messaging API `textV2` mention payload.

## Verification

- Focused LINE Bot tests: 48 passed.
- Full suite: 252 tests passed, with 1 existing capability skip.
- VPS service, localhost health, public health, and localhost-only listener
  checks passed after the atomic release switch.
