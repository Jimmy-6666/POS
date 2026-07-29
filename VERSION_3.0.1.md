# Saengngam Minimart POS — Version 3.0.1

Released 2026-07-29.

## Emergency private-LAN access update

- The POS server continues to listen on `0.0.0.0` and now permits authenticated
  staff use from the configured private LAN `192.168.0.0/24`.
- Other POS terminals and iPad/tablet browsers on the same trusted LAN use
  `http://192.168.0.200:8002` with the Desktop Launcher, or port `8000` when
  the scheduled Production service is installed with its default port.
- Requests outside the configured LAN remain blocked from staff login and from
  reusing a staff session. Customer and remote-Admin hostname isolation remains
  unchanged; the remote Admin hostname still requires Admin role and 2FA.
- Includes the public Thai privacy policy at `/order/policy` and its customer
  host regression, matching the already-verified customer-machine build.
- `configure-production-network.ps1` configures the active Windows LAN adapter
  with static IPv4 `192.168.0.200/24`, gateway `192.168.0.1`, Google DNS
  `8.8.8.8`/`8.8.4.4`, changes the
  connected profile to Private, writes the matching runtime configuration, and
  creates a Private/LocalSubnet-only firewall rule.

## Apply on the server

Close the POS, open PowerShell as Administrator in the application folder, and
run:

    .\configure-production-network.ps1

If Windows finds more than one connected adapter, specify the one used by the
shop LAN:

    .\configure-production-network.ps1 -InterfaceAlias "Wi-Fi"

Then start the Desktop Launcher and verify from another device on the same
Wi-Fi:

    http://192.168.0.200:8002/health
    http://192.168.0.200:8002/login

Do not forward port `8002` or `8000` from the router to the internet. Keep the
Windows network profile Private and keep the firewall scope at LocalSubnet.

## Compatibility

- No database schema or migration change.
- Existing database, uploads, secrets, backups, and browser profiles are
  preserved.
- The IP change is a persistent Windows adapter setting. The server must remain
  on the `192.168.0.0/24` shop LAN whose gateway is `192.168.0.1`.

## Verification

- Windows network report: static `192.168.0.200/24`, gateway
  `192.168.0.1`, DNS `8.8.8.8`/`8.8.4.4`.
- Firewall: enabled inbound TCP `8002`, Private profile, RemoteAddress
  `LocalSubnet`.
- Live runtime: local and LAN `/health` returned HTTP 200 with database ready;
  LAN `/login` returned HTTP 200 with pre-session CSRF.
- Focused access/runtime/launcher suite: 29 passed.
- Full suite: 153 passed with one existing filesystem-capability skip.
