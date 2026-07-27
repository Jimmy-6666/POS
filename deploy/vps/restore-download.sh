#!/usr/bin/env bash
set -euo pipefail
STORE_ID=""
BACKUP_NAME=""
DESTINATION=""
BASE_DIR="/srv/pos-backups"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --store-id) STORE_ID="$2"; shift 2;;
    --backup-name) BACKUP_NAME="$2"; shift 2;;
    --destination) DESTINATION="$2"; shift 2;;
    --base-dir) BASE_DIR="$2"; shift 2;;
    *) echo "Usage: $0 --store-id ID --backup-name NAME --destination FILE [--base-dir DIR]" >&2; exit 2;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
[[ "$STORE_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || { echo "Invalid store id." >&2; exit 1; }
[[ "$BACKUP_NAME" =~ ^backup-[A-Za-z0-9T Z_.:-]+\.zip$ ]] || { echo "Invalid backup name." >&2; exit 1; }
[[ -n "$DESTINATION" ]] || { echo "Destination is required." >&2; exit 1; }
SOURCE="$BASE_DIR/$STORE_ID/database-backups/$BACKUP_NAME"
MARKER="$BASE_DIR/$STORE_ID/status/${BACKUP_NAME%.zip}.complete"
[[ -f "$SOURCE" && -f "$MARKER" ]] || { echo "Backup is not complete or was not found." >&2; exit 1; }
install -D -m 0600 "$SOURCE" "$DESTINATION"
sha256sum "$DESTINATION"
