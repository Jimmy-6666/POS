#!/usr/bin/env bash
set -euo pipefail

STORE_ID=""
PUBLIC_KEY_FILE=""
BASE_DIR="/srv/pos-backups"
USER_NAME="posbackup"

usage() { echo "Usage: $0 --store-id ID --public-key-file FILE [--base-dir DIR]" >&2; exit 2; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --store-id) STORE_ID="$2"; shift 2;;
    --public-key-file) PUBLIC_KEY_FILE="$2"; shift 2;;
    --base-dir) BASE_DIR="$2"; shift 2;;
    *) usage;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
[[ "$STORE_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || { echo "Invalid store id." >&2; exit 1; }
[[ -f "$PUBLIC_KEY_FILE" ]] || { echo "Public key file was not found." >&2; exit 1; }
command -v sshd >/dev/null || { echo "OpenSSH server is required." >&2; exit 1; }

id "$USER_NAME" >/dev/null 2>&1 || useradd --system --home-dir "$BASE_DIR" --shell /usr/sbin/nologin "$USER_NAME"
install -d -o root -g root -m 0755 "$BASE_DIR"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$BASE_DIR/$STORE_ID"
for directory in database-backups file-snapshots manifests status quarantine; do
  install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$BASE_DIR/$STORE_ID/$directory"
done
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$(dirname "$(getent passwd "$USER_NAME" | cut -d: -f6)")/.ssh"
SSH_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)/.ssh"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$SSH_DIR"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 "$PUBLIC_KEY_FILE" "$SSH_DIR/authorized_keys"

SSHD_DROPIN="/etc/ssh/sshd_config.d/posbackup.conf"
install -d -m 0755 /etc/ssh/sshd_config.d
cat > "$SSHD_DROPIN" <<EOF
Match User $USER_NAME
    ChrootDirectory $BASE_DIR
    ForceCommand internal-sftp
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    PubkeyAuthentication yes
    AllowTcpForwarding no
    X11Forwarding no
    PermitTunnel no
EOF
chmod 0644 "$SSHD_DROPIN"
sshd -t
systemctl reload sshd 2>/dev/null || systemctl reload ssh
echo "SFTP-only backup user configured: $USER_NAME"
echo "Client-visible store path: /$STORE_ID"
