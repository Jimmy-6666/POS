# LINE Product-Maintenance Bot — UAT and Production Setup

This document configures the separately deployed VPS bot.  It does not turn the
POS staff application into a public product-management endpoint.

## 1. Values to collect from LINE Developers

Open the **Messaging API channel** for the bot (not the existing customer LIFF
login channel) in LINE Developers Console.

1. In **Basic settings**, copy the **Channel secret** and **Your user ID**.
   `Your user ID` is the Bot user ID used to recognize a real `@bot` mention.
2. In the **Messaging API** tab, issue/copy a **Channel access token
   (long-lived)**.
3. Enable **Use webhook** and **Allow bot to join group chats**. In LINE
   Official Account Manager, keep **Webhooks** enabled, turn off the greeting
   message and response hours, and select **Manual chat** so LINE's own canned
   replies cannot conflict with the product-maintenance flow.
4. Keep the approved existing webhook URL when it is already healthy. Group
   Mode isolates Vision UAT on that webhook; do not replace it with a second
   UAT URL.

Treat the secret and access token as passwords.  Do not commit them, put them
in screenshots, or paste them in a Git issue.  They are stored only on the VPS
in `/etc/raisanngam-line-bot/line-bot.env` (mode `0640`, root-owned).

## 2. Shared Production webhook and tunnel for Group Mode UAT

The approved existing endpoint is:

```text
https://linebot.raisanngam.com/webhook  ->  raisanngam-linebot-prd  ->  VPS 127.0.0.1:8010
```

Use this same webhook/channel/service for Vision UAT. Isolation is by the
allowlisted Vision group ID, not by a new hostname, tunnel, or webhook. Keep
port 8010 bound to localhost; do not open it to the Internet or add router
port-forwarding. Before the first write, inspect the current signed POS target
and WAF rule read-only. Do not switch a shared POS base URL if it would change
the behavior of a legacy group.

## 3. Signed POS shared secret

The bot and POS must use the existing Production-only secret of at least 32
bytes. Never reuse a development secret or paste this value into source or
chat. The server-only runtime configuration and VPS environment file retain the
same value:

```text
uat_runtime/config/line-bot-integration.env
POS_LINE_BOT_SHARED_SECRET=<new random value>
```

The Production startup configuration must load the server-only file after a
reboot. HMAC with a fresh timestamp remains mandatory on every call. Keep any
source-IP restriction only when the origin can prove the VPS egress IP without
allowlisting broad Cloudflare ranges.

## 4. VPS environment file

After the code is copied to `/opt/raisanngam-line-bot/app` and
`deploy/line-bot/install-vps.sh` has been run as root, replace the generated
example at `/etc/raisanngam-line-bot/line-bot.env` with:

```ini
LINE_BOT_CHANNEL_SECRET=<from LINE Developers>
LINE_BOT_CHANNEL_ACCESS_TOKEN=<long-lived token from LINE Developers>
LINE_BOT_ALLOWED_GROUP_IDS=<set after first UAT group event>
LINE_BOT_VISION_PRODUCT_GROUP_IDS=<UAT/Production Vision group; must be allowed>
LINE_BOT_ENROLLMENT_MODE=1
LINE_BOT_USER_ID=<Your user ID from Basic settings>
POS_LINE_BOT_BASE_URL=https://posbot.raisanngam.com
POS_LINE_BOT_SHARED_SECRET=<existing Production-only shared secret>
LINE_BOT_DATA_ROOT=/var/lib/raisanngam-line-bot
LINE_BOT_PORT=8010
LINE_BOT_RETRY_SECONDS=300
GEMINI_API_KEY=<required only when a Vision group is enabled>
# Use a provider-verified structured-Vision model. `gemini-3.1-flash` is not
# an interchangeable model ID; the current supported example is Flash-Lite.
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_TIMEOUT_SECONDS=25
# Exactly one provider attempt per product; failures use manual fallback.
GEMINI_MAX_ATTEMPTS=1
GEMINI_MONTHLY_BUDGET_USD=1.00
# USD per 1M tokens; update these together with GEMINI_MODEL after checking
# the enabled billing project's current provider pricing.
GEMINI_INPUT_USD_PER_MILLION_TOKENS=0.25
GEMINI_OUTPUT_USD_PER_MILLION_TOKENS=1.50
```

The model must be enabled and successfully probed in the billing project before
this configuration is deployed. The bot disables its thinking budget so the
bounded response allowance is available for the prompt-constrained JSON object,
then validates that object against its local schema before using it; a
malformed, unavailable, or empty response always falls back to manual name
entry.

Set permissions and start only after all placeholders have values:

```bash
chown root:raisanngam-line-bot /etc/raisanngam-line-bot/line-bot.env
chmod 0640 /etc/raisanngam-line-bot/line-bot.env
systemctl restart raisanngam-line-bot
systemctl status raisanngam-line-bot --no-pager
curl -fsS http://127.0.0.1:8010/health
```

## 5. Connect LINE and obtain the group allowlist value

1. Retain the approved existing Production LINE webhook URL and press
   **Verify**. UAT uses Group Mode on the same webhook; do not create or switch
   to a second webhook URL.
2. Start once with `LINE_BOT_ENROLLMENT_MODE=1` and an empty allowlist. This
   temporary mode records a signed group ID but never sends a reply or runs a
   product operation.
3. Invite the bot into the Manager UAT group and send one disposable message.
   On the VPS retrieve its ID with
   `sudo -u raisanngam-line-bot sqlite3 /var/lib/raisanngam-line-bot/line_bot.db 'SELECT group_id FROM enrollment_groups;'`.
4. Copy the intended value into `LINE_BOT_ALLOWED_GROUP_IDS`, set
   `LINE_BOT_ENROLLMENT_MODE=0`, and restart the service. It will then ignore
   every other group.
5. Send a clear **linear barcode** image (EAN/UPC/Code 128 etc.), Quote it,
   and send `บอท` (then repeat using a real `@bot` mention). QR Code and other
   two-dimensional codes are deliberately rejected. Verify the cost/price,
   unknown/placeholder, cancel, stale-product conflict, and POS-outage
   retry flows.

To enable the automatic Vision Product Flow for the captured UAT group, add its
value to `LINE_BOT_VISION_PRODUCT_GROUP_IDS`, add the Gemini values above, and
restart the service. This list must be a subset of the allowlist. After UAT
acceptance, promote the same group ID without changing the webhook/channel.

## 6. Group interaction behavior

Every choice button uses a LINE **Message action**, not a postback. The selected
label is therefore visible in the group as a message from the staff member and
the bot receives that member's user ID before advancing the flow. Legacy Quote
flows are intentionally shared by the group; Vision Product flows remain
owner-bound. This avoids silent confirmation actions in group chats.

The bot does not send a greeting when it is called. Its first chat message is
the barcode/product result. That result uses the Quote event's reply token when
it is still valid, then falls back to a group push. If LINE rejects a true user
mention, the same result is automatically re-sent as ordinary group text rather
than failing the workflow.

The bot has no product-image maintenance flow. Both existing and new products
can be maintained only for name creation/completion and price changes. Cost may
have up to two satang digits (for example, `12.50`) and is sent to POS as an
exact integer satang value; selling price remains a positive whole-baht value
and must be greater than any nonzero cost. Normal POS product-image controls
remain separate and unchanged.

Quoted LINE image bytes are decoded in memory and are never written to the VPS
filesystem. The bot retains only the LINE message ID and source group needed to
validate a later Quote. Any member of that same group may Quote the image within
24 hours, and all group members may progress, cancel, or confirm that group's
one active legacy flow. The signed POS command records the actual confirmer.
Vision Product flows remain owner-bound. The worker removes expired references
within the next five-minute cleanup cycle. This retention does not delete the
original message from the LINE group; only LINE/the sender controls that chat
history.

When an existing barcode is found, the first choice message shows the current
Thai product name, cost, and selling price before offering price maintenance.

### Manual barcode commands

Allowed-group members can perform a read-only lookup without starting a flow:

```text
/check 1100000
```

If the barcode exists, the Bot replies once with its product name, barcode,
and current selling price. If it does not exist, the Bot reports that once and
does not start a conversation or offer another action.

An allowed-group member can prepare a new product or complete a Placeholder
without sending images:

```text
/bot 1100000|Singha Beer|80
```

The three fields are barcode, product name, and positive whole-baht selling
price. A pipe is the delimiter so product names may contain spaces. The Bot
performs the signed POS lookup first, sets cost to zero, and then shows the
same shared confirmation buttons used by the normal create flow. Any member
of the group may confirm or cancel, and the actual confirmer remains in the
signed audit source. A named existing product is reported but never overwritten
by `/bot`; use the existing maintenance flow instead. Neither manual command
calls Gemini, stores an image, or consumes Push quota while its Reply token is
valid.

### Vision Product Group behavior

A group in `LINE_BOT_VISION_PRODUCT_GROUP_IDS` receives exactly two product
photos automatically. The Bot collects `imageSet` indexes deterministically,
including reversed webhook order. Without `imageSet` metadata it pairs only the
same group/user's two images within 15 seconds. It stores only temporary LINE
message IDs in Bot SQLite, never image bytes.

The dedicated Vision worker validates both images in memory, decodes a linear
barcode locally, and calls signed POS lookup before Gemini. Existing named
products never call Gemini: the staff member may change only the selling price
and the Bot sends the unchanged current `cost_satang` back to the existing POS
price endpoint. For unknown barcodes and Placeholders, Gemini may propose a
name which the owner must confirm or edit; the Bot then asks only for a positive
whole-baht selling price and sends `create_or_complete` with `cost_satang=0`.
No Vision command contains an image field or changes a POS product image.

Gemini is limited to one durable job at a time and is separate from the webhook,
legacy flow, and POS retry worker. Timeout, exhausted 429/5xx, invalid
structured output, safety refusal, or an unreadable name falls back to manual
name entry when one barcode was decoded. Missing/ambiguous barcodes or clearly
different products require two new photos.

### Gemini monthly spending control

`GEMINI_MONTHLY_BUDGET_USD` is an application-enforced hard cap, defaulting to
`1.00`. Before a Gemini request, the Bot atomically reserves a conservative
maximum for the two bounded images and 512 output tokens. If the reservation
would exceed the calendar-month cap in Thailand time, the Bot does not call
Gemini and continues in `VISION_NAME_EDIT` with: “วงเงิน AI สำหรับเดือนนี้ครบแล้วครับ
กรุณาพิมพ์ชื่อสินค้าเองได้เลย 😊”. The new calendar month naturally starts a
new ledger; no manual reset or deletion is needed.

The Bot stores only aggregate monthly usage and idempotent request ledger data:
month, request count, reserved/estimated cost, actual token-derived cost when
the SDK returns usage metadata, timestamps, and the job/attempt key. A repeated
webhook, worker recovery, or retry cannot reuse that attempt key to call Gemini
again. Missing usage metadata deliberately retains the full reservation. This
is stricter than assuming a failed or partial API response was free.

Existing named products never reach this ledger: the worker decodes the barcode
locally and performs signed POS lookup first. Only unknown/Placeholder products
with one barcode can reserve one Gemini call for their two images. Keep
`GEMINI_MAX_ATTEMPTS` is fixed at `1`: a transient Gemini failure proceeds to
manual name entry instead of retrying the provider. This prevents one new
product from consuming two attempts and preserves the most products within the
monthly limit.

Run this privileged, secret-free diagnostic on the VPS (it outputs no API key,
token, group ID, or image data):

```bash
sudo -u raisanngam-line-bot sh -c 'set -a; . /etc/raisanngam-line-bot/line-bot.env; set +a; /opt/raisanngam-line-bot/venv/bin/python -m line_bot gemini-budget'
```

It reports the Thailand calendar month, request count, estimated and actual
USD cost, and remaining budget. It is intentionally not a public HTTP endpoint.

Also create a matching Google Cloud Billing budget for the same project: choose
monthly calendar period, USD 1.00 amount, and email alerts at 50%, 90%, and
100%. Budget alerts are monitoring only and do not stop requests immediately;
the Bot ledger above remains the enforcement control. Before changing
`GEMINI_MODEL`, verify the provider's exact current input/output prices and
update both `GEMINI_*_USD_PER_MILLION_TOKENS` values. The cap is only as
conservative as those configured prices.

Each group/user flow expires one minute after its latest interaction. The worker
closes expired flows once per second and sends `ผมยกเลิกรายการแล้วเนื่องจากเกินเวลาที่กำหนด
กรุณาทำรายการใหม่อีกครั้งครับ ⏰` in the same group. Short friendly emoji are
used in prompts and outcome messages; button labels remain plain Thai text so
they stay easy to select and identify.

When a staff member confirms a change, the Bot makes the bounded POS request
immediately and uses that message's fresh reply token for the **final** success,
conflict, validation-failure, or initial-outage result. It does not send a
separate “connecting” message first. Reply messages do not count against the
LINE Official Account monthly message plan, so normal one-second POS updates
use no Push-message quota. The POS request is bounded to 30 seconds, leaving a
55-second response safety window.

If the reply token is unavailable (for example, a delayed durable retry), the
outcome is stored in Bot SQLite's `pending_notifications` outbox and sent as a
group Push when LINE accepts delivery again. Each deferred Push has a stable
LINE retry key so transient network failures cannot duplicate it. A 429 monthly
limit is retained and retried hourly; it never changes the already-recorded POS
command result. Inspect only secret-free operational diagnostics with:

```bash
journalctl -u raisanngam-line-bot.service --since '1 hour ago' --no-pager
```

The journal records opaque command/notification IDs, operation, attempt,
outcome, and bounded delivery/POS errors. It never logs access tokens, shared
secrets, image bytes, or full product command payloads. Downloading and reading
the quoted barcode image is bounded to 10 seconds; a timeout asks for a clear
barcode image again.

## Inputs still needed to activate live UAT

- LINE Messaging API channel secret
- LINE long-lived channel access token
- LINE Bot user ID
- verified access to the existing `raisanngam-linebot-prd` tunnel and
  `linebot.raisanngam.com` route
- UAT group ID, captured after the first signed webhook event
- Gemini API key and an approved stable Vision model when a Vision group is enabled

The application has no fallback to the customer LIFF credentials; customer
ordering identity and staff group-bot authority remain separate.
