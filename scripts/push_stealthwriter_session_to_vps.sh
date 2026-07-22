#!/usr/bin/env bash
# Run ON YOUR MAC. Uploads Playwright storageState (browser_profiles/sessions/stealthwriter.json).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="$ROOT/browser_profiles/sessions/stealthwriter.json"
DEST="${1:-}"

if [[ -z "$DEST" ]]; then
  echo "Usage: bash scripts/push_stealthwriter_session_to_vps.sh root@YOUR_VPS_IP"
  exit 1
fi

if [[ ! -f "$SESSION" ]]; then
  echo "Missing $SESSION"
  echo "Run: python3 scripts/export_stealthwriter_session.py"
  exit 1
fi

echo "Uploading StealthWriter storageState ($(du -h "$SESSION" | cut -f1)) → $DEST"
ssh "$DEST" "mkdir -p ~/docmaxxing/browser_profiles/sessions"
scp "$SESSION" "$DEST:~/docmaxxing/browser_profiles/sessions/stealthwriter.json"

echo ""
echo "On VPS:"
echo "  sudo systemctl restart docmaxxing"
echo "  sleep 8"
echo "  curl -sS http://127.0.0.1:8000/api/browser/providers/stealthwriter/status"
