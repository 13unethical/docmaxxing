#!/usr/bin/env bash
# Keep the student humanizer (and detector via /api/humanizer/warm) warm in peak hours.
# Tashkent (UTC+5): 09:00–01:00 → UTC 04:00–20:00. Outside that window, exit quietly
# so Modal can scale to zero overnight.
#
# Install (VPS):
#   */1 * * * * /root/docmaxxing/scripts/keep_humanizer_warm_peak.sh
#
# Cost floor with min_containers=1 on L40S (~$1.95/h): 16 h/day × 30 ≈ $940/mo GPU only.
# Prefer Modal Cron peak_warm_pool / offpeak_scale_to_zero on serve_modal.py; this ping is backup.
set -euo pipefail
# UTC hour 4..19 inclusive = Tashkent 09:00–00:59
hour_utc=$(date -u +%H)
hour_utc=${hour_utc#0}
if (( hour_utc < 4 || hour_utc >= 20 )); then
  exit 0
fi
BASE="${DOCMAXXING_BASE_URL:-https://docmaxxing.com}"
curl -fsS -m 25 "${BASE}/api/browser/humanizer/warm" >/dev/null || true
