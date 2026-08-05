# Release 3.1.7 candidate — LINE Bot Gemini budget enforcement

Status: deployed to the Live Production LINE Bot VPS after owner confirmed Paid
Tier billing was ready. No POS application or Windows POS deployment occurred.
Versions 3.1.6 and 3.1.7 are VPS LINE Bot-only releases; POS application work
may begin no earlier than Version 3.1.8.

## Scope

- Adds a configurable, application-enforced Gemini monthly ceiling through
  `GEMINI_MONTHLY_BUDGET_USD` (default `1.00`).
- Uses a Bot-SQLite idempotent reservation ledger keyed by Vision job and
  attempt. A call is reserved atomically before it can reach Gemini; recovered
  workers, duplicate events, and retries cannot reuse that attempt.
- Reserves a conservative maximum for the two bounded images and the 512-token
  response. It settles to SDK usage metadata when available; absent metadata
  retains the reservation conservatively.
- Continues the established manual-name workflow without calling Gemini when
  the cap would be exceeded. Barcode decoding and signed POS lookup remain
  before every possible Gemini call; known products continue to skip Gemini.
- Limits deployed Vision to exactly one Gemini call per new product; a transient
  provider failure also takes the manual fallback rather than retrying Gemini.
- Adds the private `python -m line_bot gemini-budget` diagnostic command. It
  reports month, request count, estimated/actual spend, and remaining budget,
  never secrets or image data.

## Model and billing boundary

The selected model is `gemini-3.1-flash-lite`, the stable Gemini model that
supports image input and structured text output. It was listed successfully
from the billing-enabled project before deployment.
Operators must set exact current per-million-token prices whenever they set
`GEMINI_MODEL`. Vision startup now requires those explicit prices, preventing
an unpriced model from bypassing a claimed hard cap.

The existing LINE channel, Cloudflare tunnel, POS application, Windows runtime,
POS schema, migration, and business data were not changed. The VPS service was
configured with `GEMINI_MONTHLY_BUDGET_USD=1.00`, `GEMINI_MAX_ATTEMPTS=1`, and
the verified 3.1 Flash-Lite Standard prices. A source/config/Bot-SQLite backup
was created at `20260802T165658Z-before-linebot-gemini-budget-3.1.7` before the
atomic release switch.

## Verification

- Focused LINE Bot regression: 46 passed.
- Full suite: 249 passed with 1 existing capability skip (250 run).
- VPS: Billing-project model listing passed; service active; localhost health,
  public tunnel health, and zero-usage budget diagnostic passed after restart.
