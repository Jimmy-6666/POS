# Package Source

- Base repository: `https://github.com/Jimmy-6666/POS`
- Base branch/tag: `main` / `v3.1.5`
- Base commit: `e36ebe7465bc6b17f82d75a08326b7811ab0e62a`
- Package revision: `v3.1.5-prd-linebot-hotfix1`
- Added scope: approved LINE group product-maintenance bot candidate and
  signed POS integration (Migration 31), persistent Production LINE
  integration environment loading, and the post-reboot attach-only desktop
  shortcut ACL hotfix
- Build date: 2026-08-02 (Asia/Bangkok)

## Verification

- Original LINE candidate: 43 focused tests run; 42 passed and one
  filesystem-capability skip. Full suite: 221 tests run; 220 passed and the
  same skip.
- Final hotfix revision: 33/33 focused tests passed. Full suite: 222 tests
  run; 221 passed and one filesystem-capability skip.
- Packaging this revision does not restart or replace the running Production
  server. The attach-only shortcut hotfix takes effect on the next desktop
  launch; the SYSTEM server continues to load the protected LINE environment.

## Packaging policy

The source archive excludes `.git`, virtual environments, runtime/UAT data,
databases, uploads, backups, browser profiles, generated import/work output,
private keys, credentials, caches, and prior archives. `line_bot/.env.example`
is included with credential fields blank.

Use `HANDS_ON_PRD_LINEBOT_DEPLOY_PROMPT_TH.md` for Production deployment. The
deployment must preserve Release 3.1.5 behavior and must not downgrade to an
older source baseline.
