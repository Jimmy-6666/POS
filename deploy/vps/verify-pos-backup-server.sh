#!/usr/bin/env bash
set -euo pipefail
STORE_ID=""
BASE_DIR="/srv/pos-backups"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --store-id) STORE_ID="$2"; shift 2;;
    --base-dir) BASE_DIR="$2"; shift 2;;
    *) echo "Usage: $0 --store-id ID [--base-dir DIR]" >&2; exit 2;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
[[ "$STORE_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || { echo "Invalid store id." >&2; exit 1; }
id posbackup >/dev/null 2>&1 || { echo "posbackup user is missing." >&2; exit 1; }
test "$(stat -c '%U:%a' "$BASE_DIR/$STORE_ID")" = "posbackup:700"
for directory in database-backups file-snapshots manifests status quarantine; do
  test "$(stat -c '%U:%a' "$BASE_DIR/$STORE_ID/$directory")" = "posbackup:700"
done
grep -q '^    ForceCommand internal-sftp$' /etc/ssh/sshd_config.d/posbackup.conf
grep -q '^    PasswordAuthentication no$' /etc/ssh/sshd_config.d/posbackup.conf
sshd -t
echo "POS backup SFTP server verification passed for $STORE_ID"
