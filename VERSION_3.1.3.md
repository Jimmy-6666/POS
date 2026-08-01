# Saengngam Minimart POS — Version 3.1.3

Status: Production print-driver diagnostics update

Migration: none

## Purpose

The existing browser print-agent and the Windows printer driver remain the
active automatic printing path. This release makes that path observable when
the local standard `POS` account is used, without changing a sale, stock,
payment, receipt number, or printer driver setting.

## Print diagnostic timeline

For each automatic POS receipt and checked online-order summary, the local log
records the same opaque job ID across these stages:

1. completed POS transaction or online reconciliation;
2. in-memory print job queued by the server;
3. browser print-agent page opened under the local Windows `POS` user;
4. agent claim, receipt render, and browser print request;
5. browser `afterprint`, timeout fallback, acknowledgement, or acknowledgement
   failure.

The launcher passes its Windows user name only as local diagnostic context.
No print-agent token, PIN, session value, customer data, payment evidence, or
product image is written to the log.

## Operator workflow

- Sign in to the local Windows `POS` account and open the POS launcher.
- Use the new `เปิด Log การพิมพ์` button to open
  `runtime\pos-desktop\print-diagnostics.log` in Notepad.
- Complete one normal transaction. The sequence shows exactly whether the
  driver problem is before the agent starts, before the document reaches
  browser print, during the 15-second browser acknowledgement fallback, or
  only after browser hand-off to the Windows spooler.
- The file is limited to 512 KiB and retains the newest 256 KiB on rotation.
  Logging is best-effort: a locked log can never block a transaction or print.

## Post-restart printing hotfix

- Automatic print jobs now open the existing receipt document in Edge's
  top-level frame. The receipt uses its standard print hook, then sends an
  afterprint acknowledgement before returning to the protected print queue.
  No printable iframe remains in the browser flow.
- The Wilai Startup helper and production desktop launcher coordinate so only
  one Edge print worker runs after Windows starts. The standard `POS` account
  remains on its launcher-managed worker and default printer setup.

## Compatibility

- No schema migration or business-data change.
- Receipt rendering, the protected agent token, kiosk print settings, manual
  browser receipt printing, UAT isolation, and the SYSTEM server/POS standard
  user boundary remain unchanged.
- The raw-driver experiment is not enabled by this release; this diagnostic
  build intentionally observes the established Windows driver path first.
