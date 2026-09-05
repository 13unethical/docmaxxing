#!/usr/bin/env bash
# Install synthetic Humanizer training systemd timer. Run on the VPS from the app root.
# Enables the timer schedule only — does not start a oneshot collection immediately.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

install -m 644 "$ROOT/deploy/docmaxxing-humanizer-training-daily.service" \
  /etc/systemd/system/docmaxxing-humanizer-training-daily.service
install -m 644 "$ROOT/deploy/docmaxxing-humanizer-training-daily.timer" \
  /etc/systemd/system/docmaxxing-humanizer-training-daily.timer

mkdir -p "$ROOT/data/humanizer_training/synthetic_daily"

systemctl daemon-reload
# Enable + start timer (schedules next OnCalendar). Do NOT start the .service oneshot here.
systemctl enable --now docmaxxing-humanizer-training-daily.timer

echo "Humanizer training timer enabled:"
systemctl list-timers 'docmaxxing-humanizer-training-daily.timer' --no-pager
systemctl is-enabled docmaxxing-humanizer-training-daily.timer
