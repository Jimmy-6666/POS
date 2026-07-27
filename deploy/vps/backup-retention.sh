#!/usr/bin/env bash
set -euo pipefail
STORE_ID=""
BASE_DIR="/srv/pos-backups"
RETENTION_DAYS="30"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --store-id) STORE_ID="$2"; shift 2;;
    --base-dir) BASE_DIR="$2"; shift 2;;
    --retention-days) RETENTION_DAYS="$2"; shift 2;;
    *) echo "Usage: $0 --store-id ID [--base-dir DIR] [--retention-days N]" >&2; exit 2;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
[[ "$STORE_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || { echo "Invalid store id." >&2; exit 1; }
BACKUP_DIR="$BASE_DIR/$STORE_ID/database-backups"
STATUS_DIR="$BASE_DIR/$STORE_ID/status"
mapfile -t backups < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'backup-*.zip' -printf '%T@ %p\n' | sort -nr | awk '{print substr($0,index($0,$2))}')
[[ ${#backups[@]} -gt 0 ]] || exit 0
keep="${backups[0]}"
for archive in "${backups[@]:1}"; do
  marker="$STATUS_DIR/$(basename "${archive%.zip}").complete"
  [[ -f "$marker" ]] || continue
  if find "$archive" -maxdepth 0 -type f -mtime "+$RETENTION_DAYS" | grep -q .; then
    rm -f -- "$archive" "$marker" "$BASE_DIR/$STORE_ID/manifests/$(basename "${archive%.zip}").json"
  fi
done
echo "Remote retention completed; newest verified backup retained: $(basename "$keep")"
