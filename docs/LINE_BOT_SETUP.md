# LINE Product-Maintenance Bot — UAT Setup

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
4. Do not set the webhook URL yet.  It is set after the VPS service and a
   public HTTPS hostname are healthy.

Treat the secret and access token as passwords.  Do not commit them, put them
in screenshots, or paste them in a Git issue.  They are stored only on the VPS
in `/etc/raisanngam-line-bot/line-bot.env` (mode `0640`, root-owned).

## 2. DNS and tunnel required for UAT

`https://dev.raisanngam.com` remains the POS UAT endpoint on port 8002. The
current UAT deployment uses its own public hostname:

```text
https://linebot-uat.raisanngam.com/webhook  ->  VPS localhost:8010
```

Use an outbound Cloudflare Tunnel on the VPS when the existing zone permits it.
No inbound port 8010 or router/firewall opening is required.  The POS bot
integration remains behind the existing UAT tunnel at:

```text
https://dev.raisanngam.com/_internal/line-bot/...
```

If Cloudflare WAF/Access protects `dev.raisanngam.com`, add an allow/skip rule
for VPS source IP `169.58.77.35` scoped as narrowly as possible to
`/_internal/line-bot/*`. The route still requires the independent timestamped
HMAC signature. Without this Cloudflare rule, the VPS receives Cloudflare
error `1010` before the POS can verify a request.

The UAT zone plan does not provide the certificate support needed for the
multi-level `bot.dev.raisanngam.com` hostname, so UAT deliberately uses the
single-level `linebot-uat.raisanngam.com` name instead. Do not route either
hostname to the Windows POS directly.

## 3. UAT shared secret

The UAT POS and VPS bot must share one new random secret of at least 32 bytes.
Generate it once on the Windows UAT machine, place only this line in the
ignored runtime file below, and place the same value in the VPS environment
file:

```text
uat_runtime/config/line-bot-integration.env
POS_LINE_BOT_SHARED_SECRET=<new random value>
```

`start-uat.bat` loads that ignored file, enables the signed service boundary,
uses port 8002, and trusts `dev.raisanngam.com`. Cloudflare Tunnel replaces the
original VPS address, so UAT does not use a source-IP filter; HMAC with a
fresh timestamp is the required authorization control on every call. A direct
production transport may add an independently verified source-IP filter later.

## 4. VPS environment file

After the code is copied to `/opt/raisanngam-line-bot/app` and
`deploy/line-bot/install-vps.sh` has been run as root, replace the generated
example at `/etc/raisanngam-line-bot/line-bot.env` with:

```ini
LINE_BOT_CHANNEL_SECRET=<from LINE Developers>
LINE_BOT_CHANNEL_ACCESS_TOKEN=<long-lived token from LINE Developers>
LINE_BOT_ALLOWED_GROUP_IDS=<set after first UAT group event>
LINE_BOT_ENROLLMENT_MODE=1
LINE_BOT_USER_ID=<Your user ID from Basic settings>
POS_LINE_BOT_BASE_URL=https://dev.raisanngam.com
POS_LINE_BOT_SHARED_SECRET=<same UAT shared secret>
LINE_BOT_DATA_ROOT=/var/lib/raisanngam-line-bot
LINE_BOT_PORT=8010
LINE_BOT_RETRY_SECONDS=300
```

Set permissions and start only after all placeholders have values:

```bash
chown root:raisanngam-line-bot /etc/raisanngam-line-bot/line-bot.env
chmod 0640 /etc/raisanngam-line-bot/line-bot.env
systemctl restart raisanngam-line-bot
systemctl status raisanngam-line-bot --no-pager
curl -fsS http://127.0.0.1:8010/health
```

## 5. Connect LINE and obtain the group allowlist value

1. Set the LINE webhook URL to
   `https://linebot-uat.raisanngam.com/webhook` and press **Verify**.
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

## 6. Group interaction behavior

Every choice button uses a LINE **Message action**, not a postback. The selected
label is therefore visible in the group as a message from the staff member and
the bot receives that member's user ID before advancing the owner-bound flow.
This avoids silent confirmation actions in group chats.

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
filesystem. The bot retains only the LINE message ID plus group/user ownership
needed to validate a later Quote. That reference becomes unusable after 24
hours and the worker removes expired references within the next five-minute
cleanup cycle. This retention does not delete the original message from the
LINE group; only LINE/the sender controls that chat history.

When an existing barcode is found, the first choice message shows the current
Thai product name, cost, and selling price before offering price maintenance.

Each group/user flow expires one minute after its latest interaction. The worker
closes expired flows once per second and sends `ผมยกเลิกรายการแล้วเนื่องจากเกินเวลาที่กำหนด
กรุณาทำรายการใหม่อีกครั้งครับ ⏰` in the same group. Short friendly emoji are
used in prompts and outcome messages; button labels remain plain Thai text so
they stay easy to select and identify.

When a staff member confirms a change, the bot immediately uses that message's
fresh reply token to state that it is connecting to the store. The POS request
is bounded to 30 seconds, leaving a 55-second response safety window. A genuine
stale-product conflict asks the staff member to try again, while any other
permanent validation rejection asks them to start a new flow; a connection
outage keeps the existing durable five-minute retry behavior. Downloading and reading
the quoted barcode image is bounded to 10 seconds; a timeout asks for a clear
barcode image again.

## Inputs still needed to activate live UAT

- LINE Messaging API channel secret
- LINE long-lived channel access token
- LINE Bot user ID
- permission to create/route the VPS HTTPS bot hostname, or the resulting
  hostname and its existing tunnel route
- UAT group ID, captured after the first signed webhook event

The application has no fallback to the customer LIFF credentials; customer
ordering identity and staff group-bot authority remain separate.
