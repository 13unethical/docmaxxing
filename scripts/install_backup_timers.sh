#!/usr/bin/env bash
# Install backup systemd units. Run on the VPS from the app root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
chmod 755 "$ROOT/scripts/backup.sh" "$ROOT/scripts/restore_check.sh"
install -m 644 "$ROOT/deploy/docmaxxing-backup-daily.service" /etc/systemd/system/docmaxxing-backup-daily.service
install -m 644 "$ROOT/deploy/docmaxxing-backup-daily.timer" /etc/systemd/system/docmaxxing-backup-daily.timer
install -m 644 "$ROOT/deploy/docmaxxing-backup-weekly.service" /etc/systemd/system/docmaxxing-backup-weekly.service
install -m 644 "$ROOT/deploy/docmaxxing-backup-weekly.timer" /etc/systemd/system/docmaxxing-backup-weekly.timer
install -m 644 "$ROOT/deploy/docmaxxing-restore-check.service" /etc/systemd/system/docmaxxing-restore-check.service
install -m 644 "$ROOT/deploy/docmaxxing-restore-check.timer" /etc/systemd/system/docmaxxing-restore-check.timer
mkdir -p /var/backups/docmaxxing
chmod 700 /var/backups/docmaxxing
systemctl daemon-reload
systemctl enable --now docmaxxing-backup-daily.timer
systemctl enable --now docmaxxing-backup-weekly.timer
systemctl enable --now docmaxxing-restore-check.timer
echo "Backup timers enabled:"
systemctl list-timers 'docmaxxing-backup-*' 'docmaxxing-restore-check.timer' --no-pager
