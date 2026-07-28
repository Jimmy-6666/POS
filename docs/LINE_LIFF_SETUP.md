# LINE LIFF setup

Configure the existing LINE Login channel and LIFF app before exposing customer
ordering. No LINE credential is stored in source code or browser storage.

## LINE Developers Console

1. Confirm the LINE Login and Messaging API channels belong to the same LINE
   Provider.
2. Set the LIFF app Endpoint URL to `https://your-public-host/order`; use its
   generated LIFF URL in the Rich Menu.
3. Allow the same HTTPS public host for LINE Login and request `openid` and
   `profile`. No Messaging API access token is needed in this release.

## Windows production environment

In elevated PowerShell on the POS host, replace the quoted values with the real
LINE Console and Cloudflare values:

    [Environment]::SetEnvironmentVariable('LINE_LIFF_ID', 'real-liff-id', 'Machine')
    [Environment]::SetEnvironmentVariable('LINE_LOGIN_CHANNEL_ID', 'real-channel-id', 'Machine')
    [Environment]::SetEnvironmentVariable('APP_BASE_URL', 'https://your-public-host', 'Machine')
    [Environment]::SetEnvironmentVariable('POS_TRUST_PROXY', '1', 'Machine')

`LINE_LOGIN_CHANNEL_SECRET` is not required for the implemented ID-token
verification call. Never put it in frontend code. Restart and verify:

    .\restart-production.ps1
    .\verify-production.ps1

All three LINE values are required; ordering remains unavailable without them.
The public customer host must be HTTPS and reach Waitress only through the
trusted Cloudflare Tunnel/reverse proxy when `POS_TRUST_PROXY=1`.

## Live acceptance check

Open the Rich Menu LIFF link, complete LINE Login, enter phone/location/room on
first use, refresh, check `/api/auth/me`, and place an order. A second LINE
account must not open the first account's order URL. Never test by posting a
decoded token, profile object, or made-up user ID: the backend accepts and
verifies only the raw LIFF ID token.
