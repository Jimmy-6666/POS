# Release 3.2.0 — cumulative POS and LINE Bot source

## Status

Release 3.2.0 combines the previously divergent POS and LINE Bot histories in
one source baseline. Publishing this source release does not itself redeploy
the Windows POS or the VPS service and does not rewrite runtime data.

## Lineage

- POS baseline: `v3.1.8` (`9d550206`), including the approved 80 mm
  POSPrinter GDI receipt and in-job logo implementation.
- LINE Bot baseline: `v3.1.9` (`8e1f6446`), including the signed POS boundary,
  Vision/Gemini flow, monthly cost control, Reply-first command outcome, and
  durable delayed-notification delivery.
- Shared GitHub ancestor: Production source `v3.1.5` (`e36ebe74`).

## Combined behavior

- POS keeps the complete 3.1.8 receipt behavior: native
  `80(72)mm x 297mm` driver form, approved logo drawn in the SYSTEM GDI job,
  single cash-drawer pulse, and unchanged sales/inventory semantics.
- LINE Bot keeps the complete 3.1.9 behavior: allowed-group shared Quote flow,
  barcode/POS lookup before one Gemini request, `gemini-3.1-flash-lite`, the
  configurable monthly application budget, Reply-first final outcomes, and a
  stable-retry-key outbox for delayed Push delivery.
- The POS signed integration and additive Migration 31 are included because
  the separate VPS Bot depends on that boundary. There is no new 3.2.0 schema
  migration beyond the already released Migration 31.
- Runtime, launcher, UAT, and visible POS source identity are advanced to
  `3.2.0` so the cumulative source is not mistaken for either partial branch.

## Verification

- Source-tree comparison confirmed the four core POS receipt files are
  byte-for-byte unchanged from `v3.1.8`.
- Source-tree comparison confirmed `line_bot/`, `deploy/line-bot/`, and
  `docs/LINE_BOT_SETUP.md` are unchanged from `v3.1.9`.
- Focused cumulative POS/LINE Bot/runtime regression: 73/73 passed.
- Full suite: 258 tests run, 257 passed and one existing filesystem-link
  capability test skipped; no failures.
- Release documents contain no unresolved merge markers and `git diff
  --check` passed.
