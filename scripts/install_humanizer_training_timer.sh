#!/usr/bin/env bash
# Install Humanizer training systemd timers (synthetic daily + real-user export).
# Run on the VPS from the app root.
# Enables timer schedules only — does not start oneshot services immediately.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

install -m 644 "$ROOT/deploy/docmaxxing-humanizer-training-daily.service" \
  /etc/systemd/system/docmaxxing-humanizer-training-daily.service
install -m 644 "$ROOT/deploy/docmaxxing-humanizer-training-daily.timer" \
  /etc/systemd/system/docmaxxing-humanizer-training-daily.timer

install -m 644 "$ROOT/deploy/docmaxxing-humanizer-training-export.service" \
  /etc/systemd/system/docmaxxing-humanizer-training-export.service
install -m 644 "$ROOT/deploy/docmaxxing-humanizer-training-export.timer" \
  /etc/systemd/system/docmaxxing-humanizer-training-export.timer

mkdir -p "$ROOT/data/humanizer_training/synthetic_daily"
mkdir -p "$ROOT/data/humanizer_training/real_user_raw"

systemctl daemon-reload
# Enable + start timers (schedules next OnCalendar). Do NOT start .service oneshots here.
systemctl enable --now docmaxxing-humanizer-training-daily.timer
systemctl enable --now docmaxxing-humanizer-training-export.timer

echo "Humanizer training timers enabled:"
systemctl list-timers 'docmaxxing-humanizer-training-*.timer' --no-pager
systemctl is-enabled docmaxxing-humanizer-training-daily.timer
systemctl is-enabled docmaxxing-humanizer-training-export.timer
