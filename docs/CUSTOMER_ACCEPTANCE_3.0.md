# Version 3.0 Customer Acceptance

Record the result, operator, machine, and timestamp for every item. Do not mark
a provider or physical-device check passed without observing it.

## Installation

- Extract the checksum-verified release ZIP to a stable path.
- Use Windows 10 or newer and Python 3.11 or newer.
- Run `install-production.ps1` elevated, then `verify-production.ps1`.
- Confirm the startup task exists, the obsolete backup task does not exist,
  and the firewall rule is Private/LocalSubnet only.
- Restart Windows and confirm `/health` reports an operational database.

## Store workflow

- Enroll the owner Admin, replace temporary credentials, and save TOTP recovery
  codes offline.
- Confirm Manager and Cashier can sign in only through localhost.
- Test a barcode scanner, weighted item, cash sale, transfer sale, receipt
  printer, item void, stock movement, closing, and reconciliation.
- Confirm production barcodes, prices, costs, stock, staff, and payment details
  are owner-approved; never promote mock UAT catalogue data.

## Backup and recovery

- Configure owner-approved VPS credentials if off-machine sync is required.
- Run `backup-production.ps1`; exit code 0 means local and remote succeeded,
  while code 2 means the verified local database backup succeeded but remote
  transfer or image sync failed.
- Run `backup-production.ps1 -FullRecoveryBundle`, copy the resulting
  `recovery-*.zip` to owner-controlled off-machine storage, and record SHA-256.
- Restore the bundle into an empty temporary runtime with
  `scripts/recover-production.ps1`, then run
  `scripts/verify-recovery.ps1`. Confirm the database and a sample product
  image are present.

## Public customer and Admin hosts

- Keep public-host settings unset until Cloudflare and LINE acceptance.
- Configure exact trusted hosts and a local trusted proxy; do not use wildcard
  hosts or expose Waitress directly to the internet.
- Apply Cloudflare Access to the Admin hostname and verify a non-Admin, an
  unenrolled Admin, and an Admin without second factor are rejected.
- Verify an enrolled Admin passes Cloudflare Access plus TOTP/recovery code.
- Complete LINE LIFF login, ordering, idempotent retry, cancellation, and
  delivery completion on a real phone.

## Approval boundary

The source release and offline Windows artifact may be approved before the
customer-site checks. Public DNS/tunnel activation and final store go-live are
separate operational approvals requiring recorded evidence from the target
machine, physical peripherals, Cloudflare, LINE, and the chosen off-machine
backup destination.
