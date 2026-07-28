# แสนงาม มินิมาร์ท POS — Version 2.2

Released 2026-07-28.

## Highlights

- LINE LIFF is the required customer identity for new online orders. Customer
  registered name, LINE name, confirmed phone, and delivery defaults remain
  separate and auditable.
- Suspended customers receive a stable blocked page. Admin deletion preserves
  relational order history, anonymizes identifiers, requires admin PIN, and
  allows later registration with the same LINE/phone.
- Customer checkout combines delivery and payment in one compact step followed
  by confirmation. Customers can reuse up to five distinct recent delivery
  details without overwriting their registered defaults.
- POS and online negative-stock permissions are configured independently.
- Backup ZIPs contain the verified SQLite database and metadata only. Product
  images use incremental VPS sync; replaced or locally deleted snapshots move
  into timestamped `file-backups/` paths.
- The Backup page shows the latest server status, supports manual sending, and
  controls the daily Asia/Bangkok send time. The POS must be running during the
  configured minute.
- Administrators have runtime health, redacted support bundle, and controlled
  signed-update hand-off tools.

## Runtime

- Desktop release: port `8002`, runtime root `runtime/`.
- UAT: port `8001`, runtime root `uat_runtime/`.
- Customer entry: `https://online.raisanngam.com/order`.
- Python runtime remains Flask/Waitress/SQLite with no Node, Docker, CDN, or
  frontend build requirement.

## Upgrade

Use the production lifecycle scripts in `docs/PRODUCTION_INSTALLATION.md`.
Database migrations are additive and preserve existing rows. Installation or
repair removes the legacy daily backup Task Scheduler job because Version 2.2
uses the time configured in the Backup page.

Before production promotion, run the complete test suite and review
`FEATURE_STATUS.md`. UAT catalog values with synthetic barcodes/mock prices are
not automatically approved as production master data.
