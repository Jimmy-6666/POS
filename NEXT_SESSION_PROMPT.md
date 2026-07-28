# Hands-on Prompt for the Next Session

Copy the prompt below into the next Codex session:

```text
Continue the Thai Minishop POS from the published Version 2.2 baseline.

Workspace:
C:\Users\Zekken\Documents\Codex\2026-07-22\files-mentioned-by-the-user-you\outputs\thai-minimart-pos-v2.1

Start hands-on:
1. Read AGENTS.md, then read only AI_CONTEXT.md, PROJECT_MAP.md,
   FEATURE_STATUS.md, DECISIONS.md, CODING_RULES.md, and DESIGN_RULES.md.
2. Confirm git branch/tag and run `git status --short`. Preserve all existing
   data and do not discard uncommitted user work.
3. Read VERSION_2.2.md and the newest CHANGELOG.md section before changing
   release behavior.
4. Verify UAT at http://127.0.0.1:8001/health and confirm LIFF config through
   /api/auth/config if the current task touches customer ordering.
5. For backup work, inspect the Backup page status and
   uat_runtime/support/remote-backup-status.json. Do not copy secrets, private
   keys, passwords, databases, or runtime files into Git or support output.
6. Run focused tests for every change and the full suite for shared logic,
   schema, auth, sales, inventory, reconciliation, backup, or release work.

Current Version 2.2 facts:
- LINE LIFF customer auth is active at https://online.raisanngam.com/order.
- UAT runs on port 8001; desktop release defaults to port 8002.
- POS and online negative-stock settings are independent.
- Customer deletion is an audited anonymizing tombstone and permits
  re-registration with the same LINE/phone.
- Checkout is compact and can reuse five recent delivery snapshots.
- Database ZIPs exclude product images. Product images sync by delta to the
  VPS; replaced/deleted remote snapshots move to file-backups/.
- The UAT VPS image baseline contains 385 product images.
- Daily backup time is configured in the Backup page and runs only while the
  POS is open during that minute.
- The latest release suite count is recorded in FEATURE_STATUS.md.
- Production catalog still requires owner-approved real barcodes and prices;
  UAT mock values are not production approval.

Do not start a new sprint or broaden product scope until the owner explicitly
approves it. If the owner gives a specific fix within Version 2.2, implement
and verify that fix without inventing a new sprint.
```
