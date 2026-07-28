# VPS Setup

The Windows POS initiates outbound SFTP. The VPS never connects back to the
store computer and the POS does not require internet access to sell.

## 1. Create a key on the POS computer

Run OpenSSH's key generator as the Windows account that runs the POS. Store the
private key outside Git, for example under the
production runtime config directory, and protect it with Windows ACLs:

    ssh-keygen -t ed25519 -f C:\ProgramData\SaengngamPOS\config\vps-backup-ed25519
    ssh-keyscan -H 169.58.77.35 > C:\ProgramData\SaengngamPOS\config\vps-known-hosts

Review the host key out-of-band before trusting the known-hosts file. The
private key is never copied into this repository or printed in a support
bundle.

## 2. Provision the Ubuntu server

Copy only the public key to the server and run as root:

    sudo ./deploy/vps/setup-pos-backup-server.sh \
      --store-id store-001 \
      --public-key-file /root/store-001-vps-backup-ed25519.pub
    sudo ./deploy/vps/verify-pos-backup-server.sh --store-id store-001

The setup creates `posbackup`, disables password login for that user, forces
internal SFTP, disables forwarding and shell access, and creates:

    /srv/pos-backups/store-001/
      database-backups/  file-snapshots/  file-backups/  manifests/  status/

The SFTP-visible root is `/store-001` because the account is chrooted to
`/srv/pos-backups`.

## 3. Configure the POS

Set these values in the local production environment or the protected
`runtime/config/production.json`. Do not put passwords, private keys, or API
tokens in Git:

    POS_VPS_HOST=169.58.77.35
    POS_VPS_USER=posbackup
    POS_VPS_PORT=22
    POS_VPS_ROOT=/
    POS_VPS_STORE_ID=store-001
    POS_VPS_KEY_FILE=C:\ProgramData\SaengngamPOS\config\vps-backup-ed25519
    POS_VPS_KNOWN_HOSTS=C:\ProgramData\SaengngamPOS\config\vps-known-hosts
    POS_VPS_VERIFY_DOWNLOAD=1
    POS_VPS_RETRIES=3
    POS_SYNC_PATHS=uploads/products

Test from the POS computer with the same key and known-hosts file:

    sftp -o BatchMode=yes -o StrictHostKeyChecking=yes `
      -o UserKnownHostsFile=C:\ProgramData\SaengngamPOS\config\vps-known-hosts `
      -i C:\ProgramData\SaengngamPOS\config\vps-backup-ed25519 `
      posbackup@169.58.77.35

Then run a manual backup:

    .\backup-production.ps1

## 4. Server retention

Run the retention script from a protected root cron/systemd timer. It only
removes archives with completion markers and always keeps the newest archive:

    sudo ./deploy/vps/backup-retention.sh --store-id store-001 --retention-days 30

Do not delete the only known-good local archive while setting up the VPS.
