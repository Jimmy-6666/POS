#!/usr/bin/env bash
set -euo pipefail

# Run as root after copying the reviewed source package to
# /opt/raisanngam-line-bot/app.  Secrets belong only in the EnvironmentFile.
install -d -m 0755 /opt/raisanngam-line-bot /etc/raisanngam-line-bot
id -u raisanngam-line-bot >/dev/null 2>&1 || useradd --system --home /var/lib/raisanngam-line-bot --shell /usr/sbin/nologin raisanngam-line-bot
install -d -o raisanngam-line-bot -g raisanngam-line-bot -m 0700 /var/lib/raisanngam-line-bot
python3 -m venv /opt/raisanngam-line-bot/venv
/opt/raisanngam-line-bot/venv/bin/pip install -r /opt/raisanngam-line-bot/app/line_bot/requirements.txt
install -o root -g root -m 0644 /opt/raisanngam-line-bot/app/deploy/line-bot/raisanngam-line-bot.service /etc/systemd/system/raisanngam-line-bot.service
install -o root -g raisanngam-line-bot -m 0640 /opt/raisanngam-line-bot/app/line_bot/.env.example /etc/raisanngam-line-bot/line-bot.env
systemctl daemon-reload
systemctl enable raisanngam-line-bot.service
echo "Edit /etc/raisanngam-line-bot/line-bot.env with real secrets and group ID, then run: systemctl restart raisanngam-line-bot"
